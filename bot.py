"""
SBER Scalping Bot — Tinkoff Invest API
Стратегия: EMA(9) / EMA(21) Cross + Volume Filter
Таймфрейм: 1 минута
"""

import asyncio
import logging
from datetime import datetime, timezone
from collections import deque

from tinkoff.invest import (
    AsyncClient,
    CandleInterval,
    OrderDirection,
    OrderType,
    Quotation,
)
from tinkoff.invest.utils import now
from tinkoff.invest.async_services import AsyncServices

from config import Config
from indicators import EMACalculator, VolumeFilter
from risk_manager import RiskManager
from logger import setup_logger

log = setup_logger("sber_scalper")


# ─────────────────────────────────────────────
#  Конвертеры Quotation ↔ float
# ─────────────────────────────────────────────

def q_to_float(q: Quotation) -> float:
    return q.units + q.nano / 1_000_000_000


def float_to_q(value: float) -> Quotation:
    units = int(value)
    nano = round((value - units) * 1_000_000_000)
    return Quotation(units=units, nano=nano)


# ─────────────────────────────────────────────
#  Основной класс бота
# ─────────────────────────────────────────────

class SBERScalpingBot:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.ema_fast = EMACalculator(period=cfg.EMA_FAST)
        self.ema_slow = EMACalculator(period=cfg.EMA_SLOW)
        self.vol_filter = VolumeFilter(window=cfg.VOL_WINDOW)
        self.risk = RiskManager(cfg)

        self.candles: deque = deque(maxlen=100)
        self.position: int = 0          # +1 long, -1 short, 0 нет
        self.entry_price: float = 0.0
        self.order_id: str | None = None
        self.last_signal: str = "none"  # 'buy' / 'sell' / 'none'

    # ─── Торговые часы МСК ───────────────────

    def _is_trading_time(self) -> bool:
        msk = datetime.now(tz=timezone.utc).astimezone(
            __import__("zoneinfo").ZoneInfo("Europe/Moscow")
        )
        start = msk.replace(hour=10, minute=1, second=0, microsecond=0)
        end   = msk.replace(hour=18, minute=25, second=0, microsecond=0)
        return start <= msk <= end

    # ─── Разместить рыночный ордер ───────────

    async def _place_order(
        self, client: AsyncServices, direction: OrderDirection, qty: int
    ) -> str | None:
        try:
            resp = await client.orders.post_order(
                figi=self.cfg.FIGI,
                quantity=qty,
                price=None,
                direction=direction,
                account_id=self.cfg.ACCOUNT_ID,
                order_type=OrderType.ORDER_TYPE_MARKET,
                order_id=f"scalp_{int(datetime.utcnow().timestamp()*1000)}",
            )
            log.info(
                "Ордер размещён | %s | qty=%d | order_id=%s",
                direction.name, qty, resp.order_id,
            )
            return resp.order_id
        except Exception as e:
            log.error("Ошибка размещения ордера: %s", e)
            return None

    # ─── Логика открытия позиции ─────────────

    async def _open_long(self, client: AsyncServices, price: float):
        if not self.risk.can_open(price, "long"):
            return
        qty = self.risk.position_size(price)
        oid = await self._place_order(client, OrderDirection.ORDER_DIRECTION_BUY, qty)
        if oid:
            self.position = 1
            self.entry_price = price
            self.order_id = oid
            self.risk.register_trade()
            log.info("▲ LONG открыт @ %.2f | qty=%d", price, qty)

    async def _open_short(self, client: AsyncServices, price: float):
        if not self.risk.can_open(price, "short"):
            return
        qty = self.risk.position_size(price)
        oid = await self._place_order(client, OrderDirection.ORDER_DIRECTION_SELL, qty)
        if oid:
            self.position = -1
            self.entry_price = price
            self.order_id = oid
            self.risk.register_trade()
            log.info("▼ SHORT открыт @ %.2f | qty=%d", price, qty)

    async def _close_position(self, client: AsyncServices, price: float, reason: str):
        direction = (
            OrderDirection.ORDER_DIRECTION_SELL
            if self.position == 1
            else OrderDirection.ORDER_DIRECTION_BUY
        )
        qty = self.risk.current_qty
        oid = await self._place_order(client, direction, qty)
        if oid:
            pnl = (price - self.entry_price) * self.position * qty
            self.risk.record_pnl(pnl)
            log.info(
                "■ Позиция закрыта [%s] @ %.2f | PnL=%.2f ₽",
                reason, price, pnl,
            )
            self.position = 0
            self.entry_price = 0.0
            self.order_id = None

    # ─── Проверка SL / TP ────────────────────

    async def _check_sl_tp(self, client: AsyncServices, price: float):
        if self.position == 0:
            return

        change = (price - self.entry_price) / self.entry_price * self.position

        if change <= -self.cfg.STOP_LOSS_PCT / 100:
            await self._close_position(client, price, "STOP-LOSS")
        elif change >= self.cfg.TAKE_PROFIT_PCT / 100:
            await self._close_position(client, price, "TAKE-PROFIT")

    # ─── Генерация сигнала ───────────────────

    def _get_signal(self, close: float, volume: int) -> str:
        fast = self.ema_fast.update(close)
        slow = self.ema_slow.update(close)
        high_vol = self.vol_filter.is_above_avg(volume)

        if fast is None or slow is None:
            return "none"

        # Запоминаем предыдущее соотношение
        prev_fast = self.ema_fast.prev_value
        prev_slow = self.ema_slow.prev_value

        if prev_fast is None or prev_slow is None:
            return "none"

        cross_up   = prev_fast <= prev_slow and fast > slow
        cross_down = prev_fast >= prev_slow and fast < slow

        if cross_up and high_vol:
            return "buy"
        if cross_down and high_vol:
            return "sell"
        return "none"

    # ─── Обработка новой свечи ───────────────

    async def _on_candle(self, client: AsyncServices, candle):
        close  = q_to_float(candle.close)
        volume = candle.volume

        self.candles.append({"close": close, "volume": volume})

        await self._check_sl_tp(client, close)

        signal = self._get_signal(close, volume)
        log.debug(
            "Свеча: close=%.2f vol=%d | EMA%d=%.4f EMA%d=%.4f | сигнал=%s",
            close, volume,
            self.cfg.EMA_FAST, self.ema_fast.value or 0,
            self.cfg.EMA_SLOW, self.ema_slow.value or 0,
            signal,
        )

        if not self._is_trading_time():
            if self.position != 0:
                await self._close_position(client, close, "КОНЕЦ ДНЯ")
            return

        if self.risk.daily_limit_reached():
            log.warning("Дневной лимит убытков достигнут. Торговля остановлена.")
            if self.position != 0:
                await self._close_position(client, close, "ДНЕВНОЙ ЛИМИТ")
            return

        # Открытие / разворот позиции
        if signal == "buy":
            if self.position == -1:
                await self._close_position(client, close, "разворот")
            if self.position == 0:
                await self._open_long(client, close)

        elif signal == "sell":
            if self.position == 1:
                await self._close_position(client, close, "разворот")
            if self.position == 0:
                await self._open_short(client, close)

    # ─── Исторические свечи (прогрев EMA) ───

    async def _warm_up(self, client: AsyncServices):
        log.info("Прогрев индикаторов...")
        from datetime import timedelta

        resp = await client.market_data.get_candles(
            figi=self.cfg.FIGI,
            from_=now() - timedelta(hours=2),
            to=now(),
            interval=CandleInterval.CANDLE_INTERVAL_1_MIN,
        )
        for c in resp.candles:
            close = q_to_float(c.close)
            self.ema_fast.update(close)
            self.ema_slow.update(close)
            self.vol_filter.push(c.volume)

        log.info(
            "Прогрев завершён: %d свечей | EMA%d=%.4f | EMA%d=%.4f",
            len(resp.candles),
            self.cfg.EMA_FAST, self.ema_fast.value or 0,
            self.cfg.EMA_SLOW, self.ema_slow.value or 0,
        )

    # ─── Основной цикл ───────────────────────

    async def run(self):
        log.info("=== SBER Scalping Bot запущен ===")
        async with AsyncClient(self.cfg.TOKEN) as client:
            await self._warm_up(client)

            async def stream():
                async for market_data in client.market_data_stream.market_data_stream(
                    self._subscription_request()
                ):
                    if market_data.candle:
                        await self._on_candle(client, market_data.candle)

            await stream()

    def _subscription_request(self):
        from tinkoff.invest import (
            MarketDataRequest,
            SubscribeCandlesRequest,
            SubscriptionAction,
            CandleInstrument,
            SubscriptionInterval,
        )
        return iter(
            [
                MarketDataRequest(
                    subscribe_candles_request=SubscribeCandlesRequest(
                        subscription_action=SubscriptionAction.SUBSCRIPTION_ACTION_SUBSCRIBE,
                        instruments=[
                            CandleInstrument(
                                figi=self.cfg.FIGI,
                                interval=SubscriptionInterval.SUBSCRIPTION_INTERVAL_ONE_MINUTE,
                            )
                        ],
                    )
                )
            ]
        )


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    from config import Config
    asyncio.run(SBERScalpingBot(Config()).run())

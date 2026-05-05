"""
Риск-менеджер.
Контролирует: дневной убыток, число сделок, размер позиции.
"""

import logging
from config import Config

log = logging.getLogger("sber_scalper")


class RiskManager:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.daily_pnl: float = 0.0
        self.trades_today: int = 0
        self.current_qty: int = 0

    # ─── Можно ли открыть сделку? ──────────────────────────────────────────

    def can_open(self, price: float, direction: str) -> bool:
        if self.daily_limit_reached():
            log.warning("RiskManager: дневной лимит убытков исчерпан")
            return False
        if self.trades_today >= self.cfg.MAX_TRADES_PER_DAY:
            log.warning("RiskManager: достигнут лимит сделок (%d)", self.cfg.MAX_TRADES_PER_DAY)
            return False
        return True

    def daily_limit_reached(self) -> bool:
        return self.daily_pnl <= -abs(self.cfg.MAX_DAILY_LOSS)

    # ─── Размер позиции ────────────────────────────────────────────────────

    def position_size(self, price: float) -> int:
        """Возвращает количество ЛОТОВ для сделки."""
        qty = self.cfg.LOT_SIZE
        self.current_qty = qty
        return qty

    # ─── Учёт сделок ───────────────────────────────────────────────────────

    def register_trade(self):
        self.trades_today += 1

    def record_pnl(self, pnl: float):
        self.daily_pnl += pnl
        log.info(
            "RiskManager | PnL сделки=%.2f ₽ | Дневной PnL=%.2f ₽ | Сделок: %d/%d",
            pnl, self.daily_pnl, self.trades_today, self.cfg.MAX_TRADES_PER_DAY,
        )

    def reset_daily(self):
        """Вызывать в начале каждого торгового дня."""
        self.daily_pnl = 0.0
        self.trades_today = 0

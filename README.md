# SBER Scalping Bot — Tinkoff Invest API

## Стратегия

| Параметр       | Значение        |
|----------------|-----------------|
| Инструмент     | SBER (Сбербанк) |
| Таймфрейм      | 1 минута        |
| Индикаторы     | EMA(9), EMA(21) |
| Фильтр объёма  | 1.2× от среднего |
| Take Profit    | 0.30%           |
| Stop Loss      | 0.15%           |
| Торговые часы  | 10:01–18:25 МСК |

### Логика входа

```
LONG:  EMA(9) пересекает EMA(21) снизу вверх + объём > 1.2× среднего
SHORT: EMA(9) пересекает EMA(21) сверху вниз + объём > 1.2× среднего
```

### Логика выхода

- **Take Profit** достигнут (+0.30%)
- **Stop Loss** сработал (−0.15%)
- Противоположный сигнал (разворот)
- Конец торгового дня (18:25 МСК)
- Дневной лимит убытков (настраивается в config.py)

---

## Установка

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## Настройка

### 1. Токен Tinkoff

Получите токен в [Tinkoff Invest](https://www.tbank.ru/invest/):
`Настройки → API → Создать токен`

Рекомендуется начать с **Sandbox**-токена.

### 2. Переменные окружения

```bash
export TINKOFF_TOKEN="t.ваш_токен"
export TINKOFF_ACCOUNT_ID="ваш_account_id"
export SANDBOX="true"   # или false для боевого
```

Или создайте `.env` файл и загружайте через `python-dotenv`.

### 3. Параметры стратегии

Все параметры в `config.py`:

```python
EMA_FAST = 9          # Период быстрой EMA
EMA_SLOW = 21         # Период медленной EMA
TAKE_PROFIT_PCT = 0.30
STOP_LOSS_PCT = 0.15
LOT_SIZE = 1          # Лотов на сделку (1 лот SBER = 10 акций)
MAX_DAILY_LOSS = 500  # Стоп торговли при убытке 500 ₽
MAX_TRADES_PER_DAY = 20
```

---

## Запуск

```bash
# Sandbox (рекомендуется для тестирования)
SANDBOX=true python bot.py

# Боевой режим (только после тщательного тестирования!)
SANDBOX=false python bot.py
```

---

## Структура файлов

```
sber_scalper/
├── bot.py           # Основной класс бота и точка входа
├── config.py        # Все параметры
├── indicators.py    # EMA и VolumeFilter
├── risk_manager.py  # Контроль рисков
├── logger.py        # Логирование
├── requirements.txt
└── logs/            # Создаётся автоматически
    └── sber_scalper.log
```

---

## ⚠️ Дисклеймер

Бот предназначен для **образовательных целей**. Торговля на финансовых
рынках сопряжена с риском потери капитала. Всегда тестируйте в Sandbox
перед запуском с реальными деньгами. Автор не несёт ответственности
за финансовые результаты.

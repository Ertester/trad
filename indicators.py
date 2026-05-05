"""
Технические индикаторы для скальпинг-бота.
"""

from collections import deque


class EMACalculator:
    """
    Экспоненциальная скользящая средняя (EMA) на потоке данных.
    Первые `period` значений усредняются как SMA, затем применяется EMA.
    """

    def __init__(self, period: int):
        self.period = period
        self.k = 2 / (period + 1)
        self.value: float | None = None
        self.prev_value: float | None = None
        self._warmup: list[float] = []
        self._ready = False

    def update(self, price: float) -> float | None:
        self.prev_value = self.value

        if not self._ready:
            self._warmup.append(price)
            if len(self._warmup) >= self.period:
                self.value = sum(self._warmup) / len(self._warmup)
                self._ready = True
            return self.value

        self.value = price * self.k + self.value * (1 - self.k)
        return self.value

    def reset(self):
        self.value = None
        self.prev_value = None
        self._warmup = []
        self._ready = False


class VolumeFilter:
    """
    Определяет, является ли текущий объём выше среднего.
    Используется для фильтрации слабых сигналов.
    """

    def __init__(self, window: int = 20, multiplier: float = 1.2):
        self.window = window
        self.multiplier = multiplier
        self._buf: deque[int] = deque(maxlen=window)

    def push(self, volume: int):
        self._buf.append(volume)

    def average(self) -> float:
        if not self._buf:
            return 0.0
        return sum(self._buf) / len(self._buf)

    def is_above_avg(self, volume: int) -> bool:
        avg = self.average()
        self.push(volume)
        if avg == 0:
            return True  # недостаточно данных → разрешаем
        return volume >= avg * self.multiplier

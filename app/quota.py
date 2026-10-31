"""Дневная квота прогонов на клиента.

Ключ клиента — заголовок X-Client-Key, иначе IP. Лимит: RUNS_PER_DAY (по умолчанию 10).
In-memory: переживает перезапуск процесса не обязан, боевая квота — в БД на фазе 2.
"""

from __future__ import annotations

import os
import threading
import time


class Quota:
    def __init__(self, per_day: int | None = None) -> None:
        self.per_day = per_day or int(os.environ.get("RUNS_PER_DAY", "10"))
        self._lock = threading.Lock()
        self._hits: dict[str, tuple[int, int]] = {}  # key -> (day, count)

    @staticmethod
    def _today() -> int:
        return int(time.time() // 86400)

    def check(self, key: str) -> tuple[bool, int]:
        """Возвращает (разрешено, осталось). Увеличивает счётчик при разрешении."""
        with self._lock:
            day, count = self._hits.get(key, (self._today(), 0))
            if day != self._today():
                day, count = self._today(), 0
            if count >= self.per_day:
                self._hits[key] = (day, count)
                return False, 0
            count += 1
            self._hits[key] = (day, count)
            return True, self.per_day - count

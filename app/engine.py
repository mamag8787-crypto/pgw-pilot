"""Движки вызова модели.

По умолчанию — Codex CLI (`codex exec`), тот же бинарь и авторизация, что у
агентов Hermes (файл auth.json пользователя). Переменные окружения:

    CODEX_BIN     путь к бинарю (по умолчанию ищем в PATH)
    CODEX_ARGS    доп. аргументы через пробел, напр. "--skip-git-repo-check"
    CODEX_TIMEOUT секунды на один прогон (по умолчанию 120)
    MAX_OUTPUT    кап вывода в знаках (по умолчанию 20000)
    CONCURRENCY   одновременных прогонов (по умолчанию 2)

Требует Python 3.11+ (asyncio.timeout).
"""

from __future__ import annotations

import asyncio
import codecs
import os
import shutil
from typing import AsyncIterator


class EngineError(RuntimeError):
    """Движок не смог выполнить прогон."""


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, ""))
    except ValueError:
        return default


class CodexEngine:
    def __init__(
        self,
        bin_path: str | None = None,
        extra_args: list[str] | None = None,
        timeout: int | None = None,
        max_output: int | None = None,
        concurrency: int | None = None,
    ) -> None:
        env = os.environ
        self.bin = bin_path or env.get("CODEX_BIN") or shutil.which("codex") or "codex"
        self.extra_args = extra_args if extra_args is not None else env.get("CODEX_ARGS", "").split()
        self.timeout = timeout or _env_int("CODEX_TIMEOUT", 120)
        self.max_output = max_output or _env_int("MAX_OUTPUT", 20000)
        self._sem = asyncio.Semaphore(concurrency or _env_int("CONCURRENCY", 2))

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        """Выполняет прогон и стримит куски stdout по мере готовности.

        Промпт передаётся аргументом (не stdin): так он доезжает до модели
        байт-в-байт в UTF-8 независимо от локали. Вывод декодируется
        инкрементальным декодером, чтобы многобайтовые символы не резались
        по границам 256-байтовых чанков.
        """
        if not prompt.strip():
            raise EngineError("Пустой промпт")
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        async with self._sem:
            proc = await asyncio.create_subprocess_exec(
                self.bin, "exec", *self.extra_args, prompt,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                assert proc.stdout is not None
                produced = 0
                try:
                    async with asyncio.timeout(self.timeout):
                        while True:
                            chunk = await proc.stdout.read(256)
                            if not chunk:
                                break
                            text = decoder.decode(chunk)
                            produced += len(text)
                            yield text
                            if produced >= self.max_output:
                                break
                except TimeoutError:
                    raise EngineError(f"Таймаут прогона ({self.timeout} с)") from None
                tail = decoder.decode(b"", final=True)
                if tail:
                    yield tail

                rc = await proc.wait()
                if rc != 0:
                    stderr = b""
                    if proc.stderr is not None:
                        stderr = await proc.stderr.read()
                    detail = stderr.decode("utf-8", errors="replace")[-400:]
                    raise EngineError(f"codex exec завершился кодом {rc}: {detail}")
            finally:
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()

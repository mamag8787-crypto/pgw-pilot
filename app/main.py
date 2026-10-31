"""playground-gateway — шлюз рабочей области «Обкатка» портала.

Принимает промпты от портала (bearer-ключ), применяет квоту, выполняет через
Codex CLI и стримит ответ обратно. Каждый прогон пишется в SQLite.

Переменные окружения:
    GATEWAY_API_KEY  bearer-ключ, которым портал ходит в шлюз (обязателен в проде)
    HOST / PORT     интерфейс и порт (по умолчанию 127.0.0.1:8787)
    остальные — см. engine.py / quota.py / store.py
"""

from __future__ import annotations

import os
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .engine import CodexEngine, EngineError
from .quota import Quota
from .store import RunStore


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    material_id: str | None = None
    step_index: int | None = None


class State:
    def __init__(self) -> None:
        self.api_key = os.environ.get("GATEWAY_API_KEY", "")
        self.quota = Quota()
        self.store = RunStore()
        self.engine = CodexEngine()


state = State()
app = FastAPI(title="playground-gateway", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, **state.store.stats()}


def _unauthorized() -> JSONResponse:
    return JSONResponse({"error": "Некорректный ключ"}, status_code=401)


def _client_key(req: Request) -> str:
    return req.headers.get("X-Client-Key") or (req.client.host if req.client else "anon")


@app.post("/v1/chat", response_model=None)
async def chat(body: ChatRequest, req: Request):
    auth = req.headers.get("Authorization", "")
    if state.api_key:
        if auth != f"Bearer {state.api_key}":
            return _unauthorized()
    elif auth:  # ключ не задан — локальная отладка: пропускаем без проверки
        pass

    client = _client_key(req)
    allowed, left = state.quota.check(client)
    if not allowed:
        return JSONResponse(
            {"error": "Лимит прогонов на сегодня исчерпан"},
            status_code=429,
            headers={"X-Quota-Left": "0"},
        )

    async def generate() -> AsyncIterator[str]:
        output: list[str] = []
        try:
            async for chunk in state.engine.stream(body.prompt):
                output.append(chunk)
                yield chunk
        except EngineError as e:
            yield f"\n[ошибка движка: {e}]"
        finally:
            state.store.add(client, body.material_id, body.step_index, body.prompt, "".join(output))

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "X-Engine": "codex", "X-Quota-Left": str(left)},
    )


if __name__ == "__main__":  # локальный запуск: python -m app.main
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8787")),
    )

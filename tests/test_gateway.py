"""Тесты шлюза: auth, квота, streaming, логирование. Движок — фейк, codex не нужен."""

from __future__ import annotations

import os
import sys
from typing import AsyncIterator

import pytest
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app, state  # noqa: E402
from app.quota import Quota  # noqa: E402


class FakeEngine:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        self.calls.append(prompt)
        for piece in ["часть-1;", "часть-2;", "конец"]:
            yield piece


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "runs.sqlite"))
    monkeypatch.setenv("GATEWAY_API_KEY", "test-key")
    state.api_key = "test-key"
    state.quota = Quota(per_day=3)
    fake = FakeEngine()
    monkeypatch.setattr(state, "engine", fake)
    from app.store import RunStore

    monkeypatch.setattr(state, "store", RunStore(str(tmp_path / "runs.sqlite")))
    with TestClient(app) as c:
        c.fake_engine = fake  # type: ignore[attr-defined]
        yield c


def test_healthz(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_chat_streams_and_logs(client):
    res = client.post(
        "/v1/chat",
        json={"prompt": "привет [мир]", "material_id": "m1", "step_index": 2},
        headers={"Authorization": "Bearer test-key", "X-Client-Key": "fg-1"},
    )
    assert res.status_code == 200
    assert res.headers["X-Engine"] == "codex"
    assert res.text == "часть-1;часть-2;конец"
    stats = client.get("/healthz").json()
    assert stats["total"] == 1


def test_auth_required(client):
    res = client.post("/v1/chat", json={"prompt": "x"})
    assert res.status_code == 401
    res = client.post("/v1/chat", json={"prompt": "x"}, headers={"Authorization": "Bearer wrong"})
    assert res.status_code == 401


def test_quota_limit(client):
    headers = {"Authorization": "Bearer test-key", "X-Client-Key": "fg-2"}
    for i in range(3):
        assert client.post("/v1/chat", json={"prompt": f"q{i}"}, headers=headers).status_code == 200
    over = client.post("/v1/chat", json={"prompt": "q4"}, headers=headers)
    assert over.status_code == 429
    # другой клиент не затронут
    other = client.post(
        "/v1/chat", json={"prompt": "ok"}, headers={"Authorization": "Bearer test-key", "X-Client-Key": "fg-3"}
    )
    assert other.status_code == 200


def test_validation(client):
    headers = {"Authorization": "Bearer test-key"}
    assert client.post("/v1/chat", json={}, headers=headers).status_code == 422
    assert client.post("/v1/chat", json={"prompt": ""}, headers=headers).status_code == 422
    assert client.post("/v1/chat", json={"prompt": "y" * 9000}, headers=headers).status_code == 422

"""Tests for Assistant API endpoints — ask, history, error handling."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.models.assistant_history import AssistantHistory


class _FakeSessionCtx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        pass


def _mock_history_record(
    rid: int, question: str, answer: dict
) -> MagicMock:
    r = MagicMock(spec=AssistantHistory)
    r.id = rid
    r.question = question
    r.answer = json.dumps(answer, ensure_ascii=False)
    r.created_at = datetime(2026, 7, 19, 10, 0, 0)
    return r


# ── POST /assistant/ask ──────────────────────────────────────


@pytest.mark.anyio
async def test_assistant_ask_recommend():
    """POST /assistant/ask 推荐类问题。"""
    ask_result = {
        "answer": "推荐蓝牙耳机",
        "products": [{"name": "蓝牙耳机", "score": 95, "reason": ["增长趋势强"], "tags": []}],
        "insights": ["共推荐 1 个商品"],
    }

    mock_assistant = MagicMock()
    mock_assistant.ask = AsyncMock(return_value=ask_result)

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.assistant.get_async_session_factory", return_value=mock_factory),
        patch("app.api.assistant.SelectionAssistant", return_value=mock_assistant),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/assistant/ask", json={"question": "有什么爆款推荐"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "推荐蓝牙耳机"
    assert len(data["products"]) == 1
    assert data["products"][0]["name"] == "蓝牙耳机"
    assert "insights" in data


@pytest.mark.anyio
async def test_assistant_ask_trend():
    """POST /assistant/ask 趋势类问题。"""
    ask_result = {
        "answer": "发现 2 个上升趋势商品",
        "products": [
            {"name": "耳机", "score": 80, "reason": [], "tags": []},
            {"name": "音箱", "score": 75, "reason": [], "tags": []},
        ],
        "insights": ["趋势数据已更新"],
    }

    mock_assistant = MagicMock()
    mock_assistant.ask = AsyncMock(return_value=ask_result)

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.assistant.get_async_session_factory", return_value=mock_factory),
        patch("app.api.assistant.SelectionAssistant", return_value=mock_assistant),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/assistant/ask", json={"question": "趋势如何"})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["products"]) == 2


@pytest.mark.anyio
async def test_assistant_ask_error():
    """POST /assistant/ask 异常时返回 500。"""
    mock_assistant = MagicMock()
    mock_assistant.ask = AsyncMock(side_effect=RuntimeError("DB error"))

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.assistant.get_async_session_factory", return_value=mock_factory),
        patch("app.api.assistant.SelectionAssistant", return_value=mock_assistant),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/assistant/ask", json={"question": "测试"})

    assert resp.status_code == 500


# ── GET /assistant/history ───────────────────────────────────


@pytest.mark.anyio
async def test_assistant_history():
    """GET /assistant/history 返回问答历史。"""
    records = [
        _mock_history_record(1, "推荐什么", {"answer": "推荐蓝牙耳机", "products": [], "insights": []}),
        _mock_history_record(2, "趋势如何", {"answer": "趋势稳定", "products": [], "insights": []}),
    ]

    mock_repo = MagicMock()
    mock_repo.history = AsyncMock(return_value=records)

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.assistant.get_async_session_factory", return_value=mock_factory),
        patch("app.api.assistant.AssistantRepository", return_value=mock_repo),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/assistant/history")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["question"] == "推荐什么"
    assert data[0]["answer"]["answer"] == "推荐蓝牙耳机"
    assert "id" in data[0]
    assert "created_at" in data[0]


@pytest.mark.anyio
async def test_assistant_history_empty():
    """GET /assistant/history 无记录时返回空列表。"""
    mock_repo = MagicMock()
    mock_repo.history = AsyncMock(return_value=[])

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.assistant.get_async_session_factory", return_value=mock_factory),
        patch("app.api.assistant.AssistantRepository", return_value=mock_repo),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/assistant/history")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.anyio
async def test_assistant_history_error():
    """GET /assistant/history 异常时返回 500。"""
    mock_repo = MagicMock()
    mock_repo.history = AsyncMock(side_effect=RuntimeError("DB error"))

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.assistant.get_async_session_factory", return_value=mock_factory),
        patch("app.api.assistant.AssistantRepository", return_value=mock_repo),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/assistant/history")

    assert resp.status_code == 500

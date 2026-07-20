"""Tests for Knowledge API endpoints — tags, product, learn."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.models.product_tag import ProductTag


class _FakeSessionCtx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        pass


def _mock_tag(
    tid: int, name: str, tag_type: str, description: str = ""
) -> MagicMock:
    t = MagicMock(spec=ProductTag)
    t.id = tid
    t.name = name
    t.type = tag_type
    t.description = description
    t.created_at = datetime(2026, 7, 19, 10, 0, 0)
    return t


# ── GET /knowledge/tags ─────────────────────────────────────


@pytest.mark.anyio
async def test_knowledge_tags():
    """GET /knowledge/tags 返回标签列表。"""
    tags = [
        _mock_tag(1, "高速增长商品", "SUCCESS_PATTERN", "24小时销量增幅超过50%"),
        _mock_tag(2, "红海风险商品", "FAIL_PATTERN", "竞争激烈且销量下滑"),
    ]

    mock_repo = MagicMock()
    mock_repo.get_all_tags = AsyncMock(return_value=tags)

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.knowledge.get_async_session_factory", return_value=mock_factory),
        patch("app.api.knowledge.KnowledgeRepository", return_value=mock_repo),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/knowledge/tags")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] == "高速增长商品"
    assert data[0]["type"] == "SUCCESS_PATTERN"
    assert data[1]["name"] == "红海风险商品"
    assert "id" in data[0]
    assert "description" in data[0]
    assert "created_at" in data[0]


@pytest.mark.anyio
async def test_knowledge_tags_empty():
    """GET /knowledge/tags 无标签时返回空列表。"""
    mock_repo = MagicMock()
    mock_repo.get_all_tags = AsyncMock(return_value=[])

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.knowledge.get_async_session_factory", return_value=mock_factory),
        patch("app.api.knowledge.KnowledgeRepository", return_value=mock_repo),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/knowledge/tags")

    assert resp.status_code == 200
    assert resp.json() == []


# ── GET /knowledge/products/{id} ─────────────────────────────


@pytest.mark.anyio
async def test_knowledge_product():
    """GET /knowledge/products/{id} 返回商品标签。"""
    product_tags = [
        {"tag_id": 1, "name": "高速增长商品", "type": "SUCCESS_PATTERN", "confidence": 1.0, "source": "LEARNING"},
    ]

    mock_repo = MagicMock()
    mock_repo.get_product_tags = AsyncMock(return_value=product_tags)

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.knowledge.get_async_session_factory", return_value=mock_factory),
        patch("app.api.knowledge.KnowledgeRepository", return_value=mock_repo),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/knowledge/products/42")

    assert resp.status_code == 200
    data = resp.json()
    assert data["product_id"] == 42
    assert data["tag_count"] == 1
    assert data["tags"][0]["name"] == "高速增长商品"


@pytest.mark.anyio
async def test_knowledge_product_no_tags():
    """GET /knowledge/products/{id} 无标签时返回空。"""
    mock_repo = MagicMock()
    mock_repo.get_product_tags = AsyncMock(return_value=[])

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.knowledge.get_async_session_factory", return_value=mock_factory),
        patch("app.api.knowledge.KnowledgeRepository", return_value=mock_repo),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/knowledge/products/99")

    assert resp.status_code == 200
    data = resp.json()
    assert data["product_id"] == 99
    assert data["tag_count"] == 0
    assert data["tags"] == []


# ── POST /knowledge/learn ────────────────────────────────────


@pytest.mark.anyio
async def test_knowledge_learn():
    """POST /knowledge/learn 触发知识库学习。"""
    learn_result = {
        "processed": 5,
        "success_tags": 2,
        "fail_tags": 1,
        "bindings": 3,
    }

    mock_builder = MagicMock()
    mock_builder.learn_from_reviews = AsyncMock(return_value=learn_result)

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.knowledge.get_async_session_factory", return_value=mock_factory),
        patch("app.api.knowledge.KnowledgeBuilder", return_value=mock_builder),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/knowledge/learn")

    assert resp.status_code == 200
    data = resp.json()
    assert data["processed"] == 5
    assert data["success_tags"] == 2
    assert data["fail_tags"] == 1
    assert data["bindings"] == 3


@pytest.mark.anyio
async def test_knowledge_learn_error():
    """POST /knowledge/learn 异常时返回 500。"""
    mock_builder = MagicMock()
    mock_builder.learn_from_reviews = AsyncMock(side_effect=RuntimeError("DB error"))

    mock_session = MagicMock()
    mock_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

    with (
        patch("app.api.knowledge.get_async_session_factory", return_value=mock_factory),
        patch("app.api.knowledge.KnowledgeBuilder", return_value=mock_builder),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/knowledge/learn")

    assert resp.status_code == 500

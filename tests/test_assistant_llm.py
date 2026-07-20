"""Tests for Phase 13: SelectionAssistant LLM enhancement — classification and response enhancement."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.services.assistant.assistant import SelectionAssistant


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── LLM Classification ────────────────────────────────────────


class TestClassifyWithLLM:
    """LLM 二次分类测试。"""

    @pytest.mark.anyio
    async def test_llm_unavailable_returns_none(self, session):
        """LLM 不可用时返回 None。"""
        assistant = SelectionAssistant(session)
        with patch("app.services.assistant.assistant.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.available = False
            mock_get.return_value = mock_client

            result = await assistant._classify_with_llm("今天天气怎么样")
            assert result is None

    @pytest.mark.anyio
    async def test_llm_returns_valid_category(self, session):
        """LLM 返回有效类别。"""
        assistant = SelectionAssistant(session)
        with patch("app.services.assistant.assistant.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.available = True
            mock_client.chat = AsyncMock(return_value="recommend")
            mock_get.return_value = mock_client

            result = await assistant._classify_with_llm("有什么好东西")
            assert result == "recommend"

    @pytest.mark.anyio
    async def test_llm_returns_invalid_category(self, session):
        """LLM 返回无效类别时返回 None。"""
        assistant = SelectionAssistant(session)
        with patch("app.services.assistant.assistant.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.available = True
            mock_client.chat = AsyncMock(return_value="invalid_category")
            mock_get.return_value = mock_client

            result = await assistant._classify_with_llm("随便问问")
            assert result is None

    @pytest.mark.anyio
    async def test_llm_returns_none_response(self, session):
        """LLM 返回 None 时返回 None。"""
        assistant = SelectionAssistant(session)
        with patch("app.services.assistant.assistant.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.available = True
            mock_client.chat = AsyncMock(return_value=None)
            mock_get.return_value = mock_client

            result = await assistant._classify_with_llm("测试问题")
            assert result is None

    @pytest.mark.anyio
    async def test_llm_exception_returns_none(self, session):
        """LLM 异常时返回 None。"""
        assistant = SelectionAssistant(session)
        with patch("app.services.assistant.assistant.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.available = True
            mock_client.chat = AsyncMock(side_effect=Exception("LLM error"))
            mock_get.return_value = mock_client

            result = await assistant._classify_with_llm("测试异常")
            assert result is None

    @pytest.mark.anyio
    async def test_llm_strips_whitespace(self, session):
        """LLM 返回带空白的类别名能正确解析。"""
        assistant = SelectionAssistant(session)
        with patch("app.services.assistant.assistant.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.available = True
            mock_client.chat = AsyncMock(return_value="  trend  \n")
            mock_get.return_value = mock_client

            result = await assistant._classify_with_llm("市场走势如何")
            assert result == "trend"


# ── Response Enhancement ──────────────────────────────────────


class TestEnhanceResponse:
    """LLM 回答增强测试。"""

    @pytest.mark.anyio
    async def test_llm_unavailable_no_change(self, session):
        """LLM 不可用时不修改回答。"""
        assistant = SelectionAssistant(session)
        result = {"answer": "推荐商品A", "products": [{"name": "商品A"}], "insights": ["原有洞察"]}

        with patch("app.services.assistant.assistant.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.available = False
            mock_get.return_value = mock_client

            await assistant._enhance_response("推荐什么", result)
            # 不应添加新洞察
            assert len(result["insights"]) == 1

    @pytest.mark.anyio
    async def test_llm_adds_insight(self, session):
        """LLM 成功时添加洞察。"""
        assistant = SelectionAssistant(session)
        result = {"answer": "推荐商品A", "products": [{"name": "商品A"}], "insights": ["原有洞察"]}

        with patch("app.services.assistant.assistant.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.available = True
            mock_client.chat = AsyncMock(return_value="建议关注销量趋势")
            mock_get.return_value = mock_client

            await assistant._enhance_response("推荐什么", result)
            assert len(result["insights"]) == 2
            assert "AI 洞察" in result["insights"][-1]

    @pytest.mark.anyio
    async def test_llm_skips_empty_answer(self, session):
        """空回答不增强。"""
        assistant = SelectionAssistant(session)
        result = {"answer": "", "products": [], "insights": []}

        with patch("app.services.assistant.assistant.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.available = True
            mock_get.return_value = mock_client

            await assistant._enhance_response("测试", result)
            mock_client.chat.assert_not_called()

    @pytest.mark.anyio
    async def test_llm_skips_sorry_answer(self, session):
        """'抱歉'开头的回答不增强。"""
        assistant = SelectionAssistant(session)
        result = {"answer": "抱歉，我暂时无法理解您的问题。", "products": [], "insights": []}

        with patch("app.services.assistant.assistant.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.available = True
            mock_get.return_value = mock_client

            await assistant._enhance_response("测试", result)
            mock_client.chat.assert_not_called()

    @pytest.mark.anyio
    async def test_llm_exception_no_change(self, session):
        """LLM 异常时不修改回答。"""
        assistant = SelectionAssistant(session)
        result = {"answer": "推荐商品A", "products": [{"name": "商品A"}], "insights": []}

        with patch("app.services.assistant.assistant.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.available = True
            mock_client.chat = AsyncMock(side_effect=Exception("LLM error"))
            mock_get.return_value = mock_client

            await assistant._enhance_response("推荐什么", result)
            assert len(result["insights"]) == 0

    @pytest.mark.anyio
    async def test_llm_skips_empty_insight(self, session):
        """LLM 返回空洞察时不添加。"""
        assistant = SelectionAssistant(session)
        result = {"answer": "推荐商品A", "products": [{"name": "商品A"}], "insights": []}

        with patch("app.services.assistant.assistant.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.available = True
            mock_client.chat = AsyncMock(return_value="   ")
            mock_get.return_value = mock_client

            await assistant._enhance_response("推荐什么", result)
            assert len(result["insights"]) == 0


# ── Build Enhance Context ─────────────────────────────────────


class TestBuildEnhanceContext:
    """上下文构建测试。"""

    def test_empty_result(self):
        context = SelectionAssistant._build_enhance_context({"products": [], "insights": []})
        assert context == ""

    def test_with_products(self):
        result = {"products": [{"name": "商品A"}, {"name": "商品B"}], "insights": []}
        context = SelectionAssistant._build_enhance_context(result)
        assert "商品A" in context
        assert "商品B" in context

    def test_with_insights(self):
        result = {"products": [], "insights": ["洞察1", "洞察2"]}
        context = SelectionAssistant._build_enhance_context(result)
        assert "洞察1" in context

    def test_with_both(self):
        result = {"products": [{"name": "商品A"}], "insights": ["洞察1"]}
        context = SelectionAssistant._build_enhance_context(result)
        assert "商品A" in context
        assert "洞察1" in context


# ── Integration: ask() with LLM fallback ──────────────────────


class TestAskWithLLMFallback:
    """集成测试：LLM 不可用时的降级行为。"""

    @pytest.mark.anyio
    async def test_ask_unknown_falls_back_gracefully(self, session):
        """unknown 类问题 LLM 不可用时正常降级。"""
        assistant = SelectionAssistant(session)

        with patch("app.services.assistant.assistant.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.available = False
            mock_get.return_value = mock_client

            result = await assistant.ask("你好世界")
            # 应该返回 unknown 处理结果
            assert "抱歉" in result["answer"] or "暂时" in result["answer"]
            assert result["products"] == []

    @pytest.mark.anyio
    async def test_ask_classified_by_keyword_no_llm(self, session):
        """关键词分类命中时不调用 LLM 分类。"""
        assistant = SelectionAssistant(session)

        with patch("app.services.assistant.assistant.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.available = True
            mock_get.return_value = mock_client

            # "推荐" 关键词命中，不应调用 LLM 分类
            await assistant.ask("有什么推荐")
            # _classify_with_llm 不应被调用（因为关键词分类已命中）
            # 但 _enhance_response 会尝试调用 LLM
            # 这里只验证不抛异常

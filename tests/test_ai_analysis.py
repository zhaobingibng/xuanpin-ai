"""Tests for app.services.ai_analysis and app.api.ai_analysis."""

from __future__ import annotations

import json
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.models.daily_report import DailyReport, DailyReportItem
from app.models.product import Product
from app.services.ai_analysis.product_analyzer import LLMProductAnalyzer
from app.services.ai_analysis.report_summarizer import LLMReportSummarizer


# ── Helpers ───────────────────────────────────────────────────


def _mock_product(**kwargs) -> MagicMock:
    p = MagicMock(spec=Product)
    p.id = kwargs.get("id", 1)
    p.name = kwargs.get("name", "蓝牙耳机降噪")
    p.platform = kwargs.get("platform", "xiaohongshu")
    p.shop = kwargs.get("shop", "数码旗舰店")
    p.price = kwargs.get("price", 99.0)
    p.sales_24h = kwargs.get("sales_24h", 5000)
    p.viewers = kwargs.get("viewers", 20000)
    p.category = kwargs.get("category", "数码")
    p.lifecycle_stage = kwargs.get("lifecycle_stage", "HOT")
    p.ai_score = kwargs.get("ai_score", 85.0)
    p.image = kwargs.get("image", "")
    p.url = kwargs.get("url", "")
    return p


def _mock_report() -> MagicMock:
    report = MagicMock(spec=DailyReport)
    report.id = 1
    report.report_date = date(2026, 7, 21)
    report.total = 50
    report.hot_products = 5
    report.potential_products = 10
    report.average_score = 72.5

    item1 = MagicMock(spec=DailyReportItem)
    item1.rank = 1
    item1.name = "爆款蓝牙耳机"
    item1.platform = "xiaohongshu"
    item1.price = 99.0
    item1.score = 92
    item1.level = "爆款"
    item1.reasons = json.dumps(["销量高", "好评多"])
    item1.product_id = 1
    item1.image = ""

    item2 = MagicMock(spec=DailyReportItem)
    item2.rank = 2
    item2.name = "便携充电宝"
    item2.platform = "douyin"
    item2.price = 129.0
    item2.score = 85
    item2.level = "潜力"
    item2.reasons = json.dumps(["趋势上升"])
    item2.product_id = 2
    item2.image = ""

    report.items = [item1, item2]
    return report


def _mock_llm_client(available: bool = True) -> MagicMock:
    client = MagicMock()
    client.available = available
    client.model = "deepseek-chat"
    client.base_url = "https://api.deepseek.com"
    client.status.return_value = {
        "available": available,
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
    }
    return client


# ── LLMProductAnalyzer tests ─────────────────────────────────


class TestLLMProductAnalyzer:
    """Test the LLM product analysis service."""

    @pytest.mark.anyio
    async def test_analyze_returns_none_when_unavailable(self):
        mock_client = _mock_llm_client(available=False)
        with patch("app.services.ai_analysis.product_analyzer.get_llm_client", return_value=mock_client):
            analyzer = LLMProductAnalyzer()
            product = _mock_product()
            result = await analyzer.analyze(product)

        assert result is None

    @pytest.mark.anyio
    async def test_analyze_returns_result_on_success(self):
        llm_result = {
            "summary": "高需求爆款",
            "tags": ["高需求", "爆款"],
            "market_insight": "市场需求旺盛",
            "selling_points": ["降噪效果好", "性价比高"],
            "risks": ["竞争激烈"],
            "recommendation": "SELL",
            "confidence": 85,
        }
        mock_client = _mock_llm_client(available=True)
        mock_client.chat_json = AsyncMock(return_value=llm_result)

        with patch("app.services.ai_analysis.product_analyzer.get_llm_client", return_value=mock_client):
            analyzer = LLMProductAnalyzer()
            product = _mock_product()
            result = await analyzer.analyze(product)

        assert result is not None
        assert result["summary"] == "高需求爆款"
        assert result["recommendation"] == "SELL"
        assert result["confidence"] == 85
        assert "tags" in result

    @pytest.mark.anyio
    async def test_analyze_returns_none_on_llm_failure(self):
        mock_client = _mock_llm_client(available=True)
        mock_client.chat_json = AsyncMock(return_value=None)

        with patch("app.services.ai_analysis.product_analyzer.get_llm_client", return_value=mock_client):
            analyzer = LLMProductAnalyzer()
            product = _mock_product()
            result = await analyzer.analyze(product)

        assert result is None

    @pytest.mark.anyio
    async def test_analyze_validates_recommendation(self):
        llm_result = {
            "summary": "测试",
            "tags": ["test"],
            "recommendation": "invalid_action",
        }
        mock_client = _mock_llm_client(available=True)
        mock_client.chat_json = AsyncMock(return_value=llm_result)

        with patch("app.services.ai_analysis.product_analyzer.get_llm_client", return_value=mock_client):
            analyzer = LLMProductAnalyzer()
            result = await analyzer.analyze(_mock_product())

        assert result is not None
        assert result["recommendation"] == "WATCH"  # Invalid -> default to WATCH

    @pytest.mark.anyio
    async def test_analyze_returns_none_if_missing_required_fields(self):
        llm_result = {"some_field": "value"}  # Missing summary, tags, recommendation
        mock_client = _mock_llm_client(available=True)
        mock_client.chat_json = AsyncMock(return_value=llm_result)

        with patch("app.services.ai_analysis.product_analyzer.get_llm_client", return_value=mock_client):
            analyzer = LLMProductAnalyzer()
            result = await analyzer.analyze(_mock_product())

        assert result is None

    @pytest.mark.anyio
    async def test_analyze_batch_mixed_results(self):
        llm_result = {
            "summary": "好",
            "tags": ["good"],
            "recommendation": "SELL",
            "confidence": 80,
        }
        mock_client = _mock_llm_client(available=True)
        # First call succeeds, second fails
        mock_client.chat_json = AsyncMock(side_effect=[llm_result, None])

        with patch("app.services.ai_analysis.product_analyzer.get_llm_client", return_value=mock_client):
            analyzer = LLMProductAnalyzer()
            products = [_mock_product(id=1), _mock_product(id=2)]
            results = await analyzer.analyze_batch(products)

        assert len(results) == 2
        assert results[0] is not None
        assert results[0]["summary"] == "好"
        assert results[1] is None


# ── LLMReportSummarizer tests ────────────────────────────────


class TestLLMReportSummarizer:
    """Test the LLM report summarization service."""

    @pytest.mark.anyio
    async def test_summarize_returns_none_when_unavailable(self):
        mock_client = _mock_llm_client(available=False)
        with patch("app.services.ai_analysis.report_summarizer.get_llm_client", return_value=mock_client):
            summarizer = LLMReportSummarizer()
            report = _mock_report()
            result = await summarizer.summarize(report)

        assert result is None

    @pytest.mark.anyio
    async def test_summarize_returns_result_on_success(self):
        llm_result = {
            "summary": "今日共分析50个商品，发现5个爆款",
            "highlights": ["蓝牙耳机销量领先", "充电宝趋势上升"],
            "warnings": ["部分商品竞争加剧"],
            "action_items": ["重点推荐蓝牙耳机", "关注充电宝趋势"],
            "market_trend": "数码品类整体向好",
        }
        mock_client = _mock_llm_client(available=True)
        mock_client.chat_json = AsyncMock(return_value=llm_result)

        with patch("app.services.ai_analysis.report_summarizer.get_llm_client", return_value=mock_client):
            summarizer = LLMReportSummarizer()
            report = _mock_report()
            result = await summarizer.summarize(report)

        assert result is not None
        assert "summary" in result
        assert len(result["highlights"]) == 2
        assert len(result["action_items"]) == 2

    @pytest.mark.anyio
    async def test_summarize_returns_none_on_failure(self):
        mock_client = _mock_llm_client(available=True)
        mock_client.chat_json = AsyncMock(return_value=None)

        with patch("app.services.ai_analysis.report_summarizer.get_llm_client", return_value=mock_client):
            summarizer = LLMReportSummarizer()
            result = await summarizer.summarize(_mock_report())

        assert result is None

    @pytest.mark.anyio
    async def test_summarize_validates_required_fields(self):
        llm_result = {"unrelated_field": "value"}  # Missing summary
        mock_client = _mock_llm_client(available=True)
        mock_client.chat_json = AsyncMock(return_value=llm_result)

        with patch("app.services.ai_analysis.report_summarizer.get_llm_client", return_value=mock_client):
            summarizer = LLMReportSummarizer()
            result = await summarizer.summarize(_mock_report())

        assert result is None

    def test_build_top_items_text_empty(self):
        report = MagicMock(spec=DailyReport)
        report.items = []
        text = LLMReportSummarizer._build_top_items_text(report)
        assert text == "（无商品数据）"

    def test_build_top_items_text_with_data(self):
        report = _mock_report()
        text = LLMReportSummarizer._build_top_items_text(report)
        assert "爆款蓝牙耳机" in text
        assert "便携充电宝" in text
        assert "#1" in text
        assert "#2" in text


# ── API endpoint tests ────────────────────────────────────────


class TestAIAnalysisAPI:
    """Test the /api/ai-analysis endpoints."""

    @pytest.mark.anyio
    async def test_status_unavailable(self):
        mock_client = _mock_llm_client(available=False)
        with patch("app.api.ai_analysis.get_llm_client", return_value=mock_client):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/ai-analysis/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False
        assert data["reason"] == "no_api_key"

    @pytest.mark.anyio
    async def test_status_available(self):
        mock_client = _mock_llm_client(available=True)
        with patch("app.api.ai_analysis.get_llm_client", return_value=mock_client):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/ai-analysis/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert data["model"] == "deepseek-chat"

    @pytest.mark.anyio
    async def test_analyze_product_fallback(self):
        """When LLM is unavailable, should return fallback response."""
        mock_client = _mock_llm_client(available=False)

        mock_product = _mock_product(id=1, name="蓝牙耳机")

        # Mock the session and product query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_product

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock()
        mock_factory.return_value = mock_session

        with patch("app.services.ai_analysis.product_analyzer.get_llm_client", return_value=mock_client), \
             patch("app.api.ai_analysis.get_async_session_factory", return_value=mock_factory):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/ai-analysis/product/1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["fallback"] is True
        assert "error" in data

    @pytest.mark.anyio
    async def test_analyze_product_success(self):
        """When LLM is available, should return analysis."""
        llm_result = {
            "summary": "爆款",
            "tags": ["hot"],
            "market_insight": "需求旺盛",
            "selling_points": ["性价比高"],
            "risks": [],
            "recommendation": "SELL",
            "confidence": 90,
        }
        mock_client = _mock_llm_client(available=True)
        mock_client.chat_json = AsyncMock(return_value=llm_result)

        mock_product = _mock_product(id=1, name="蓝牙耳机")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_product

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock()
        mock_factory.return_value = mock_session

        with patch("app.services.ai_analysis.product_analyzer.get_llm_client", return_value=mock_client), \
             patch("app.api.ai_analysis.get_async_session_factory", return_value=mock_factory):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/ai-analysis/product/1")

        assert resp.status_code == 200
        data = resp.json()
        assert "llm_analysis" in data
        assert data["llm_analysis"]["summary"] == "爆款"
        assert data["llm_analysis"]["recommendation"] == "SELL"

    @pytest.mark.anyio
    async def test_analyze_product_not_found(self):
        """When product doesn't exist, should return 404."""
        mock_client = _mock_llm_client(available=True)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock()
        mock_factory.return_value = mock_session

        with patch("app.services.ai_analysis.product_analyzer.get_llm_client", return_value=mock_client), \
             patch("app.api.ai_analysis.get_async_session_factory", return_value=mock_factory):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/ai-analysis/product/9999")

        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_report_summary_not_found(self):
        """When report doesn't exist, should return 404."""
        mock_client = _mock_llm_client(available=True)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock()
        mock_factory.return_value = mock_session

        with patch("app.api.ai_analysis.get_llm_client", return_value=mock_client), \
             patch("app.api.ai_analysis.get_async_session_factory", return_value=mock_factory), \
             patch("app.api.ai_analysis.ReportRepository") as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo.get_report_detail = AsyncMock(return_value=None)
            mock_repo_cls.return_value = mock_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/ai-analysis/report/9999/summary")

        assert resp.status_code == 404

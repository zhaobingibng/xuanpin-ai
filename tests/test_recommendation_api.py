"""Tests for GET /products/recommendations endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeSessionCtx:
    async def __aenter__(self):
        return AsyncMock()

    async def __aexit__(self, *exc):
        return False


def _mock_factory():
    def factory():
        return _FakeSessionCtx()
    return factory


def _mock_product(pid: int, name: str) -> MagicMock:
    p = MagicMock()
    p.id = pid
    p.name = name
    p.platform = "xiaohongshu"
    p.price = 99.0
    p.sales_24h = 5000
    p.viewers = 10000
    p.image = ""
    return p


class TestRecommendationsNormal:
    """正常返回：有商品数据时。"""

    @pytest.mark.asyncio
    async def test_recommendations_returns_list(self):
        """GET /products/recommendations 应返回商品列表。"""
        products = [_mock_product(1, "爆款耳机")]
        with (
            patch("app.api.products.get_async_session_factory", return_value=_mock_factory()),
            patch("app.services.product_service.ProductService") as mock_ps_cls,
            patch("app.api.products.ProductScorer") as mock_scorer_cls,
            patch("app.api.products.LifecycleAnalyzer") as mock_lc_cls,
            patch("app.api.products.ProductDecisionEngine") as mock_de_cls,
            patch("app.api.products.HistoryRepository") as mock_hr_cls,
        ):
            # ProductService mock
            mock_ps = AsyncMock()
            mock_ps.list_all.return_value = products
            mock_ps_cls.return_value = mock_ps

            # HistoryRepository mock
            mock_hr = AsyncMock()
            mock_hr.get_history.return_value = []
            mock_hr_cls.return_value = mock_hr

            # ProductScorer mock
            mock_scorer = MagicMock()
            mock_scorer.calculate_score.return_value = {
                "score": 95, "level": "爆款", "reasons": ["高销量"],
            }
            mock_scorer_cls.return_value = mock_scorer

            # LifecycleAnalyzer mock
            mock_lc = AsyncMock()
            mock_lc.analyze.return_value = {
                "product_id": 1, "stage": "HOT", "score": 90, "signals": [],
            }
            mock_lc_cls.return_value = mock_lc

            # ProductDecisionEngine mock
            mock_de = MagicMock()
            mock_de.decide.return_value = {
                "action": "SELL", "confidence": 95, "reason": ["高评分", "爆款阶段"],
            }
            mock_de_cls.return_value = mock_de

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/products/recommendations")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "爆款耳机"
        assert data[0]["action"] == "SELL"
        assert data[0]["confidence"] == 95

    @pytest.mark.asyncio
    async def test_recommendations_sorted_by_confidence(self):
        """返回结果应按 confidence 降序排列。"""
        products = [
            _mock_product(1, "商品A"),
            _mock_product(2, "商品B"),
        ]
        call_count = 0

        def mock_decide(product, score, lifecycle):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"action": "WATCH", "confidence": 50, "reason": ["观察"]}
            return {"action": "SELL", "confidence": 95, "reason": ["推荐"]}

        with (
            patch("app.api.products.get_async_session_factory", return_value=_mock_factory()),
            patch("app.services.product_service.ProductService") as mock_ps_cls,
            patch("app.api.products.ProductScorer") as mock_scorer_cls,
            patch("app.api.products.LifecycleAnalyzer") as mock_lc_cls,
            patch("app.api.products.ProductDecisionEngine") as mock_de_cls,
            patch("app.api.products.HistoryRepository") as mock_hr_cls,
        ):
            mock_ps = AsyncMock()
            mock_ps.list_all.return_value = products
            mock_ps_cls.return_value = mock_ps

            mock_hr = AsyncMock()
            mock_hr.get_history.return_value = []
            mock_hr_cls.return_value = mock_hr

            mock_scorer = MagicMock()
            mock_scorer.calculate_score.return_value = {
                "score": 80, "level": "潜力", "reasons": [],
            }
            mock_scorer_cls.return_value = mock_scorer

            mock_lc = AsyncMock()
            mock_lc.analyze.return_value = {
                "product_id": 1, "stage": "HOT", "score": 80, "signals": [],
            }
            mock_lc_cls.return_value = mock_lc

            mock_de = MagicMock()
            mock_de.decide.side_effect = mock_decide
            mock_de_cls.return_value = mock_de

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/products/recommendations")

        data = resp.json()
        assert data[0]["confidence"] >= data[1]["confidence"]


class TestRecommendationsEmpty:
    """空数据：无商品时返回空列表。"""

    @pytest.mark.asyncio
    async def test_recommendations_empty(self):
        with (
            patch("app.api.products.get_async_session_factory", return_value=_mock_factory()),
            patch("app.services.product_service.ProductService") as mock_ps_cls,
            patch("app.api.products.ProductScorer") as mock_scorer_cls,
            patch("app.api.products.LifecycleAnalyzer") as mock_lc_cls,
            patch("app.api.products.ProductDecisionEngine") as mock_de_cls,
            patch("app.api.products.HistoryRepository") as mock_hr_cls,
        ):
            mock_ps = AsyncMock()
            mock_ps.list_all.return_value = []
            mock_ps_cls.return_value = mock_ps

            mock_hr = AsyncMock()
            mock_hr_cls.return_value = mock_hr

            mock_scorer = MagicMock()
            mock_scorer_cls.return_value = mock_scorer

            mock_lc = AsyncMock()
            mock_lc_cls.return_value = mock_lc

            mock_de = MagicMock()
            mock_de_cls.return_value = mock_de

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/products/recommendations")

        assert resp.status_code == 200
        assert resp.json() == []


class TestRecommendationsFields:
    """字段完整性验证。"""

    @pytest.mark.asyncio
    async def test_recommendation_fields(self):
        """每条推荐应包含 name/score/lifecycle/action/confidence/reasons。"""
        products = [_mock_product(1, "爆款耳机")]
        with (
            patch("app.api.products.get_async_session_factory", return_value=_mock_factory()),
            patch("app.services.product_service.ProductService") as mock_ps_cls,
            patch("app.api.products.ProductScorer") as mock_scorer_cls,
            patch("app.api.products.LifecycleAnalyzer") as mock_lc_cls,
            patch("app.api.products.ProductDecisionEngine") as mock_de_cls,
            patch("app.api.products.HistoryRepository") as mock_hr_cls,
        ):
            mock_ps = AsyncMock()
            mock_ps.list_all.return_value = products
            mock_ps_cls.return_value = mock_ps

            mock_hr = AsyncMock()
            mock_hr.get_history.return_value = []
            mock_hr_cls.return_value = mock_hr

            mock_scorer = MagicMock()
            mock_scorer.calculate_score.return_value = {
                "score": 95, "level": "爆款", "reasons": ["高销量"],
            }
            mock_scorer_cls.return_value = mock_scorer

            mock_lc = AsyncMock()
            mock_lc.analyze.return_value = {
                "product_id": 1, "stage": "HOT", "score": 90, "signals": [],
            }
            mock_lc_cls.return_value = mock_lc

            mock_de = MagicMock()
            mock_de.decide.return_value = {
                "action": "SELL", "confidence": 95, "reason": ["高评分", "爆款阶段"],
            }
            mock_de_cls.return_value = mock_de

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/products/recommendations")

        data = resp.json()
        expected_keys = {"name", "score", "lifecycle", "action", "confidence", "reasons"}
        assert set(data[0].keys()) == expected_keys

    @pytest.mark.asyncio
    async def test_recommendation_error_returns_500(self):
        """服务异常时返回 500。"""
        with (
            patch("app.api.products.get_async_session_factory", return_value=_mock_factory()),
            patch("app.services.product_service.ProductService") as mock_ps_cls,
        ):
            mock_ps = AsyncMock()
            mock_ps.list_all.side_effect = RuntimeError("db error")
            mock_ps_cls.return_value = mock_ps

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/products/recommendations")

        assert resp.status_code == 500
        assert resp.json()["detail"] == "获取推荐商品失败"


# ── /recommendations/today ───────────────────────────────────


class TestRecommendationsToday:
    """GET /recommendations/today 接口。"""

    @pytest.mark.asyncio
    async def test_today_returns_list(self):
        """应返回排序后的推荐列表。"""
        products = [_mock_product(1, "爆款耳机")]
        with (
            patch("app.api.recommendations.get_async_session_factory", return_value=_mock_factory()),
            patch("app.services.product_service.ProductService") as mock_ps_cls,
            patch("app.api.recommendations.ProductScorer") as mock_scorer_cls,
            patch("app.api.recommendations.LifecycleAnalyzer") as mock_lc_cls,
            patch("app.api.recommendations.ProductDecisionEngine") as mock_de_cls,
            patch("app.api.recommendations.HistoryRepository") as mock_hr_cls,
            patch("app.api.recommendations.RecommendationRanker") as mock_ranker_cls,
        ):
            mock_ps = AsyncMock()
            mock_ps.list_all.return_value = products
            mock_ps_cls.return_value = mock_ps

            mock_hr = AsyncMock()
            mock_hr.get_history.return_value = []
            mock_hr_cls.return_value = mock_hr

            mock_scorer = MagicMock()
            mock_scorer.calculate_score.return_value = {
                "score": 95, "level": "爆款", "reasons": ["高销量"],
            }
            mock_scorer_cls.return_value = mock_scorer

            mock_lc = AsyncMock()
            mock_lc.analyze.return_value = {
                "product_id": 1, "stage": "HOT", "score": 90, "signals": [],
            }
            mock_lc_cls.return_value = mock_lc

            mock_de = MagicMock()
            mock_de.decide.return_value = {
                "action": "SELL", "confidence": 95, "reason": ["高评分"],
            }
            mock_de_cls.return_value = mock_de

            mock_ranker = MagicMock()
            mock_ranker.rank.return_value = [
                {
                    "rank": 1, "product_id": 1, "name": "爆款耳机",
                    "platform": "xiaohongshu", "image": "", "price": 99.0,
                    "recommend_score": 97.5, "score": 95,
                    "lifecycle": "HOT", "action": "SELL",
                    "confidence": 95, "reasons": ["高评分"],
                },
            ]
            mock_ranker_cls.return_value = mock_ranker

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/recommendations/today")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["rank"] == 1
        assert data[0]["recommend_score"] == 97.5

    @pytest.mark.asyncio
    async def test_today_sorting_correct(self):
        """ranker 返回的顺序即为最终顺序。"""
        products = [_mock_product(1, "A"), _mock_product(2, "B")]
        with (
            patch("app.api.recommendations.get_async_session_factory", return_value=_mock_factory()),
            patch("app.services.product_service.ProductService") as mock_ps_cls,
            patch("app.api.recommendations.ProductScorer") as mock_scorer_cls,
            patch("app.api.recommendations.LifecycleAnalyzer") as mock_lc_cls,
            patch("app.api.recommendations.ProductDecisionEngine") as mock_de_cls,
            patch("app.api.recommendations.HistoryRepository") as mock_hr_cls,
            patch("app.api.recommendations.RecommendationRanker") as mock_ranker_cls,
        ):
            mock_ps = AsyncMock()
            mock_ps.list_all.return_value = products
            mock_ps_cls.return_value = mock_ps

            mock_hr = AsyncMock()
            mock_hr.get_history.return_value = []
            mock_hr_cls.return_value = mock_hr

            mock_scorer = MagicMock()
            mock_scorer.calculate_score.return_value = {
                "score": 80, "level": "潜力", "reasons": [],
            }
            mock_scorer_cls.return_value = mock_scorer

            mock_lc = AsyncMock()
            mock_lc.analyze.return_value = {
                "product_id": 1, "stage": "RISING", "score": 80, "signals": [],
            }
            mock_lc_cls.return_value = mock_lc

            mock_de = MagicMock()
            mock_de.decide.return_value = {
                "action": "TEST", "confidence": 80, "reason": ["测试"],
            }
            mock_de_cls.return_value = mock_de

            mock_ranker = MagicMock()
            mock_ranker.rank.return_value = [
                {
                    "rank": 1, "product_id": 2, "name": "B",
                    "platform": "", "image": "", "price": 99.0,
                    "recommend_score": 85.0, "score": 80,
                    "lifecycle": "RISING", "action": "TEST",
                    "confidence": 80, "reasons": ["测试"],
                },
                {
                    "rank": 2, "product_id": 1, "name": "A",
                    "platform": "", "image": "", "price": 99.0,
                    "recommend_score": 75.0, "score": 80,
                    "lifecycle": "RISING", "action": "TEST",
                    "confidence": 80, "reasons": ["测试"],
                },
            ]
            mock_ranker_cls.return_value = mock_ranker

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/recommendations/today")

        data = resp.json()
        assert data[0]["rank"] == 1
        assert data[0]["recommend_score"] >= data[1]["recommend_score"]

    @pytest.mark.asyncio
    async def test_today_empty(self):
        """无商品时返回空列表。"""
        with (
            patch("app.api.recommendations.get_async_session_factory", return_value=_mock_factory()),
            patch("app.services.product_service.ProductService") as mock_ps_cls,
            patch("app.api.recommendations.ProductScorer") as mock_scorer_cls,
            patch("app.api.recommendations.LifecycleAnalyzer") as mock_lc_cls,
            patch("app.api.recommendations.ProductDecisionEngine") as mock_de_cls,
            patch("app.api.recommendations.HistoryRepository") as mock_hr_cls,
            patch("app.api.recommendations.RecommendationRanker") as mock_ranker_cls,
        ):
            mock_ps = AsyncMock()
            mock_ps.list_all.return_value = []
            mock_ps_cls.return_value = mock_ps

            mock_hr = AsyncMock()
            mock_hr_cls.return_value = mock_hr

            mock_scorer = MagicMock()
            mock_scorer_cls.return_value = mock_scorer

            mock_lc = AsyncMock()
            mock_lc_cls.return_value = mock_lc

            mock_de = MagicMock()
            mock_de_cls.return_value = mock_de

            mock_ranker = MagicMock()
            mock_ranker.rank.return_value = []
            mock_ranker_cls.return_value = mock_ranker

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/recommendations/today")

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_today_error_returns_500(self):
        """服务异常时返回 500。"""
        with (
            patch("app.api.recommendations.get_async_session_factory", return_value=_mock_factory()),
            patch("app.services.product_service.ProductService") as mock_ps_cls,
        ):
            mock_ps = AsyncMock()
            mock_ps.list_all.side_effect = RuntimeError("db error")
            mock_ps_cls.return_value = mock_ps

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/recommendations/today")

        assert resp.status_code == 500
        assert resp.json()["detail"] == "获取今日推荐失败"

    @pytest.mark.asyncio
    async def test_today_fields(self):
        """字段完整性验证。"""
        products = [_mock_product(1, "爆款耳机")]
        with (
            patch("app.api.recommendations.get_async_session_factory", return_value=_mock_factory()),
            patch("app.services.product_service.ProductService") as mock_ps_cls,
            patch("app.api.recommendations.ProductScorer") as mock_scorer_cls,
            patch("app.api.recommendations.LifecycleAnalyzer") as mock_lc_cls,
            patch("app.api.recommendations.ProductDecisionEngine") as mock_de_cls,
            patch("app.api.recommendations.HistoryRepository") as mock_hr_cls,
            patch("app.api.recommendations.RecommendationRanker") as mock_ranker_cls,
        ):
            mock_ps = AsyncMock()
            mock_ps.list_all.return_value = products
            mock_ps_cls.return_value = mock_ps

            mock_hr = AsyncMock()
            mock_hr.get_history.return_value = []
            mock_hr_cls.return_value = mock_hr

            mock_scorer = MagicMock()
            mock_scorer.calculate_score.return_value = {
                "score": 95, "level": "爆款", "reasons": ["高销量"],
            }
            mock_scorer_cls.return_value = mock_scorer

            mock_lc = AsyncMock()
            mock_lc.analyze.return_value = {
                "product_id": 1, "stage": "HOT", "score": 90, "signals": [],
            }
            mock_lc_cls.return_value = mock_lc

            mock_de = MagicMock()
            mock_de.decide.return_value = {
                "action": "SELL", "confidence": 95, "reason": ["高评分"],
            }
            mock_de_cls.return_value = mock_de

            mock_ranker = MagicMock()
            mock_ranker.rank.return_value = [
                {
                    "rank": 1, "product_id": 1, "name": "爆款耳机",
                    "platform": "xiaohongshu", "image": "img.jpg", "price": 99.0,
                    "recommend_score": 97.5, "score": 95,
                    "lifecycle": "HOT", "action": "SELL",
                    "confidence": 95, "reasons": ["高评分"],
                },
            ]
            mock_ranker_cls.return_value = mock_ranker

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/recommendations/today")

        data = resp.json()
        expected_keys = {
            "rank", "product_id", "name", "image", "price",
            "recommend_score", "score", "lifecycle", "action", "confidence", "reasons",
        }
        assert set(data[0].keys()) == expected_keys

"""Tests for DailyRecommendationService — full pipeline, sorting, dedup, empty, errors."""

from __future__ import annotations

from contextlib import ExitStack
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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


def _patch_all(
    products: list,
    history: list | None = None,
    score_result: dict | None = None,
    lifecycle_result: dict | None = None,
    decision_result: dict | None = None,
    trend_score: float = 60.0,
    competition_result: dict | None = None,
):
    """Create all patches for DailyRecommendationService testing."""
    _history = history if history is not None else []
    _score = score_result or {"score": 80, "level": "潜力", "reasons": ["好"]}
    _lifecycle = lifecycle_result or {"product_id": 1, "stage": "NEW", "score": 60, "signals": []}
    _decision = decision_result or {"action": "TEST", "confidence": 80, "reason": ["测试"]}
    _competition = competition_result or {
        "product_id": 1,
        "competition_score": 80,
        "market_level": "LOW",
        "signals": ["竞争商品较少"],
    }

    mock_ps = AsyncMock()
    mock_ps.list_all.return_value = products

    mock_hr = AsyncMock()
    mock_hr.get_history.return_value = _history

    mock_scorer = MagicMock()
    mock_scorer.calculate_score.return_value = _score

    mock_lc = AsyncMock()
    mock_lc.analyze.return_value = _lifecycle

    mock_comp = AsyncMock()
    mock_comp.analyze.return_value = _competition

    mock_de = MagicMock()
    mock_de.decide.return_value = _decision

    mock_rec_repo = AsyncMock()

    mock_knowledge_repo = AsyncMock()
    mock_knowledge_repo.get_product_tags.return_value = []

    mock_trend = MagicMock()
    mock_trend_instance = MagicMock()
    mock_trend_instance.calculate_trend_score.return_value = {"trend_score": trend_score}
    mock_trend.return_value = mock_trend_instance

    patches = [
        patch(
            "app.services.recommendation.daily_recommendation.ProductService",
            return_value=mock_ps,
        ),
        patch(
            "app.services.recommendation.daily_recommendation.HistoryRepository",
            return_value=mock_hr,
        ),
        patch(
            "app.services.recommendation.daily_recommendation.ProductScorer",
            return_value=mock_scorer,
        ),
        patch(
            "app.services.recommendation.daily_recommendation.LifecycleAnalyzer",
            return_value=mock_lc,
        ),
        patch(
            "app.services.recommendation.daily_recommendation.CompetitionAnalyzer",
            return_value=mock_comp,
        ),
        patch(
            "app.services.recommendation.daily_recommendation.ProductDecisionEngine",
            return_value=mock_de,
        ),
        patch(
            "app.services.recommendation.daily_recommendation.RecommendationRepository",
            return_value=mock_rec_repo,
        ),
        patch(
            "app.services.recommendation.daily_recommendation.KnowledgeRepository",
            return_value=mock_knowledge_repo,
        ),
        patch(
            "app.services.recommendation.daily_recommendation.TrendAnalyzer",
            mock_trend,
        ),
    ]
    return patches, mock_ps, mock_hr, mock_scorer, mock_lc, mock_de, mock_rec_repo


def _apply_patches(patches):
    """Start all patches and return an ExitStack for cleanup."""
    stack = ExitStack()
    for p in patches:
        stack.enter_context(p)
    return stack


# ── Full pipeline ────────────────────────────────────────────


class TestFullPipeline:
    """完整生成流程。"""

    @pytest.mark.anyio
    async def test_generate_returns_correct_structure(self):
        """generate() 返回包含 date/total/items 的字典。"""
        products = [_mock_product(1, "商品A")]
        patches, *_ = _patch_all(products)

        from app.services.recommendation.daily_recommendation import (
            DailyRecommendationService,
        )

        with _apply_patches(patches):
            svc = DailyRecommendationService(MagicMock())
            result = await svc.generate()

        assert "date" in result
        assert result["date"] == date.today().isoformat()
        assert "total" in result
        assert isinstance(result["items"], list)

    @pytest.mark.anyio
    async def test_generate_items_have_status(self):
        """每个推荐 item 应有 status=ACTIVE。"""
        products = [_mock_product(1, "商品A"), _mock_product(2, "商品B")]
        patches, *_ = _patch_all(products)

        from app.services.recommendation.daily_recommendation import (
            DailyRecommendationService,
        )

        with _apply_patches(patches):
            svc = DailyRecommendationService(MagicMock())
            result = await svc.generate()

        for item in result["items"]:
            assert item["status"] == "ACTIVE"

    @pytest.mark.anyio
    async def test_generate_saves_to_repository(self):
        """generate() 应调用 RecommendationRepository 保存结果。"""
        products = [_mock_product(1, "商品A")]
        patches, _, _, _, _, _, mock_rec_repo = _patch_all(products)

        from app.services.recommendation.daily_recommendation import (
            DailyRecommendationService,
        )

        with _apply_patches(patches):
            svc = DailyRecommendationService(MagicMock())
            await svc.generate()

        mock_rec_repo.save_daily_recommendations.assert_awaited_once()


# ── Sorting ──────────────────────────────────────────────────


class TestSorting:
    """排序正确。"""

    @pytest.mark.anyio
    async def test_ranked_output_has_ranks(self):
        """排序后的 items 应有递增的 rank。"""
        products = [
            _mock_product(1, "A"),
            _mock_product(2, "B"),
            _mock_product(3, "C"),
        ]
        patches, *_ = _patch_all(products)

        from app.services.recommendation.daily_recommendation import (
            DailyRecommendationService,
        )

        with _apply_patches(patches):
            svc = DailyRecommendationService(MagicMock())
            result = await svc.generate()

        ranks = [item["rank"] for item in result["items"]]
        assert ranks == sorted(ranks)
        assert ranks[0] == 1


# ── Duplicate generation ─────────────────────────────────────


class TestDuplicateGeneration:
    """重复生成：同一天多次调用不报错。"""

    @pytest.mark.anyio
    async def test_generate_twice_no_error(self):
        """两次 generate() 应都成功。"""
        products = [_mock_product(1, "商品A")]
        patches, _, _, _, _, _, mock_rec_repo = _patch_all(products)

        from app.services.recommendation.daily_recommendation import (
            DailyRecommendationService,
        )

        with _apply_patches(patches):
            svc = DailyRecommendationService(MagicMock())
            r1 = await svc.generate()
            r2 = await svc.generate()

        assert r1["total"] == r2["total"]
        assert mock_rec_repo.save_daily_recommendations.await_count == 2


# ── Empty products ───────────────────────────────────────────


class TestEmptyProducts:
    """空商品处理。"""

    @pytest.mark.anyio
    async def test_empty_products(self):
        """无商品时返回空列表。"""
        patches, *_ = _patch_all([])

        from app.services.recommendation.daily_recommendation import (
            DailyRecommendationService,
        )

        with _apply_patches(patches):
            svc = DailyRecommendationService(MagicMock())
            result = await svc.generate()

        assert result["total"] == 0
        assert result["items"] == []


# ── Error handling ───────────────────────────────────────────


class TestErrorHandling:
    """异常处理。"""

    @pytest.mark.anyio
    async def test_save_error_does_not_crash(self):
        """保存失败时 generate() 仍正常返回。"""
        products = [_mock_product(1, "商品A")]
        patches, _, _, _, _, _, mock_rec_repo = _patch_all(products)
        mock_rec_repo.save_daily_recommendations.side_effect = RuntimeError("db error")

        from app.services.recommendation.daily_recommendation import (
            DailyRecommendationService,
        )

        with _apply_patches(patches):
            svc = DailyRecommendationService(MagicMock())
            result = await svc.generate()

        assert result["total"] >= 1


# ── Save result ──────────────────────────────────────────────


class TestSaveResult:
    """保存结果验证。"""

    @pytest.mark.anyio
    async def test_save_called_with_ranked_items(self):
        """保存时应传入排序后的 items。"""
        products = [_mock_product(1, "商品A")]
        patches, _, _, _, _, _, mock_rec_repo = _patch_all(products)

        from app.services.recommendation.daily_recommendation import (
            DailyRecommendationService,
        )

        with _apply_patches(patches):
            svc = DailyRecommendationService(MagicMock())
            await svc.generate()

        saved_items = mock_rec_repo.save_daily_recommendations.call_args[0][0]
        assert len(saved_items) == 1
        assert saved_items[0]["status"] == "ACTIVE"
        assert "rank" in saved_items[0]
        assert "recommend_score" in saved_items[0]

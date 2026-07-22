"""Tests for Phase 37.1: DailySelectionPipeline orchestration layer.

Covers:
- 正常完整流程 (end-to-end happy path)
- 空商品列表 (empty candidate list)
- 无供应商匹配 (products without any supplier matches)
- 爬虫异常 (product acquisition failure → error result)
- 匹配异常 (per-product matching failure is isolated)
- 报告生成异常 (report generation failure → error result)
- TaskExecution 记录 (RUNNING → SUCCESS / FAILED tracking)
- 多次运行隔离 (statelessness across multiple runs)

All dependencies are injected as mocks — no real DB required.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.product import Product
from app.models.supplier_match import SupplierMatch
from app.services.selection.daily_selection_pipeline import (
    DailySelectionPipeline,
    TASK_NAME,
)


# ── Helpers ──────────────────────────────────────────────────


def _make_product(
    pid: int = 1,
    name: str = "三只松鼠坚果礼盒装",
    price: float = 99.0,
    viewers: int = 1000,
    sales_24h: int = 50,
) -> Product:
    return Product(
        id=pid,
        name=name,
        platform="taobao",
        shop="旗舰店",
        price=price,
        viewers=viewers,
        sales_24h=sales_24h,
        first_seen_time=datetime.now(),
    )


def _make_supplier_match(
    product_id: int = 1,
    supplier_product_id: int = 100,
    supplier_title: str = "坚果礼盒装 厂家直销",
    supplier_price: float = 50.0,
    similarity_score: float = 0.9,
    profit_margin: float = 49.0,
    estimated_profit: float = 49.0,
    rank: int = 1,
) -> SupplierMatch:
    return SupplierMatch(
        product_id=product_id,
        supplier_product_id=supplier_product_id,
        supplier_title=supplier_title,
        supplier_url="https://1688.com/offer/1",
        supplier_price=supplier_price,
        similarity_score=similarity_score,
        text_score=0.85,
        feature_score=0.4,
        rank=rank,
        estimated_profit=estimated_profit,
        profit_margin=profit_margin,
    )


def _make_product_service(products: list) -> MagicMock:
    """Build a mock product service with async list_all."""
    svc = MagicMock()
    svc.list_all = AsyncMock(return_value=products)
    return svc


def _make_matching_service(
    matches_by_call: list | None = None,
    side_effect=None,
) -> MagicMock:
    """Build a mock matching service.

    Args:
        matches_by_call: default return value (same for every product).
        side_effect: optional side_effect (e.g. exception or per-call list).
    """
    svc = MagicMock()
    if side_effect is not None:
        svc.match_products_with_matcher = AsyncMock(side_effect=side_effect)
    else:
        svc.match_products_with_matcher = AsyncMock(
            return_value=matches_by_call or [],
        )
    return svc


def _make_task_repo() -> MagicMock:
    """Build a mock TaskExecution repo. create() returns a record with id."""
    repo = MagicMock()

    async def _create(record):
        # Simulate DB assigning an id.
        record.id = 4242
        return record

    repo.create = AsyncMock(side_effect=_create)
    repo.finish = AsyncMock(return_value=None)
    return repo


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock(return_value=None)
    return session


def _build_pipeline(
    products: list,
    matches=None,
    matching_side_effect=None,
    task_repo: MagicMock | None = None,
    scorer=None,
    report_generator=None,
) -> tuple[DailySelectionPipeline, MagicMock]:
    """Convenience builder returning (pipeline, task_repo)."""
    repo = task_repo or _make_task_repo()
    pipeline = DailySelectionPipeline(
        product_service=_make_product_service(products),
        matching_service=_make_matching_service(
            matches_by_call=matches, side_effect=matching_side_effect,
        ),
        scorer=scorer,
        report_generator=report_generator,
        task_repo=repo,
    )
    return pipeline, repo


# ═══════════════════════════════════════════════════════════════
# 正常完整流程
# ═══════════════════════════════════════════════════════════════


class TestHappyPath:
    """End-to-end happy path."""

    @pytest.mark.asyncio
    async def test_full_flow_success(self):
        products = [_make_product(1), _make_product(2, "机械键盘")]
        matches = [_make_supplier_match(1)]
        pipeline, _ = _build_pipeline(products, matches=matches)
        session = _make_session()

        result = await pipeline.run(session, limit=20, top_k=3)

        assert result["status"] == "success"
        assert result["task"] == TASK_NAME
        assert result["report"] is not None
        assert "top_products" in result["report"]

    @pytest.mark.asyncio
    async def test_stats_populated(self):
        products = [_make_product(1), _make_product(2, "机械键盘")]
        matches = [_make_supplier_match(1)]
        pipeline, _ = _build_pipeline(products, matches=matches)
        session = _make_session()

        result = await pipeline.run(session)

        stats = result["stats"]
        assert stats["total_products"] == 2
        # Each product returns the same one match (mock), so both matched.
        assert stats["matched_products"] == 2
        assert stats["total_matches"] == 2
        assert stats["match_errors"] == 0
        assert stats["duration"] >= 0.0

    @pytest.mark.asyncio
    async def test_matching_called_per_product(self):
        products = [_make_product(1), _make_product(2), _make_product(3)]
        pipeline, _ = _build_pipeline(products, matches=[_make_supplier_match(1)])
        session = _make_session()

        await pipeline.run(session, top_k=5)

        matching = pipeline._matching_service.match_products_with_matcher
        assert matching.await_count == 3
        # top_k propagated
        _, kwargs = matching.await_args
        assert kwargs.get("top_k") == 5

    @pytest.mark.asyncio
    async def test_report_contains_scored_products(self):
        products = [_make_product(1, price=200.0, viewers=8000, sales_24h=600)]
        matches = [
            _make_supplier_match(
                1, supplier_price=60.0, similarity_score=0.95, profit_margin=70.0,
            )
        ]
        pipeline, _ = _build_pipeline(products, matches=matches)
        session = _make_session()

        result = await pipeline.run(session)

        top = result["report"]["top_products"]
        assert len(top) == 1
        assert top[0]["product_id"] == 1
        assert top[0]["supplier_info"] is not None

    @pytest.mark.asyncio
    async def test_default_limit_and_top_k(self):
        products = [_make_product(1)]
        pipeline, _ = _build_pipeline(products, matches=[_make_supplier_match(1)])
        session = _make_session()

        result = await pipeline.run(session)

        assert result["status"] == "success"
        matching = pipeline._matching_service.match_products_with_matcher
        _, kwargs = matching.await_args
        assert kwargs.get("top_k") == 3


# ═══════════════════════════════════════════════════════════════
# 空商品列表
# ═══════════════════════════════════════════════════════════════


class TestEmptyProducts:
    """Empty candidate list handling."""

    @pytest.mark.asyncio
    async def test_empty_products_success(self):
        pipeline, _ = _build_pipeline([])
        session = _make_session()

        result = await pipeline.run(session)

        assert result["status"] == "success"
        assert result["stats"]["total_products"] == 0
        assert result["report"]["top_products"] == []

    @pytest.mark.asyncio
    async def test_empty_products_skips_matching(self):
        pipeline, _ = _build_pipeline([])
        session = _make_session()

        await pipeline.run(session)

        matching = pipeline._matching_service.match_products_with_matcher
        matching.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_products_report_has_statistics(self):
        pipeline, _ = _build_pipeline([])
        session = _make_session()

        result = await pipeline.run(session)

        assert "statistics" in result["report"]
        assert result["report"]["statistics"]["total_products"] == 0


# ═══════════════════════════════════════════════════════════════
# 无供应商匹配
# ═══════════════════════════════════════════════════════════════


class TestNoSupplierMatch:
    """Products with no supplier matches."""

    @pytest.mark.asyncio
    async def test_no_matches_still_success(self):
        products = [_make_product(1), _make_product(2)]
        pipeline, _ = _build_pipeline(products, matches=[])
        session = _make_session()

        result = await pipeline.run(session)

        assert result["status"] == "success"
        assert result["stats"]["matched_products"] == 0
        assert result["stats"]["total_matches"] == 0

    @pytest.mark.asyncio
    async def test_no_matches_filtered_from_report(self):
        # No matches → opportunity score low → filtered out by generator.
        products = [_make_product(1)]
        pipeline, _ = _build_pipeline(products, matches=[])
        session = _make_session()

        result = await pipeline.run(session)

        # Low score products are filtered; report still generated.
        assert result["report"]["top_products"] == []
        assert result["report"]["statistics"]["matched_products"] == 0

    @pytest.mark.asyncio
    async def test_partial_matches(self):
        products = [_make_product(1), _make_product(2)]

        async def _match(session, product, top_k=3):
            if product.id == 1:
                return [_make_supplier_match(1)]
            return []

        pipeline, _ = _build_pipeline(
            products, matching_side_effect=_match,
        )
        session = _make_session()

        result = await pipeline.run(session)

        assert result["status"] == "success"
        assert result["stats"]["matched_products"] == 1
        assert result["stats"]["total_matches"] == 1


# ═══════════════════════════════════════════════════════════════
# 爬虫异常 (product acquisition failure)
# ═══════════════════════════════════════════════════════════════


class TestAcquireFailure:
    """Product acquisition (crawler/list_all) failure."""

    @pytest.mark.asyncio
    async def test_acquire_exception_returns_error(self):
        svc = MagicMock()
        svc.list_all = AsyncMock(side_effect=RuntimeError("db down"))
        pipeline = DailySelectionPipeline(
            product_service=svc,
            matching_service=_make_matching_service(),
            task_repo=_make_task_repo(),
        )
        session = _make_session()

        result = await pipeline.run(session)

        assert result["status"] == "error"
        assert result["stage"] == "acquire"
        assert "db down" in result["error"]
        assert result["report"] is None

    @pytest.mark.asyncio
    async def test_acquire_exception_marks_task_failed(self):
        svc = MagicMock()
        svc.list_all = AsyncMock(side_effect=RuntimeError("boom"))
        repo = _make_task_repo()
        pipeline = DailySelectionPipeline(
            product_service=svc,
            matching_service=_make_matching_service(),
            task_repo=repo,
        )
        session = _make_session()

        await pipeline.run(session)

        repo.finish.assert_awaited_once()
        _, kwargs = repo.finish.await_args
        assert kwargs["status"] == "FAILED"
        assert kwargs["error"] is not None

    @pytest.mark.asyncio
    async def test_acquire_exception_never_raises(self):
        svc = MagicMock()
        svc.list_all = AsyncMock(side_effect=ValueError("bad"))
        pipeline = DailySelectionPipeline(
            product_service=svc,
            matching_service=_make_matching_service(),
            task_repo=_make_task_repo(),
        )
        session = _make_session()

        # Must not raise.
        result = await pipeline.run(session)
        assert result["status"] == "error"


# ═══════════════════════════════════════════════════════════════
# 匹配异常 (per-product matching failure isolated)
# ═══════════════════════════════════════════════════════════════


class TestMatchingFailure:
    """Matching failures are isolated per product."""

    @pytest.mark.asyncio
    async def test_matching_exception_isolated(self):
        products = [_make_product(1), _make_product(2)]

        async def _match(session, product, top_k=3):
            if product.id == 1:
                raise RuntimeError("match blew up")
            return [_make_supplier_match(2)]

        pipeline, _ = _build_pipeline(products, matching_side_effect=_match)
        session = _make_session()

        result = await pipeline.run(session)

        # Pipeline still succeeds; error counted, product 2 matched.
        assert result["status"] == "success"
        assert result["stats"]["match_errors"] == 1
        assert result["stats"]["matched_products"] == 1

    @pytest.mark.asyncio
    async def test_all_matching_fail_still_success(self):
        products = [_make_product(1), _make_product(2)]
        pipeline, _ = _build_pipeline(
            products, matching_side_effect=RuntimeError("all fail"),
        )
        session = _make_session()

        result = await pipeline.run(session)

        assert result["status"] == "success"
        assert result["stats"]["match_errors"] == 2
        assert result["stats"]["matched_products"] == 0

    @pytest.mark.asyncio
    async def test_matching_failure_marks_task_success(self):
        # Isolated matching error should NOT fail the whole task.
        products = [_make_product(1)]
        repo = _make_task_repo()
        pipeline, _ = _build_pipeline(
            products,
            matching_side_effect=RuntimeError("x"),
            task_repo=repo,
        )
        session = _make_session()

        await pipeline.run(session)

        _, kwargs = repo.finish.await_args
        assert kwargs["status"] == "SUCCESS"


# ═══════════════════════════════════════════════════════════════
# 报告生成异常
# ═══════════════════════════════════════════════════════════════


class TestReportFailure:
    """Report generation failure → error result."""

    @pytest.mark.asyncio
    async def test_report_exception_returns_error(self):
        products = [_make_product(1)]
        bad_generator = MagicMock()
        bad_generator.generate = MagicMock(side_effect=RuntimeError("report fail"))
        pipeline, _ = _build_pipeline(
            products,
            matches=[_make_supplier_match(1)],
            report_generator=bad_generator,
        )
        session = _make_session()

        result = await pipeline.run(session)

        assert result["status"] == "error"
        assert result["stage"] == "report"
        assert "report fail" in result["error"]
        assert result["report"] is None

    @pytest.mark.asyncio
    async def test_report_exception_marks_task_failed(self):
        products = [_make_product(1)]
        bad_generator = MagicMock()
        bad_generator.generate = MagicMock(side_effect=RuntimeError("x"))
        repo = _make_task_repo()
        pipeline, _ = _build_pipeline(
            products,
            matches=[_make_supplier_match(1)],
            report_generator=bad_generator,
            task_repo=repo,
        )
        session = _make_session()

        await pipeline.run(session)

        _, kwargs = repo.finish.await_args
        assert kwargs["status"] == "FAILED"


# ═══════════════════════════════════════════════════════════════
# TaskExecution 记录
# ═══════════════════════════════════════════════════════════════


class TestTaskExecutionTracking:
    """TaskExecution record lifecycle."""

    @pytest.mark.asyncio
    async def test_creates_running_record(self):
        products = [_make_product(1)]
        repo = _make_task_repo()
        pipeline, _ = _build_pipeline(
            products, matches=[_make_supplier_match(1)], task_repo=repo,
        )
        session = _make_session()

        result = await pipeline.run(session)

        repo.create.assert_awaited_once()
        created = repo.create.await_args[0][0]
        assert created.task_name == TASK_NAME
        assert created.status == "RUNNING"
        assert result["task_execution_id"] == 4242

    @pytest.mark.asyncio
    async def test_finishes_with_success(self):
        products = [_make_product(1)]
        repo = _make_task_repo()
        pipeline, _ = _build_pipeline(
            products, matches=[_make_supplier_match(1)], task_repo=repo,
        )
        session = _make_session()

        await pipeline.run(session)

        repo.finish.assert_awaited_once()
        args, kwargs = repo.finish.await_args
        assert args[0] == 4242
        assert kwargs["status"] == "SUCCESS"
        assert kwargs["duration"] >= 0.0

    @pytest.mark.asyncio
    async def test_track_disabled_skips_repo(self):
        products = [_make_product(1)]
        repo = _make_task_repo()
        pipeline, _ = _build_pipeline(
            products, matches=[_make_supplier_match(1)], task_repo=repo,
        )
        session = _make_session()

        result = await pipeline.run(session, track=False)

        repo.create.assert_not_awaited()
        repo.finish.assert_not_awaited()
        assert result["task_execution_id"] is None
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_tracking_failure_does_not_break_run(self):
        products = [_make_product(1)]
        repo = MagicMock()
        repo.create = AsyncMock(side_effect=RuntimeError("no db"))
        repo.finish = AsyncMock(return_value=None)
        pipeline, _ = _build_pipeline(
            products, matches=[_make_supplier_match(1)], task_repo=repo,
        )
        session = _make_session()

        result = await pipeline.run(session)

        # Business still succeeds even if tracking creation fails.
        assert result["status"] == "success"
        assert result["task_execution_id"] is None


# ═══════════════════════════════════════════════════════════════
# 多次运行隔离 (statelessness)
# ═══════════════════════════════════════════════════════════════


class TestStatelessness:
    """Multiple runs must not leak state."""

    @pytest.mark.asyncio
    async def test_two_runs_independent_stats(self):
        products = [_make_product(1)]
        pipeline, _ = _build_pipeline(products, matches=[_make_supplier_match(1)])
        session = _make_session()

        r1 = await pipeline.run(session)
        r2 = await pipeline.run(session)

        assert r1["stats"]["total_products"] == 1
        assert r2["stats"]["total_products"] == 1
        assert r1["stats"]["total_matches"] == 1
        assert r2["stats"]["total_matches"] == 1
        # Separate stats dicts, not accumulated.
        assert r1["stats"] is not r2["stats"]

    @pytest.mark.asyncio
    async def test_run_after_error_recovers(self):
        products = [_make_product(1)]
        svc = MagicMock()
        # First call fails, second succeeds.
        svc.list_all = AsyncMock(
            side_effect=[RuntimeError("boom"), products],
        )
        pipeline = DailySelectionPipeline(
            product_service=svc,
            matching_service=_make_matching_service(
                matches_by_call=[_make_supplier_match(1)],
            ),
            task_repo=_make_task_repo(),
        )
        session = _make_session()

        r1 = await pipeline.run(session)
        r2 = await pipeline.run(session)

        assert r1["status"] == "error"
        assert r2["status"] == "success"

    @pytest.mark.asyncio
    async def test_reusable_across_sessions(self):
        products = [_make_product(1)]
        pipeline, _ = _build_pipeline(products, matches=[_make_supplier_match(1)])

        r1 = await pipeline.run(_make_session())
        r2 = await pipeline.run(_make_session())

        assert r1["status"] == "success"
        assert r2["status"] == "success"


# ═══════════════════════════════════════════════════════════════
# 数据转换 / 边界
# ═══════════════════════════════════════════════════════════════


class TestDataConversion:
    """match/product dict conversion helpers."""

    def test_match_to_dict_maps_similarity_to_final(self):
        m = _make_supplier_match(1, similarity_score=0.77)
        d = DailySelectionPipeline._match_to_dict(1, m)
        assert d["final_score"] == 0.77
        assert d["product_id"] == 1
        assert d["supplier_title"]

    def test_match_to_dict_dict_input(self):
        raw = {"similarity_score": 0.6, "supplier_title": "x"}
        d = DailySelectionPipeline._match_to_dict(9, raw)
        assert d["product_id"] == 9
        assert d["final_score"] == 0.6

    def test_match_to_dict_preserves_existing_final_score(self):
        raw = {"final_score": 0.9, "similarity_score": 0.1}
        d = DailySelectionPipeline._match_to_dict(1, raw)
        assert d["final_score"] == 0.9

    def test_product_to_dict_from_orm(self):
        p = _make_product(5, name="测试", price=88.0, viewers=10, sales_24h=2)
        d = DailySelectionPipeline._product_to_dict(p)
        assert d["product_id"] == 5
        assert d["title"] == "测试"
        assert d["price"] == 88.0
        assert d["viewers"] == 10
        assert d["sales_24h"] == 2

    def test_product_to_dict_from_dict(self):
        raw = {"id": 7, "title": "abc", "price": 10}
        d = DailySelectionPipeline._product_to_dict(raw)
        assert d["product_id"] == 7

    def test_get_product_id_orm_and_dict(self):
        assert DailySelectionPipeline._get_product_id(_make_product(3)) == 3
        assert DailySelectionPipeline._get_product_id({"product_id": 8}) == 8
        assert DailySelectionPipeline._get_product_id({"id": 11}) == 11


# ═══════════════════════════════════════════════════════════════
# 默认依赖 & 无侵入
# ═══════════════════════════════════════════════════════════════


class TestDefaults:
    """Default dependency wiring."""

    def test_default_scorer_and_generator(self):
        from app.services.opportunity.scorer import OpportunityScorer
        from app.services.report.daily_selection_report_generator import (
            DailySelectionReportGenerator,
        )

        pipeline = DailySelectionPipeline()
        assert isinstance(pipeline._scorer, OpportunityScorer)
        assert isinstance(pipeline._report_generator, DailySelectionReportGenerator)

    def test_session_dependent_defaults_lazy(self):
        # Not built until run(); None until then.
        pipeline = DailySelectionPipeline()
        assert pipeline._product_service is None
        assert pipeline._matching_service is None
        assert pipeline._task_repo is None

    @pytest.mark.asyncio
    async def test_commit_called_on_tracking(self):
        products = [_make_product(1)]
        pipeline, _ = _build_pipeline(products, matches=[_make_supplier_match(1)])
        session = _make_session()

        await pipeline.run(session)

        # commit invoked for create + finish tracking.
        assert session.commit.await_count >= 1

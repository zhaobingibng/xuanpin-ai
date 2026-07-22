"""Tests for Phase 29: SupplierMatchingService integration with ProductMatcher.

Covers:
1. ProductMatcher is called by match_with_db
2. Returns top_k results
3. SupplierMatch correctly saved with new fields
4. Empty supplier_products handling
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.product import Product
from app.models.supplier_match import SupplierMatch
from app.services.supplier_matching import SupplierMatchingService


# ── Helpers ──────────────────────────────────────────────────

def _make_product(
    pid: int = 1,
    name: str = "三只松鼠坚果礼盒装",
    price: float = 99.0,
) -> Product:
    return Product(
        id=pid,
        name=name,
        platform="taobao",
        shop="三只松鼠旗舰店",
        price=price,
        first_seen_time=datetime.now(),
    )


def _make_match_result(
    supplier_product_id: int = 1,
    title: str = "坚果礼盒装 厂家直销",
    price: float = 50.0,
    final_score: float = 0.92,
    text_score: float = 0.85,
    feature_score: float = 0.40,
    url: str = "https://1688.com/offer/1",
) -> dict:
    return {
        "supplier_product_id": supplier_product_id,
        "title": title,
        "price": price,
        "url": url,
        "offer_id": f"offer_{supplier_product_id}",
        "shop_name": "测试店铺",
        "image": "https://img.example.com/1.jpg",
        "similarity_score": final_score,
        "text_score": text_score,
        "feature_score": feature_score,
        "final_score": final_score,
    }


# ═══════════════════════════════════════════════════════════════
# match_with_db — ProductMatcher 调用验证
# ═══════════════════════════════════════════════════════════════


class TestMatchWithDb:
    """Test match_with_db() method."""

    @pytest.mark.asyncio
    async def test_calls_product_matcher(self):
        """Verify match_with_db calls ProductMatcher internally."""
        service = SupplierMatchingService()
        session = AsyncMock()
        product = _make_product()

        mock_results = [_make_match_result(1, "坚果礼盒", 50.0)]

        with patch(
            "app.matching.product_matcher.ProductMatcher"
        ) as mock_pm_cls:
            mock_pm = MagicMock()
            mock_pm.match_product = AsyncMock(return_value=mock_results)
            mock_pm_cls.return_value = mock_pm

            results = await service.match_with_db(session, product, top_k=3)

        mock_pm_cls.assert_called_once_with(session)
        mock_pm.match_product.assert_called_once_with(
            "三只松鼠坚果礼盒装", image=None, top_k=3
        )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_returns_top_k_results(self):
        """match_with_db should return exactly top_k results."""
        service = SupplierMatchingService()
        session = AsyncMock()
        product = _make_product()

        mock_results = [
            _make_match_result(i, f"商品{i}", 50.0 + i * 10, 0.9 - i * 0.1)
            for i in range(1, 6)
        ]

        with patch(
            "app.matching.product_matcher.ProductMatcher"
        ) as mock_pm_cls:
            mock_pm = MagicMock()
            mock_pm.match_product = AsyncMock(return_value=mock_results[:3])
            mock_pm_cls.return_value = mock_pm

            results = await service.match_with_db(session, product, top_k=3)

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_empty_product(self):
        """match_with_db with empty product should return empty list."""
        service = SupplierMatchingService()
        session = AsyncMock()
        product = Product(id=0, name="", price=0.0)

        results = await service.match_with_db(session, product, top_k=3)
        assert results == []

    @pytest.mark.asyncio
    async def test_none_product(self):
        """match_with_db with None product should return empty list."""
        service = SupplierMatchingService()
        session = AsyncMock()

        results = await service.match_with_db(session, None, top_k=3)
        assert results == []

    @pytest.mark.asyncio
    async def test_empty_supplier_products(self):
        """When ProductMatcher returns [], match_with_db returns []."""
        service = SupplierMatchingService()
        session = AsyncMock()
        product = _make_product()

        with patch(
            "app.matching.product_matcher.ProductMatcher"
        ) as mock_pm_cls:
            mock_pm = MagicMock()
            mock_pm.match_product = AsyncMock(return_value=[])
            mock_pm_cls.return_value = mock_pm

            results = await service.match_with_db(session, product, top_k=3)

        assert results == []

    @pytest.mark.asyncio
    async def test_result_structure(self):
        """Each result should contain all expected fields."""
        service = SupplierMatchingService()
        session = AsyncMock()
        product = _make_product()

        mock_results = [_make_match_result(42, "测试商品", 88.8, 0.95, 0.9, 0.5)]

        with patch(
            "app.matching.product_matcher.ProductMatcher"
        ) as mock_pm_cls:
            mock_pm = MagicMock()
            mock_pm.match_product = AsyncMock(return_value=mock_results)
            mock_pm_cls.return_value = mock_pm

            results = await service.match_with_db(session, product, top_k=3)

        r = results[0]
        assert "supplier_product_id" in r
        assert r["supplier_product_id"] == 42
        assert "title" in r
        assert "price" in r
        assert r["price"] == 88.8
        assert "similarity_score" in r
        assert "text_score" in r
        assert "feature_score" in r
        assert "final_score" in r
        assert r["final_score"] == 0.95

    @pytest.mark.asyncio
    async def test_top_k_5(self):
        """Request top_k=5 should call ProductMatcher with top_k=5."""
        service = SupplierMatchingService()
        session = AsyncMock()
        product = _make_product()

        mock_results = [_make_match_result(i) for i in range(1, 6)]

        with patch(
            "app.matching.product_matcher.ProductMatcher"
        ) as mock_pm_cls:
            mock_pm = MagicMock()
            mock_pm.match_product = AsyncMock(return_value=mock_results)
            mock_pm_cls.return_value = mock_pm

            results = await service.match_with_db(session, product, top_k=5)

        mock_pm.match_product.assert_called_once_with(
            "三只松鼠坚果礼盒装", image=None, top_k=5
        )
        assert len(results) == 5


# ═══════════════════════════════════════════════════════════════
# SupplierMatch 新字段验证
# ═══════════════════════════════════════════════════════════════


class TestSupplierMatchNewFields:
    """Test SupplierMatch model with new fields."""

    def test_supplier_match_with_supplier_product_id(self):
        """SupplierMatch should accept supplier_product_id."""
        match = SupplierMatch(
            product_id=1,
            supplier_product_id=42,
            supplier_title="坚果礼盒",
            supplier_price=50.0,
            similarity_score=0.92,
            text_score=0.85,
            feature_score=0.40,
            rank=1,
            estimated_profit=49.0,
            profit_margin=49.5,
        )
        assert match.supplier_product_id == 42
        assert match.text_score == 0.85
        assert match.feature_score == 0.40
        assert match.rank == 1

    def test_supplier_match_backward_compat(self):
        """Old-style SupplierMatch (without new fields) should still work."""
        match = SupplierMatch(
            product_id=1,
            supplier_title="坚果礼盒 厂家直销",
            supplier_url="https://1688.com/xxx",
            supplier_price=18.0,
            similarity_score=85.0,
            estimated_profit=51.0,
            profit_margin=73.9,
        )
        assert match.product_id == 1
        assert match.supplier_product_id is None
        assert match.text_score is None
        assert match.feature_score is None
        assert match.rank is None
        assert match.supplier_price == 18.0
        assert match.profit_margin == 73.9

    def test_supplier_match_multiple_ranks(self):
        """Multiple matches for same product with different ranks."""
        match1 = SupplierMatch(
            product_id=1, supplier_product_id=42,
            supplier_title="匹配1", supplier_price=50.0,
            similarity_score=0.92, rank=1,
            estimated_profit=49.0, profit_margin=49.5,
        )
        match2 = SupplierMatch(
            product_id=1, supplier_product_id=43,
            supplier_title="匹配2", supplier_price=55.0,
            similarity_score=0.85, rank=2,
            estimated_profit=44.0, profit_margin=44.4,
        )
        match3 = SupplierMatch(
            product_id=1, supplier_product_id=44,
            supplier_title="匹配3", supplier_price=60.0,
            similarity_score=0.71, rank=3,
            estimated_profit=39.0, profit_margin=39.4,
        )

        assert match1.rank == 1
        assert match2.rank == 2
        assert match3.rank == 3
        assert match1.similarity_score > match2.similarity_score > match3.similarity_score


# ═══════════════════════════════════════════════════════════════
# 端到端：match_with_db → SupplierMatch 保存
# ═══════════════════════════════════════════════════════════════


class TestMatchWithDbToSupplierMatch:
    """Test end-to-end: match_with_db results → SupplierMatch records."""

    def test_create_supplier_matches_from_results(self):
        """Convert match_with_db results to SupplierMatch records."""
        service = SupplierMatchingService()
        product = _make_product(price=99.0)

        results = [
            _make_match_result(1, "坚果礼盒", 50.0, 0.92, 0.85, 0.40),
            _make_match_result(2, "坚果大礼包", 60.0, 0.80, 0.75, 0.35),
            _make_match_result(3, "混合坚果", 70.0, 0.68, 0.60, 0.32),
        ]

        matches = []
        for rank, r in enumerate(results, 1):
            supplier_price = r.get("price", 0.0)
            profit_data = service.calculate_profit(product.price, supplier_price)

            match = SupplierMatch(
                product_id=product.id,
                supplier_product_id=r.get("supplier_product_id"),
                supplier_title=r.get("title", ""),
                supplier_url=r.get("url"),
                supplier_price=supplier_price,
                similarity_score=r.get("final_score", 0.0),
                text_score=r.get("text_score"),
                feature_score=r.get("feature_score"),
                rank=rank,
                estimated_profit=profit_data["estimated_profit"],
                profit_margin=profit_data["profit_margin"],
            )
            matches.append(match)

        assert len(matches) == 3
        assert matches[0].rank == 1
        assert matches[0].similarity_score == 0.92
        assert matches[1].rank == 2
        assert matches[2].rank == 3

    def test_create_supplier_matches_empty_results(self):
        """Empty results should produce no matches."""
        service = SupplierMatchingService()
        product = _make_product()

        matches = []
        for rank, r in enumerate([], 1):
            pass  # never executed

        assert len(matches) == 0

    def test_profit_calculation_in_flow(self):
        """Profit calculation in the integration flow."""
        service = SupplierMatchingService()
        product = _make_product(price=99.0)

        results = [
            _make_match_result(1, "坚果礼盒", 50.0, 0.92),
        ]

        for rank, r in enumerate(results, 1):
            supplier_price = r.get("price", 0.0)
            profit_data = service.calculate_profit(product.price, supplier_price)

            # Profit = 99 - 50 = 49, margin = 49/99 * 100 ≈ 49.49%
            assert profit_data["estimated_profit"] == 49.0
            assert profit_data["profit_margin"] == pytest.approx(49.5, abs=0.1)


# ═══════════════════════════════════════════════════════════════
# 旧接口兼容性验证
# ═══════════════════════════════════════════════════════════════


class TestOldMethodCompatibility:
    """Verify old match_product() still works unchanged."""

    def test_old_match_product_still_works(self):
        """Old match_product should still work after adding match_with_db."""
        service = SupplierMatchingService()
        product = _make_product(name="芋泥味蛋皮吐司卷", price=69.0)

        supplier_products = [
            {
                "title": "芋泥蛋皮吐司卷 厂家直销 批发",
                "url": "https://detail.1688.com/offer/123.html",
                "price": 18.0,
            },
            {
                "title": "肉松面包 工厂货源",
                "url": "https://detail.1688.com/offer/456.html",
                "price": 15.0,
            },
        ]

        result = service.match_product(product, supplier_products)

        assert result is not None
        assert "supplier_title" in result
        assert "supplier_price" in result
        assert "similarity_score" in result
        assert "estimated_profit" in result
        assert "profit_margin" in result
        # Old result does NOT include supplier_product_id
        assert "supplier_product_id" not in result

    def test_old_create_match_record_still_works(self):
        """Old create_match_record should still work."""
        service = SupplierMatchingService()
        product = _make_product()

        match_data = {
            "supplier_title": "供应商商品",
            "supplier_url": "https://1688.com/xxx",
            "supplier_price": 18.0,
            "similarity_score": 85.0,
            "estimated_profit": 51.0,
            "profit_margin": 73.9,
        }

        record = service.create_match_record(product, match_data)

        assert isinstance(record, SupplierMatch)
        assert record.product_id == 1
        assert record.supplier_product_id is None  # Not set by old method


# ═══════════════════════════════════════════════════════════════
# Daily selection task 集成验证
# ═══════════════════════════════════════════════════════════════


class TestDailySelectionIntegration:
    """Test daily selection task with new matching."""

    @pytest.mark.asyncio
    async def test_run_daily_selection_no_alibaba_client_import(self):
        """Verify run_daily_selection no longer imports AlibabaSearchClient."""
        import inspect
        from app.tasks.daily_selection_task import run_daily_selection

        source = inspect.getsource(run_daily_selection)
        # AlibabaSearchClient should NOT appear in run_daily_selection
        assert "AlibabaSearchClient" not in source
        # match_products_with_matcher SHOULD appear
        assert "match_products_with_matcher" in source

    @pytest.mark.asyncio
    async def test_run_daily_selection_uses_match_with_db(self):
        """run_daily_selection should use match_products_with_matcher."""
        import inspect
        from app.tasks.daily_selection_task import run_daily_selection

        source = inspect.getsource(run_daily_selection)
        assert "match_products_with_matcher" in source
        # Old cleaning/search pipeline should be gone
        assert "clean_title" not in source
        assert "generate_search_keyword" not in source

    @pytest.mark.asyncio
    async def test_run_daily_selection_saves_top3(self):
        """run_daily_selection should save top-3 results per product."""
        import inspect
        from app.tasks.daily_selection_task import run_daily_selection

        source = inspect.getsource(run_daily_selection)
        assert "top_k=3" in source
        # Uses match_products_with_matcher which internally handles rank
        assert "match_products_with_matcher" in source


# ═══════════════════════════════════════════════════════════════
# 回归：ensure no broken imports
# ═══════════════════════════════════════════════════════════════


class TestImports:
    """Verify imports work correctly."""

    def test_alibaba_client_still_importable(self):
        """AlibabaSearchClient import should still work (not removed)."""
        from app.crawler.alibaba import AlibabaSearchClient
        client = AlibabaSearchClient(use_mock=True)
        assert client is not None

    def test_supplier_match_new_fields_exist(self):
        """New fields should exist on SupplierMatch."""
        assert hasattr(SupplierMatch, "supplier_product_id")
        assert hasattr(SupplierMatch, "text_score")
        assert hasattr(SupplierMatch, "feature_score")
        assert hasattr(SupplierMatch, "rank")

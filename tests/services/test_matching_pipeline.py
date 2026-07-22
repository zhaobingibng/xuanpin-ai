"""Tests for Phase 30: Unified matching pipeline via match_products_with_matcher().

Covers:
- ProductMatcher call
- SupplierMatch save
- top_k handling
- Empty supplier pool
- Match failure
- Multiple supplier save
- Deprecated methods still work
- final_score property
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


def _make_match_dict(
    supplier_product_id: int = 1,
    title: str = "坚果礼盒 厂家直销",
    price: float = 50.0,
    final_score: float = 0.92,
    text_score: float = 0.85,
    feature_score: float = 0.40,
) -> dict:
    return {
        "supplier_product_id": supplier_product_id,
        "title": title,
        "price": price,
        "url": f"https://1688.com/offer/{supplier_product_id}",
        "offer_id": f"offer_{supplier_product_id}",
        "shop_name": "测试店铺",
        "image": "https://img.example.com/1.jpg",
        "similarity_score": final_score,
        "text_score": text_score,
        "feature_score": feature_score,
        "final_score": final_score,
    }


# ═══════════════════════════════════════════════════════════════
# match_products_with_matcher — 统一入口
# ═══════════════════════════════════════════════════════════════


class TestMatchProductsWithMatcher:
    """Test the unified match_products_with_matcher() entry."""

    @pytest.mark.asyncio
    async def test_returns_supplier_match_records(self):
        """Should return list of SupplierMatch records."""
        service = SupplierMatchingService()
        session = AsyncMock()
        product = _make_product()

        mock_results = [_make_match_dict(1, "坚果礼盒", 50.0, 0.92)]

        with patch(
            "app.matching.product_matcher.ProductMatcher"
        ) as mock_pm_cls:
            mock_pm = MagicMock()
            mock_pm.match_product = AsyncMock(return_value=mock_results)
            mock_pm_cls.return_value = mock_pm

            matches = await service.match_products_with_matcher(session, product, top_k=3)

        assert len(matches) == 1
        assert isinstance(matches[0], SupplierMatch)

    @pytest.mark.asyncio
    async def test_supplier_match_has_supplier_product_id(self):
        """SupplierMatch should contain supplier_product_id."""
        service = SupplierMatchingService()
        session = AsyncMock()
        product = _make_product()

        mock_results = [_make_match_dict(42, "坚果礼盒", 50.0, 0.92)]

        with patch(
            "app.matching.product_matcher.ProductMatcher"
        ) as mock_pm_cls:
            mock_pm = MagicMock()
            mock_pm.match_product = AsyncMock(return_value=mock_results)
            mock_pm_cls.return_value = mock_pm

            matches = await service.match_products_with_matcher(session, product, top_k=3)

        assert matches[0].supplier_product_id == 42

    @pytest.mark.asyncio
    async def test_supplier_match_has_scores(self):
        """SupplierMatch should have text_score, feature_score, similarity_score."""
        service = SupplierMatchingService()
        session = AsyncMock()
        product = _make_product()

        mock_results = [_make_match_dict(1, "坚果", 50.0, 0.92, 0.85, 0.40)]

        with patch(
            "app.matching.product_matcher.ProductMatcher"
        ) as mock_pm_cls:
            mock_pm = MagicMock()
            mock_pm.match_product = AsyncMock(return_value=mock_results)
            mock_pm_cls.return_value = mock_pm

            matches = await service.match_products_with_matcher(session, product, top_k=3)

        m = matches[0]
        assert m.text_score == 0.85
        assert m.feature_score == 0.40
        assert m.similarity_score == 0.92

    @pytest.mark.asyncio
    async def test_supplier_match_has_rank(self):
        """SupplierMatch records should be ranked 1, 2, 3..."""
        service = SupplierMatchingService()
        session = AsyncMock()
        product = _make_product()

        mock_results = [
            _make_match_dict(i, f"商品{i}", 50.0 + i * 10, 0.9 - i * 0.1)
            for i in range(1, 4)
        ]

        with patch(
            "app.matching.product_matcher.ProductMatcher"
        ) as mock_pm_cls:
            mock_pm = MagicMock()
            mock_pm.match_product = AsyncMock(return_value=mock_results)
            mock_pm_cls.return_value = mock_pm

            matches = await service.match_products_with_matcher(session, product, top_k=3)

        assert len(matches) == 3
        assert matches[0].rank == 1
        assert matches[1].rank == 2
        assert matches[2].rank == 3

    @pytest.mark.asyncio
    async def test_top_k_limits_results(self):
        """top_k=2 should return at most 2 results."""
        service = SupplierMatchingService()
        session = AsyncMock()
        product = _make_product()

        mock_results = [_make_match_dict(i) for i in range(1, 3)]  # 2 results

        with patch(
            "app.matching.product_matcher.ProductMatcher"
        ) as mock_pm_cls:
            mock_pm = MagicMock()
            mock_pm.match_product = AsyncMock(return_value=mock_results)
            mock_pm_cls.return_value = mock_pm

            matches = await service.match_products_with_matcher(session, product, top_k=2)

        assert len(matches) == 2

    @pytest.mark.asyncio
    async def test_empty_supplier_pool(self):
        """Empty supplier_products table → returns empty list."""
        service = SupplierMatchingService()
        session = AsyncMock()
        product = _make_product()

        with patch(
            "app.matching.product_matcher.ProductMatcher"
        ) as mock_pm_cls:
            mock_pm = MagicMock()
            mock_pm.match_product = AsyncMock(return_value=[])
            mock_pm_cls.return_value = mock_pm

            matches = await service.match_products_with_matcher(session, product, top_k=3)

        assert matches == []

    @pytest.mark.asyncio
    async def test_match_failure_no_results(self):
        """No matching products → returns empty list."""
        service = SupplierMatchingService()
        session = AsyncMock()
        product = _make_product(name="xyz不存在商品123")

        with patch(
            "app.matching.product_matcher.ProductMatcher"
        ) as mock_pm_cls:
            mock_pm = MagicMock()
            mock_pm.match_product = AsyncMock(return_value=[])
            mock_pm_cls.return_value = mock_pm

            matches = await service.match_products_with_matcher(session, product, top_k=3)

        assert matches == []

    @pytest.mark.asyncio
    async def test_profit_calculation_integrated(self):
        """Profit should be calculated automatically."""
        service = SupplierMatchingService()
        session = AsyncMock()
        product = _make_product(price=99.0)

        # supplier price = 50 → profit = 49, margin ≈ 49.5%
        mock_results = [_make_match_dict(1, "坚果", 50.0, 0.92)]

        with patch(
            "app.matching.product_matcher.ProductMatcher"
        ) as mock_pm_cls:
            mock_pm = MagicMock()
            mock_pm.match_product = AsyncMock(return_value=mock_results)
            mock_pm_cls.return_value = mock_pm

            matches = await service.match_products_with_matcher(session, product, top_k=3)

        m = matches[0]
        assert m.estimated_profit == 49.0
        assert m.profit_margin == pytest.approx(49.5, abs=0.1)

    @pytest.mark.asyncio
    async def test_multiple_suppliers_saved(self):
        """Multiple supplier results should all be returned."""
        service = SupplierMatchingService()
        session = AsyncMock()
        product = _make_product()

        mock_results = [
            _make_match_dict(1, "商品A", 50.0, 0.92),
            _make_match_dict(2, "商品B", 55.0, 0.80),
            _make_match_dict(3, "商品C", 60.0, 0.68),
        ]

        with patch(
            "app.matching.product_matcher.ProductMatcher"
        ) as mock_pm_cls:
            mock_pm = MagicMock()
            mock_pm.match_product = AsyncMock(return_value=mock_results)
            mock_pm_cls.return_value = mock_pm

            matches = await service.match_products_with_matcher(session, product, top_k=3)

        assert len(matches) == 3
        assert matches[0].similarity_score > matches[2].similarity_score


# ═══════════════════════════════════════════════════════════════
# SupplierMatch final_score property
# ═══════════════════════════════════════════════════════════════


class TestFinalScoreProperty:
    """Test SupplierMatch.final_score property."""

    def test_final_score_equals_similarity_score(self):
        """final_score should return similarity_score."""
        match = SupplierMatch(
            product_id=1,
            supplier_title="坚果",
            supplier_price=50.0,
            similarity_score=0.92,
            estimated_profit=49.0,
            profit_margin=49.5,
        )
        assert match.final_score == 0.92
        assert match.final_score == match.similarity_score


# ═══════════════════════════════════════════════════════════════
# Deprecated methods backward compatibility
# ═══════════════════════════════════════════════════════════════


class TestDeprecatedMethods:
    """Verify old methods still work after marking deprecated."""

    def test_old_match_product_still_works(self):
        """match_product (old) should still return result."""
        import warnings
        service = SupplierMatchingService()
        product = _make_product(name="芋泥味蛋皮吐司卷", price=69.0)

        supplier_products = [
            {
                "title": "芋泥蛋皮吐司卷 厂家直销 批发",
                "url": "https://detail.1688.com/offer/123.html",
                "price": 18.0,
            },
        ]

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = service.match_product(product, supplier_products)

        assert result is not None
        assert "supplier_title" in result

    def test_old_create_match_record_still_works(self):
        """create_match_record (old) should still work."""
        import warnings
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

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            record = service.create_match_record(product, match_data)

        assert isinstance(record, SupplierMatch)
        assert record.product_id == 1

    def test_old_clean_title_still_works(self):
        """clean_title (old) should still remove brand words."""
        service = SupplierMatchingService()
        result = service.clean_title("三只松鼠坚果礼盒装")
        assert "三只松鼠" not in result

    def test_old_calculate_similarity_still_works(self):
        """calculate_similarity (old) should still compute Jaccard."""
        service = SupplierMatchingService()
        score = service.calculate_similarity("芋泥蛋皮吐司卷", "芋泥蛋皮吐司卷")
        assert score == 100.0

    def test_old_generate_keyword_still_works(self):
        """generate_search_keyword (old) should still work."""
        service = SupplierMatchingService()
        kw = service.generate_search_keyword("芋泥味蛋皮吐司卷")
        assert len(kw) > 0


# ═══════════════════════════════════════════════════════════════
# Deprecation warning tests
# ═══════════════════════════════════════════════════════════════


class TestDeprecationWarnings:
    """Verify DeprecationWarning is raised."""

    def test_match_product_emits_warning(self):
        """match_product should emit DeprecationWarning."""
        import warnings
        service = SupplierMatchingService()
        product = _make_product(name="芋泥味蛋皮吐司卷", price=69.0)
        supplier_products = [
            {"title": "芋泥蛋皮吐司卷", "url": "https://1688.com/x", "price": 18.0},
        ]

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always", DeprecationWarning)
            service.match_product(product, supplier_products)

        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)

    def test_create_match_record_emits_warning(self):
        """create_match_record should emit DeprecationWarning."""
        import warnings
        service = SupplierMatchingService()
        product = _make_product()
        match_data = {
            "supplier_title": "x", "supplier_url": "x", "supplier_price": 10.0,
            "similarity_score": 50.0, "estimated_profit": 10.0, "profit_margin": 10.0,
        }

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always", DeprecationWarning)
            service.create_match_record(product, match_data)

        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)

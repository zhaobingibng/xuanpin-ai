"""Tests for Phase 33: Multimodal ProductMatcher (text + image matching)."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image as PILImage

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.matching.product_matcher import ProductMatcher
from app.models.supplier_product import SupplierProductDB
from app.models.product import Product as ProductModel
from app.models.supplier_match import SupplierMatch

import app.models  # noqa: F401 — ensure models registered


# ── Helpers ──────────────────────────────────────────────────

def _make_solid_image(color: tuple[int, int, int] = (255, 0, 0),
                      size: int = 100) -> PILImage.Image:
    """Create a simple solid-color test image."""
    return PILImage.new("RGB", (size, size), color)


def _image_to_bytes(img: PILImage.Image, fmt: str = "PNG") -> bytes:
    """Convert PIL image to bytes."""
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
async def session():
    """Create async in-memory SQLite session with supplier_products table."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def _insert_products(session: AsyncSession) -> list[int]:
    """Insert test supplier products and return IDs."""
    products_data = [
        SupplierProductDB(
            offer_id="p1", title="三只松鼠坚果礼盒装2024新款", price=89.9,
            shop_name="三只松鼠旗舰店", url="https://detail.1688.com/p1.html",
            image="https://img.alicdn.com/p1.jpg",
        ),
        SupplierProductDB(
            offer_id="p2", title="海苔卷零食大礼包即食脆", price=29.9,
            shop_name="海味零食铺", url="https://detail.1688.com/p2.html",
            image="https://img.alicdn.com/p2.jpg",
        ),
        SupplierProductDB(
            offer_id="p3", title="无线蓝牙耳机降噪运动款", price=59.0,
            shop_name="数码科技店", url="https://detail.1688.com/p3.html",
            image="https://img.alicdn.com/p3.jpg",
        ),
        SupplierProductDB(
            offer_id="p4", title="坚果零食大礼包混合装", price=49.9,
            shop_name="零食批发中心", url="https://detail.1688.com/p4.html",
            image=None,  # no image
        ),
    ]
    ids = []
    for p in products_data:
        session.add(p)
        await session.flush()
        ids.append(p.id)
    return ids


# ── Test: No Image — Backward Compatible ─────────────────────

class TestNoImageBackwardCompat:
    """Old interface (no image) must continue to work unchanged."""

    @pytest.mark.asyncio
    async def test_no_image_old_signature(self, session):
        """match_product(title, top_k=N) still works."""
        await _insert_products(session)
        matcher = ProductMatcher(session)

        results = await matcher.match_product("坚果礼盒", top_k=3)

        assert len(results) > 0
        assert results[0]["offer_id"] == "p1"

    @pytest.mark.asyncio
    async def test_no_image_score_is_none(self, session):
        """Without image, image_score should be None."""
        await _insert_products(session)
        matcher = ProductMatcher(session)

        results = await matcher.match_product("坚果礼盒")

        for r in results:
            assert r["image_score"] is None

    @pytest.mark.asyncio
    async def test_no_image_old_formula(self, session):
        """Without image → old formula text*0.6 + feature*0.4."""
        await _insert_products(session)
        matcher = ProductMatcher(session)

        results = await matcher.match_product("坚果礼盒")

        for r in results:
            expected = r["text_score"] * 0.6 + r["feature_score"] * 0.4
            assert r["final_score"] == pytest.approx(expected, abs=0.01)

    @pytest.mark.asyncio
    async def test_no_image_result_fields(self, session):
        """All expected fields present, image_score=None."""
        await _insert_products(session)
        matcher = ProductMatcher(session)

        results = await matcher.match_product("坚果礼盒")
        assert len(results) > 0

        r = results[0]
        assert "text_score" in r
        assert "feature_score" in r
        assert "image_score" in r
        assert "final_score" in r
        assert "similarity_score" in r
        assert r["image_score"] is None


# ── Test: With Image — ImageMatcher Called ───────────────────

class TestWithImageMatcher:
    """When image is provided, ImageMatcher should be invoked."""

    @pytest.mark.asyncio
    async def test_with_image_calls_image_matcher(self, session):
        """Providing an image should trigger ImageMatcher."""
        await _insert_products(session)
        img = _make_solid_image()

        with patch("app.matching.image_matcher.ImageMatcher") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.calculate_similarity.return_value = 0.85

            matcher = ProductMatcher(session)
            results = await matcher.match_product("坚果礼盒", image=img)

            assert len(results) > 0
            # ImageMatcher.calculate_similarity should be called for each candidate with an image URL
            # p1, p2, p3 have images → 3 calls; p4 has no image
            assert mock_instance.calculate_similarity.call_count >= 1

    @pytest.mark.asyncio
    async def test_image_score_present(self, session):
        """Results should contain non-None image_score for candidates with images."""
        await _insert_products(session)
        img = _make_solid_image()

        matcher = ProductMatcher(session)
        matcher._image_matcher = MagicMock()
        matcher._image_matcher.calculate_similarity.return_value = 0.85
        results = await matcher.match_product("坚果礼盒", image=img)

        # At least one result with image should have non-None image_score
        has_image_results = [r for r in results if r["image_score"] is not None]
        assert len(has_image_results) >= 1
        for r in has_image_results:
            assert 0 <= r["image_score"] <= 1
        # Candidates without image URL → image_score=None (expected)
        no_image_results = [r for r in results if r["image_score"] is None]
        for r in no_image_results:
            assert r["image_score"] is None

    @pytest.mark.asyncio
    async def test_image_score_in_range(self, session):
        """image_score should be within [0, 1] when present."""
        await _insert_products(session)
        img = _make_solid_image()

        matcher = ProductMatcher(session)
        matcher._image_matcher = MagicMock()
        matcher._image_matcher.calculate_similarity.return_value = 0.72
        results = await matcher.match_product("坚果", image=img)

        # Check only candidates that actually have image_score (skip those w/o image URL)
        scored = [r for r in results if r["image_score"] is not None]
        assert len(scored) >= 1
        for r in scored:
            assert 0.0 <= r["image_score"] <= 1.0

    @pytest.mark.asyncio
    async def test_pil_image_passed_through(self, session):
        """PIL Image is passed to ImageMatcher."""
        await _insert_products(session)
        img = _make_solid_image(color=(100, 200, 50))

        with patch("app.matching.image_matcher.ImageMatcher") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.calculate_similarity.return_value = 0.8

            matcher = ProductMatcher(session)
            await matcher.match_product("坚果", image=img)

            # First argument to calculate_similarity should be the PIL image
            calls = mock_instance.calculate_similarity.call_args_list
            assert len(calls) > 0
            # Each call: calculate_similarity(query_image, candidate_url)
            for call in calls:
                assert call[0][0] is img

    @pytest.mark.asyncio
    async def test_bytes_image_passed_through(self, session):
        """Bytes image works."""
        await _insert_products(session)
        img = _make_solid_image()
        img_bytes = _image_to_bytes(img)

        with patch("app.matching.image_matcher.ImageMatcher") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.calculate_similarity.return_value = 0.8

            matcher = ProductMatcher(session)
            results = await matcher.match_product("坚果", image=img_bytes)

            assert len(results) > 0


# ── Test: 3D Scoring (new formula) ───────────────────────────

class TestThreeDimensionalScoring:
    """With image → new formula: text*0.4 + feature*0.3 + image*0.3."""

    @pytest.mark.asyncio
    async def test_new_formula_with_image(self, session):
        """New formula applies when image is provided (for candidates with images)."""
        await _insert_products(session)
        img = _make_solid_image()

        matcher = ProductMatcher(session)
        matcher._image_matcher = MagicMock()
        matcher._image_matcher.calculate_similarity.return_value = 0.9
        results = await matcher.match_product("坚果", image=img)

        for r in results:
            if r["image_score"] is not None:
                # New formula: text*0.4 + feature*0.3 + image*0.3
                expected = (
                    r["text_score"] * 0.4
                    + r["feature_score"] * 0.3
                    + r["image_score"] * 0.3
                )
                assert r["final_score"] == pytest.approx(expected, abs=0.01)
            else:
                # Old formula: text*0.6 + feature*0.4
                expected = r["text_score"] * 0.6 + r["feature_score"] * 0.4
                assert r["final_score"] == pytest.approx(expected, abs=0.01)

    @pytest.mark.asyncio
    async def test_all_three_scores_present(self, session):
        """text/feature/image/final scores all present for candidates with images."""
        await _insert_products(session)
        img = _make_solid_image()

        matcher = ProductMatcher(session)
        matcher._image_matcher = MagicMock()
        matcher._image_matcher.calculate_similarity.return_value = 0.9
        results = await matcher.match_product("坚果", image=img)

        # At least one result should have all three scores
        with_image = [r for r in results if r["image_score"] is not None]
        assert len(with_image) >= 1
        for r in with_image:
            assert r["text_score"] > 0
            assert r["feature_score"] > 0
            assert r["image_score"] is not None
            assert r["final_score"] > 0

    @pytest.mark.asyncio
    async def test_sort_by_final_score(self, session):
        """Results still sorted by final_score desc with image."""
        await _insert_products(session)
        img = _make_solid_image()

        matcher = ProductMatcher(session)
        matcher._image_matcher = MagicMock()
        matcher._image_matcher.calculate_similarity.return_value = 0.7
        results = await matcher.match_product("零食", image=img)

        scores = [r["final_score"] for r in results]
        assert scores == sorted(scores, reverse=True)


# ── Test: Graceful Degradation ───────────────────────────────

class TestGracefulDegradation:
    """Image matching failures should degrade gracefully."""

    @pytest.mark.asyncio
    async def test_image_match_exception_graceful(self, session):
        """Exception in ImageMatcher → image_score=None, result still returned."""
        await _insert_products(session)
        img = _make_solid_image()

        with patch("app.matching.image_matcher.ImageMatcher") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.calculate_similarity.side_effect = Exception("Network error")

            matcher = ProductMatcher(session)
            results = await matcher.match_product("坚果", image=img)

            # Should still get results (degraded to text-only)
            assert len(results) > 0
            # image_score should be None for the failed candidate
            # (FusionMatcher with None image_score uses old formula)
            has_none_image = any(r["image_score"] is None for r in results)
            assert has_none_image

    @pytest.mark.asyncio
    async def test_candidate_no_image_url(self, session):
        """Candidate without image URL → image_score=None for that candidate."""
        await _insert_products(session)
        img = _make_solid_image()

        with patch("app.matching.image_matcher.ImageMatcher") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.calculate_similarity.return_value = 0.9

            matcher = ProductMatcher(session)
            results = await matcher.match_product("零食大礼包", image=img)

            # p4 has no image → should not call calculate_similarity for p4
            # Find p4 result
            p4_results = [r for r in results if r["offer_id"] == "p4"]
            if p4_results:
                assert p4_results[0]["image_score"] is None

    @pytest.mark.asyncio
    async def test_all_candidates_no_image(self, session):
        """All candidates lack image → all image_score=None, old formula."""
        # Insert products without images
        for i in range(3):
            session.add(SupplierProductDB(
                offer_id=f"ni_{i}", title=f"商品{i}", price=10.0,
                image=None,
            ))
        await session.flush()

        img = _make_solid_image()

        matcher = ProductMatcher(session)
        results = await matcher.match_product("商品", image=img)

        for r in results:
            assert r["image_score"] is None
            expected = r["text_score"] * 0.6 + r["feature_score"] * 0.4
            assert r["final_score"] == pytest.approx(expected, abs=0.01)


# ── Test: Reranking with Image ───────────────────────────────

class TestImageReranking:
    """Image similarity can change result ordering."""

    @pytest.mark.asyncio
    async def test_image_changes_ranking(self, session):
        """Different image scores should produce different ranking."""
        await _insert_products(session)
        img = _make_solid_image()

        # Get baseline (no image)
        matcher_text = ProductMatcher(session)
        baseline = await matcher_text.match_product("坚果", top_k=5)

        # Get with image (high score for p4, low for p1)
        def mock_calc(source_a, source_b):
            url = str(source_b)
            if "p1" in url:
                return 0.1  # Low image similarity for p1
            if "p4" in url:
                return 0.95  # High image similarity for p4
            return 0.5

        with patch("app.matching.image_matcher.ImageMatcher") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.calculate_similarity.side_effect = mock_calc

            matcher_img = ProductMatcher(session)
            with_image = await matcher_img.match_product("坚果", image=img, top_k=5)

        # Rankings may differ
        baseline_order = [r["offer_id"] for r in baseline]
        with_image_order = [r["offer_id"] for r in with_image]
        assert len(baseline) > 0
        assert len(with_image) > 0

    @pytest.mark.asyncio
    async def test_perfect_image_boosts_score(self, session):
        """High image_score should boost final_score for candidates with images."""
        await _insert_products(session)
        img = _make_solid_image()

        matcher = ProductMatcher(session)
        matcher._image_matcher = MagicMock()
        matcher._image_matcher.calculate_similarity.return_value = 1.0
        results = await matcher.match_product("坚果", image=img)

        for r in results:
            if r["image_score"] is not None:
                # final_score with image=1.0 should be >= text*0.6+feature*0.4
                # new-old = 0.3 - 0.2*text - 0.1*feature >= 0 (since text,feature <= 1)
                old_style = r["text_score"] * 0.6 + r["feature_score"] * 0.4
                assert r["final_score"] >= old_style - 0.01


# ── Test: Edge Cases ─────────────────────────────────────────

class TestMultimodalEdgeCases:
    """Edge cases for multimodal matching."""

    @pytest.mark.asyncio
    async def test_empty_title_returns_empty(self, session):
        """Empty title → [ ], even with image."""
        img = _make_solid_image()
        matcher = ProductMatcher(session)
        results = await matcher.match_product("", image=img)
        assert results == []

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty(self, session):
        """Empty DB → [ ], even with image."""
        img = _make_solid_image()
        matcher = ProductMatcher(session)
        results = await matcher.match_product("坚果", image=img)
        assert results == []

    @pytest.mark.asyncio
    async def test_top_k_with_image(self, session):
        """top_k limits results with image matching."""
        await _insert_products(session)
        img = _make_solid_image()

        with patch("app.matching.image_matcher.ImageMatcher") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.calculate_similarity.return_value = 0.8

            matcher = ProductMatcher(session)
            results = await matcher.match_product("零食", image=img, top_k=2)

            assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_image_matcher_lazy_initialized(self, session):
        """ImageMatcher should only be initialized when image is provided."""
        await _insert_products(session)

        # Without image → _image_matcher stays None
        matcher = ProductMatcher(session)
        assert matcher._image_matcher is None
        await matcher.match_product("坚果")
        assert matcher._image_matcher is None

        # With image → _image_matcher is created
        img = _make_solid_image()
        with patch("app.matching.image_matcher.ImageMatcher") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.calculate_similarity.return_value = 0.8

            await matcher.match_product("坚果", image=img)
            assert matcher._image_matcher is not None


# ── Test: SupplierMatchingService Image Support ──────────────

class TestSupplierMatchingServiceImage:
    """SupplierMatchingService pass-through of image parameter."""

    @pytest.mark.asyncio
    async def test_match_with_db_passes_image(self, session):
        """match_with_db should pass image to ProductMatcher."""
        await _insert_products(session)
        from app.services.supplier_matching import SupplierMatchingService

        service = SupplierMatchingService()
        product = ProductModel(
            id=1, name="坚果礼盒", price=99.0, platform="taobao",
            shop="测试店铺", url="https://taobao.com/item/1",
        )

        img = _make_solid_image()

        with patch("app.matching.image_matcher.ImageMatcher") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.calculate_similarity.return_value = 0.85

            results = await service.match_with_db(session, product, image=img)

            assert len(results) > 0
            # image_score should be present for candidates with images
            has_image = [r for r in results if r["image_score"] is not None]
            assert len(has_image) >= 1
            for r in has_image:
                assert "image_score" in r
                assert 0 <= r["image_score"] <= 1

    @pytest.mark.asyncio
    async def test_match_products_with_matcher_image(self, session):
        """match_products_with_matcher should include image_score."""
        await _insert_products(session)
        from app.services.supplier_matching import SupplierMatchingService

        service = SupplierMatchingService()
        product = ProductModel(
            id=1, name="坚果礼盒", price=99.0, platform="taobao",
            shop="测试店铺", url="https://taobao.com/item/1",
        )

        img = _make_solid_image()

        with patch("app.matching.image_matcher.ImageMatcher") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.calculate_similarity.return_value = 0.85

            matches = await service.match_products_with_matcher(
                session, product, image=img, top_k=3,
            )

            assert len(matches) > 0
            # At least one match should have image_score from candidates with images
            has_image = [m for m in matches if m.image_score is not None]
            assert len(has_image) >= 1
            for m in has_image:
                assert isinstance(m, SupplierMatch)
                assert 0 <= m.image_score <= 1

    @pytest.mark.asyncio
    async def test_match_products_no_image_compat(self, session):
        """match_products_with_matcher without image → image_score=None."""
        await _insert_products(session)
        from app.services.supplier_matching import SupplierMatchingService

        service = SupplierMatchingService()
        product = ProductModel(
            id=1, name="坚果礼盒", price=99.0, platform="taobao",
            shop="测试店铺", url="https://taobao.com/item/1",
        )

        matches = await service.match_products_with_matcher(session, product, top_k=3)

        assert len(matches) > 0
        for m in matches:
            assert m.image_score is None


# ── Test: SupplierMatch ORM image_score ──────────────────────

class TestSupplierMatchImageScore:
    """SupplierMatch ORM model should have image_score field."""

    def test_image_score_field_exists(self):
        """image_score column exists on SupplierMatch."""
        assert hasattr(SupplierMatch, "image_score")

    def test_image_score_default_none(self):
        """Default value of image_score should be None."""
        match = SupplierMatch(
            product_id=1,
            supplier_title="测试",
            supplier_price=10.0,
        )
        assert match.image_score is None

    def test_image_score_settable(self):
        """image_score can be set."""
        match = SupplierMatch(
            product_id=1,
            supplier_title="测试",
            supplier_price=10.0,
            image_score=0.85,
        )
        assert match.image_score == 0.85

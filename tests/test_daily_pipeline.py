"""Tests for Phase 9.1 — daily pipeline, crawler_jobs, analysis_jobs."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.crawler.models.schemas import RawProduct
from app.tasks.crawler_jobs import crawl_all_platforms, DEFAULT_KEYWORDS
from app.tasks.analysis_jobs import analyze_products
from app.tasks.jobs import daily_pipeline_job
from app.tasks.scheduler import TaskScheduler


# ── Helpers ────────────────────────────────────────────────────

def _make_raw(name: str = "蓝牙耳机", platform: str = "xiaohongshu") -> RawProduct:
    return RawProduct(
        name=name,
        platform=platform,
        shop="测试店铺",
        price=99.9,
        viewers=5000,
        sales_24h=1200,
    )


# ═══════════════════════════════════════════════════════════════
# crawl_all_platforms
# ═══════════════════════════════════════════════════════════════

class TestCrawlAllPlatforms:
    """Test crawl_all_platforms function."""

    @pytest.mark.asyncio
    async def test_returns_products(self):
        """Should return RawProduct list from mocked crawlers."""
        mock_products = [_make_raw("蓝牙耳机"), _make_raw("水杯")]

        with patch("app.tasks.crawler_jobs.CrawlerManager") as mock_cls:
            mock_manager = MagicMock()
            mock_manager.crawl = AsyncMock(return_value=mock_products)
            mock_manager.close_all = AsyncMock()
            mock_manager.register = MagicMock()
            mock_cls.return_value = mock_manager

            result = await crawl_all_platforms(
                keywords=["耳机"],
                platforms=["xiaohongshu"],
            )

        assert len(result) >= 2
        assert all(isinstance(p, RawProduct) for p in result)

    @pytest.mark.asyncio
    async def test_exception_does_not_crash(self):
        """Single platform error should not interrupt others."""
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Network error")
            return [_make_raw("水杯")]

        with patch("app.tasks.crawler_jobs.CrawlerManager") as mock_cls:
            mock_manager = MagicMock()
            mock_manager.crawl = AsyncMock(side_effect=side_effect)
            mock_manager.close_all = AsyncMock()
            mock_manager.register = MagicMock()
            mock_cls.return_value = mock_manager

            result = await crawl_all_platforms(
                keywords=["测试"],
                platforms=["xiaohongshu", "douyin"],
            )

        # Second call succeeded
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_empty_crawl(self):
        """When crawlers return nothing, should return empty list."""
        with patch("app.tasks.crawler_jobs.CrawlerManager") as mock_cls:
            mock_manager = MagicMock()
            mock_manager.crawl = AsyncMock(return_value=[])
            mock_manager.close_all = AsyncMock()
            mock_manager.register = MagicMock()
            mock_cls.return_value = mock_manager

            result = await crawl_all_platforms(
                keywords=["耳机"],
                platforms=["xiaohongshu"],
            )

        assert result == []

    def test_default_keywords_not_empty(self):
        """DEFAULT_KEYWORDS should have at least one keyword."""
        assert len(DEFAULT_KEYWORDS) > 0


# ═══════════════════════════════════════════════════════════════
# analyze_products
# ═══════════════════════════════════════════════════════════════

class TestAnalyzeProducts:
    """Test analyze_products function."""

    @pytest.mark.asyncio
    async def test_empty_data(self):
        """Empty input should return zero counts without crashing."""
        mock_session = AsyncMock()

        result = await analyze_products([], mock_session)

        assert result["raw_count"] == 0
        assert result["cleaned_count"] == 0
        assert result["saved_count"] == 0

    @pytest.mark.asyncio
    async def test_with_mock_products(self):
        """Should clean, save, and create history for valid products."""
        raw_products = [
            _make_raw("蓝牙耳机降噪", "xiaohongshu"),
            _make_raw("保温水杯500ml", "douyin"),
        ]

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.refresh = AsyncMock()

        # Mock the query result: scalar_one_or_none returns None (no existing record)
        # so upsert creates new products and history snapshots are not skipped
        mock_query_result = MagicMock()
        mock_query_result.scalar_one_or_none.return_value = None
        mock_query_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_query_result)

        result = await analyze_products(raw_products, mock_session)

        assert result["raw_count"] == 2
        assert result["cleaned_count"] == 2
        assert result["saved_count"] == 2
        assert result["new_count"] == 2
        assert result["history_count"] == 2

    @pytest.mark.asyncio
    async def test_invalid_products_filtered(self):
        """Products with empty names after cleaning should be dropped."""
        raw_products = [
            _make_raw("包邮秒杀清仓", "xiaohongshu"),  # all ad words → empty name
            _make_raw("蓝牙耳机", "xiaohongshu"),  # valid
        ]

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_query_result = MagicMock()
        mock_query_result.scalar_one_or_none.return_value = None
        mock_query_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_query_result)

        result = await analyze_products(raw_products, mock_session)

        assert result["raw_count"] == 2
        # Only valid product should pass cleaning
        assert result["cleaned_count"] == 1
        assert result["saved_count"] == 1

    @pytest.mark.asyncio
    async def test_db_commit_failure(self):
        """If commit fails, should handle gracefully."""
        raw_products = [_make_raw("蓝牙耳机")]

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(side_effect=Exception("DB error"))
        mock_session.rollback = AsyncMock()

        result = await analyze_products(raw_products, mock_session)

        assert result["saved_count"] == 0


# ═══════════════════════════════════════════════════════════════
# daily_pipeline_job (deprecated)
# ═══════════════════════════════════════════════════════════════

class TestDailyPipelineJob:
    """Test daily_pipeline_job function (deprecated)."""

    @pytest.mark.asyncio
    async def test_returns_deprecated_result(self):
        """Should return a deprecation status dict."""
        with patch("app.tasks.crawler_jobs.crawl_all_platforms", new_callable=AsyncMock) as mock_crawl:
            mock_crawl.return_value = []

            result = await daily_pipeline_job(
                keywords=["测试"],
                platforms=["xiaohongshu"],
            )

        assert result["status"] == "deprecated"
        assert result["raw_count"] == 0
        assert "Use `python -m app.cli daily` instead" in result["message"]


# ═══════════════════════════════════════════════════════════════
# Scheduler integration
# ═══════════════════════════════════════════════════════════════

class TestSchedulerPipeline:
    """Test TaskScheduler.add_daily_pipeline."""

    def test_add_daily_pipeline(self):
        """Should register a daily pipeline job."""
        scheduler = TaskScheduler()
        job_id = scheduler.add_daily_pipeline(hour=8, minute=0)

        assert job_id == "daily_pipeline"
        jobs = scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["id"] == "daily_pipeline"

    def test_add_daily_pipeline_custom_hour(self):
        """Should accept custom hour from settings."""
        scheduler = TaskScheduler()
        job_id = scheduler.add_daily_pipeline(hour=10, minute=30)

        assert job_id == "daily_pipeline"

    def test_add_daily_pipeline_replaces_existing(self):
        """Adding pipeline twice should replace the old one."""
        scheduler = TaskScheduler()
        scheduler.add_daily_pipeline(hour=8)
        scheduler.add_daily_pipeline(hour=9)
        jobs = scheduler.list_jobs()
        assert len(jobs) == 1

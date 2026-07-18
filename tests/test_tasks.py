"""Tests for task scheduling module."""

import pytest
from unittest.mock import AsyncMock, patch

from app.tasks.scheduler import TaskScheduler
from app.tasks.jobs import daily_crawl_job, PLATFORM_CRAWLERS


class TestTaskScheduler:
    """Test TaskScheduler lifecycle and job management."""

    def test_add_daily_crawl(self):
        """Adding a daily crawl job should register it."""
        scheduler = TaskScheduler()
        job_id = scheduler.add_daily_crawl(
            keywords=["防晒霜", "蓝牙耳机"],
            platforms=["xiaohongshu"],
            hour=9,
            minute=30,
        )
        assert job_id == "daily_crawl"
        jobs = scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["id"] == "daily_crawl"
        assert "Daily crawl" in jobs[0]["name"]

    def test_add_multiple_jobs(self):
        """Multiple jobs with different IDs should coexist."""
        scheduler = TaskScheduler()
        scheduler.add_daily_crawl(keywords=["手机壳"], hour=9, job_id="morning_crawl")
        scheduler.add_daily_crawl(keywords=["耳机"], hour=18, job_id="evening_crawl")
        jobs = scheduler.list_jobs()
        assert len(jobs) == 2
        ids = {j["id"] for j in jobs}
        assert ids == {"morning_crawl", "evening_crawl"}

    def test_add_job_replaces_existing(self):
        """Adding a job with same ID should replace the old one."""
        scheduler = TaskScheduler()
        scheduler.add_daily_crawl(keywords=["旧关键词"], hour=9)
        scheduler.add_daily_crawl(keywords=["新关键词"], hour=9)
        jobs = scheduler.list_jobs()
        assert len(jobs) == 1

    def test_remove_job(self):
        """Removing an existing job should return True."""
        scheduler = TaskScheduler()
        scheduler.add_daily_crawl(keywords=["测试"], hour=9)
        assert scheduler.remove_job("daily_crawl") is True
        assert scheduler.list_jobs() == []

    def test_remove_nonexistent_job(self):
        """Removing a nonexistent job should return False."""
        scheduler = TaskScheduler()
        assert scheduler.remove_job("nonexistent") is False

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Scheduler should start and stop cleanly."""
        scheduler = TaskScheduler()
        scheduler.add_daily_crawl(keywords=["测试"], hour=9)
        assert scheduler.running is False

        scheduler.start()
        assert scheduler.running is True

        scheduler.stop()
        assert scheduler.running is False

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        """Starting twice should not raise."""
        scheduler = TaskScheduler()
        scheduler.add_daily_crawl(keywords=["测试"], hour=9)
        scheduler.start()
        scheduler.start()  # should not raise
        assert scheduler.running is True
        scheduler.stop()

    def test_stop_idempotent(self):
        """Stopping when not started should not raise."""
        scheduler = TaskScheduler()
        scheduler.stop()  # should not raise

    @pytest.mark.asyncio
    async def test_list_jobs_has_next_run(self):
        """Running scheduler should populate next_run_time."""
        scheduler = TaskScheduler()
        scheduler.add_daily_crawl(keywords=["测试"], hour=9)
        scheduler.start()
        jobs = scheduler.list_jobs()
        assert jobs[0]["next_run"] is not None
        assert jobs[0]["trigger"] is not None
        scheduler.stop()

    def test_add_generic_job(self):
        """Adding a generic async job should work."""
        scheduler = TaskScheduler()

        async def my_task():
            pass

        job_id = scheduler.add_job(my_task, trigger="cron", job_id="custom", name="Custom Job", hour=12)
        assert job_id == "custom"
        jobs = scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["name"] == "Custom Job"


class TestDailyCrawlJob:
    """Test the daily_crawl_job function."""

    @pytest.mark.asyncio
    async def test_no_products_returns_summary(self):
        """When crawler returns no products, should return summary with 0 counts."""
        mock_crawler = AsyncMock()
        mock_crawler.crawl = AsyncMock(return_value=[])
        mock_crawler.close = AsyncMock()

        with patch("app.tasks.jobs.CrawlerManager") as mock_manager_cls:
            mock_manager = AsyncMock()
            mock_manager.crawl = AsyncMock(return_value=[])
            mock_manager.close_all = AsyncMock()
            mock_manager.register = lambda x: None
            mock_manager_cls.return_value = mock_manager

            result = await daily_crawl_job(
                keywords=["测试"],
                platforms=["xiaohongshu"],
                save_to_db=False,
            )

        assert result["raw_count"] == 0
        assert result["cleaned_count"] == 0
        assert result["saved_count"] == 0
        assert result["top_products"] == []
        assert "job_id" in result
        assert "started_at" in result
        assert "finished_at" in result

    @pytest.mark.asyncio
    async def test_with_mock_products(self):
        """Should process mock products through the full pipeline."""
        from app.crawler.models.schemas import RawProduct

        mock_products = [
            RawProduct(name="蓝牙耳机降噪", platform="xiaohongshu", shop="数码店", price=99.9, viewers=5000, sales_24h=1200),
            RawProduct(name="保温水杯500ml", platform="xiaohongshu", shop="家居店", price=49.9, viewers=3000, sales_24h=800),
        ]

        with patch("app.tasks.jobs.CrawlerManager") as mock_manager_cls:
            mock_manager = AsyncMock()
            mock_manager.crawl = AsyncMock(return_value=mock_products)
            mock_manager.close_all = AsyncMock()
            mock_manager.register = lambda x: None
            mock_manager_cls.return_value = mock_manager

            result = await daily_crawl_job(
                keywords=["耳机"],
                platforms=["xiaohongshu"],
                save_to_db=False,
            )

        assert result["raw_count"] == 2
        assert result["cleaned_count"] == 2
        assert len(result["top_products"]) == 2
        # Top product should be the one with higher sales/viewers
        assert result["top_products"][0]["name"] == "蓝牙耳机降噪"

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Should catch and report crawl errors gracefully."""
        with patch("app.tasks.jobs.CrawlerManager") as mock_manager_cls:
            mock_manager = AsyncMock()
            mock_manager.crawl = AsyncMock(side_effect=Exception("Network error"))
            mock_manager.close_all = AsyncMock()
            mock_manager.register = lambda x: None
            mock_manager_cls.return_value = mock_manager

            result = await daily_crawl_job(
                keywords=["测试"],
                platforms=["xiaohongshu"],
                save_to_db=False,
            )

        assert len(result["errors"]) > 0
        assert "Network error" in result["errors"][0]
        assert result["raw_count"] == 0

    def test_platform_crawlers_mapping(self):
        """PLATFORM_CRAWLERS should have all 3 platforms."""
        assert "xiaohongshu" in PLATFORM_CRAWLERS
        assert "douyin" in PLATFORM_CRAWLERS
        assert "kuaishou" in PLATFORM_CRAWLERS
        assert len(PLATFORM_CRAWLERS) == 3

"""Tests for Phase 9.6.1 — Scheduler 自动采集接入."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config.settings import AppSettings
from app.tasks.jobs import auto_crawl_job
from app.tasks.scheduler import TaskScheduler


# ── 配置读取 ──────────────────────────────────────────────────


class TestCrawlSettings:
    """验证 settings 中新增的采集配置参数。"""

    def test_default_crawl_keywords(self):
        """crawl_keywords 默认值应为生产级关键词池。"""
        settings = AppSettings()
        assert settings.crawl_keywords == [
            "蓝牙耳机",
            "手机配件",
            "家居用品",
            "收纳神器",
            "宠物用品",
            "女装",
            "美妆",
        ]

    def test_default_daily_crawl_limit(self):
        """daily_crawl_limit 默认值应为 100。"""
        settings = AppSettings()
        assert settings.daily_crawl_limit == 100

    def test_default_crawl_platforms(self):
        """crawl_platforms 默认值应包含 xiaohongshu 和 taobao。"""
        settings = AppSettings()
        assert settings.crawl_platforms == ["xiaohongshu", "taobao"]

    def test_taobao_enabled_in_default_platforms(self):
        """taobao 应在默认采集平台中启用。"""
        settings = AppSettings()
        assert "taobao" in settings.crawl_platforms

    def test_xiaohongshu_preserved_in_default_platforms(self):
        """xiaohongshu 应保留在默认采集平台中。"""
        settings = AppSettings()
        assert "xiaohongshu" in settings.crawl_platforms

    def test_crawl_keywords_type(self):
        """crawl_keywords 应为 list[str]。"""
        settings = AppSettings()
        assert isinstance(settings.crawl_keywords, list)
        assert all(isinstance(k, str) for k in settings.crawl_keywords)

    def test_crawl_platforms_type(self):
        """crawl_platforms 应为 list[str]。"""
        settings = AppSettings()
        assert isinstance(settings.crawl_platforms, list)
        assert all(isinstance(p, str) for p in settings.crawl_platforms)

    def test_daily_crawl_limit_type(self):
        """daily_crawl_limit 应为 int。"""
        settings = AppSettings()
        assert isinstance(settings.daily_crawl_limit, int)


# ── auto_crawl_job ────────────────────────────────────────────


class TestAutoCrawlJob:
    """验证 auto_crawl_job 函数。"""

    @pytest.mark.asyncio
    async def test_reads_from_settings(self):
        """auto_crawl_job 应从 settings 读取 keywords 和 platforms。"""
        mock_settings = MagicMock(spec=AppSettings)
        mock_settings.crawl_keywords = ["测试关键词"]
        mock_settings.crawl_platforms = ["xiaohongshu"]

        with (
            patch("app.config.settings.get_settings", return_value=mock_settings),
            patch("app.tasks.jobs.daily_crawl_job", new_callable=AsyncMock, return_value={"saved_count": 0}) as mock_job,
        ):
            await auto_crawl_job()

        mock_job.assert_awaited_once_with(
            keywords=["测试关键词"],
            platforms=["xiaohongshu"],
            save_to_db=True,
        )

    @pytest.mark.asyncio
    async def test_returns_daily_crawl_result(self):
        """auto_crawl_job 应返回 daily_crawl_job 的结果。"""
        expected = {"saved_count": 5, "raw_count": 10, "errors": []}
        mock_settings = MagicMock(spec=AppSettings)
        mock_settings.crawl_keywords = ["好物"]
        mock_settings.crawl_platforms = ["xiaohongshu"]

        with (
            patch("app.config.settings.get_settings", return_value=mock_settings),
            patch("app.tasks.jobs.daily_crawl_job", new_callable=AsyncMock, return_value=expected),
        ):
            result = await auto_crawl_job()

        assert result == expected

    @pytest.mark.asyncio
    async def test_exception_does_not_propagate(self):
        """daily_crawl_job 抛出异常时，auto_crawl_job 不应传播异常。"""
        mock_settings = MagicMock(spec=AppSettings)
        mock_settings.crawl_keywords = ["测试"]
        mock_settings.crawl_platforms = ["xiaohongshu"]

        with (
            patch("app.config.settings.get_settings", return_value=mock_settings),
            patch("app.tasks.jobs.daily_crawl_job", new_callable=AsyncMock, side_effect=RuntimeError("crawl failed")),
        ):
            result = await auto_crawl_job()

        assert "errors" in result
        assert "crawl failed" in result["errors"][0]
        assert result["saved_count"] == 0

    @pytest.mark.asyncio
    async def test_empty_result(self):
        """daily_crawl_job 返回空结果时，auto_crawl_job 应正常返回。"""
        empty_result = {"saved_count": 0, "raw_count": 0, "errors": []}
        mock_settings = MagicMock(spec=AppSettings)
        mock_settings.crawl_keywords = ["新品"]
        mock_settings.crawl_platforms = ["douyin"]

        with (
            patch("app.config.settings.get_settings", return_value=mock_settings),
            patch("app.tasks.jobs.daily_crawl_job", new_callable=AsyncMock, return_value=empty_result),
        ):
            result = await auto_crawl_job()

        assert result["saved_count"] == 0
        assert result["raw_count"] == 0

    @pytest.mark.asyncio
    async def test_uses_default_settings(self):
        """auto_crawl_job 应使用 get_settings() 返回的默认配置。"""
        with (
            patch("app.config.settings.get_settings") as mock_get_settings,
            patch("app.tasks.jobs.daily_crawl_job", new_callable=AsyncMock, return_value={"saved_count": 0}),
        ):
            mock_get_settings.return_value = AppSettings()
            await auto_crawl_job()
            mock_get_settings.assert_called_once()


# ── Scheduler 注册 ────────────────────────────────────────────


class TestSchedulerAutoCrawl:
    """验证 TaskScheduler.add_auto_crawl() 方法。"""

    def test_add_auto_crawl_registers_job(self):
        """add_auto_crawl 应注册一个 job。"""
        scheduler = TaskScheduler()
        job_id = scheduler.add_auto_crawl()
        assert job_id == "daily_crawl"
        jobs = scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["id"] == "daily_crawl"

    def test_add_auto_crawl_custom_time(self):
        """add_auto_crawl 应支持自定义时间。"""
        scheduler = TaskScheduler()
        job_id = scheduler.add_auto_crawl(hour=3, minute=30)
        assert job_id == "daily_crawl"
        jobs = scheduler.list_jobs()
        assert len(jobs) == 1

    def test_add_auto_crawl_custom_id(self):
        """add_auto_crawl 应支持自定义 job_id。"""
        scheduler = TaskScheduler()
        job_id = scheduler.add_auto_crawl(job_id="nightly_crawl")
        assert job_id == "nightly_crawl"
        jobs = scheduler.list_jobs()
        assert jobs[0]["id"] == "nightly_crawl"

    def test_add_auto_crawl_replaces_existing(self):
        """add_auto_crawl 相同 job_id 应替换旧任务。"""
        scheduler = TaskScheduler()
        scheduler.add_auto_crawl()
        scheduler.add_auto_crawl()
        jobs = scheduler.list_jobs()
        assert len(jobs) == 1

    def test_add_auto_crawl_uses_auto_crawl_job(self):
        """add_auto_crawl 注册的 job 应使用 auto_crawl_job 函数。"""
        scheduler = TaskScheduler()
        scheduler.add_auto_crawl()
        jobs = scheduler._scheduler.get_jobs()
        assert jobs[0].func.__name__ == "auto_crawl_job"

    def test_default_hour_is_2(self):
        """add_auto_crawl 默认 hour 应为 2。"""
        import inspect
        sig = inspect.signature(TaskScheduler.add_auto_crawl)
        assert sig.parameters["hour"].default == 2

    def test_add_daily_crawl_default_hour_is_2(self):
        """add_daily_crawl 默认 hour 也应改为 2。"""
        import inspect
        sig = inspect.signature(TaskScheduler.add_daily_crawl)
        assert sig.parameters["hour"].default == 2


# ── daily_crawl_job 使用 ProductService ───────────────────────


class TestDailyCrawlJobSave:
    """验证 daily_crawl_job 保存步骤使用 ProductService。"""

    @pytest.mark.asyncio
    async def test_save_uses_product_service(self):
        """save_to_db=True 时应调用 ProductService.save_raw_products。"""
        from app.crawler.models.schemas import RawProduct

        mock_products = [
            RawProduct(
                name="蓝牙耳机降噪",
                platform="xiaohongshu",
                shop="数码店",
                price=99.9,
                viewers=5000,
                sales_24h=1200,
            ),
        ]

        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_svc = AsyncMock()
        mock_svc.save_raw_products = AsyncMock(return_value={
            "total": 1, "cleaned_count": 1, "saved_count": 1,
            "new_count": 1, "updated_count": 0, "history_count": 1,
            "failed_count": 0,
        })

        with (
            patch("app.tasks.jobs.CrawlerManager") as mock_manager_cls,
            patch("app.database.base.get_async_session_factory", return_value=mock_factory),
            patch("app.services.product_service.ProductService", return_value=mock_svc),
        ):
            mock_manager = AsyncMock()
            mock_manager.crawl = AsyncMock(return_value=mock_products)
            mock_manager.close_all = AsyncMock()
            mock_manager.register = lambda x: None
            mock_manager_cls.return_value = mock_manager

            from app.tasks.jobs import daily_crawl_job
            result = await daily_crawl_job(
                keywords=["耳机"],
                platforms=["xiaohongshu"],
                save_to_db=True,
            )

        mock_svc.save_raw_products.assert_awaited_once()
        assert result["saved_count"] == 1

    @pytest.mark.asyncio
    async def test_save_error_does_not_stop_job(self):
        """保存步骤异常不应中断 job，应记录在 errors 中。"""
        from app.crawler.models.schemas import RawProduct

        mock_products = [
            RawProduct(
                name="保温杯",
                platform="xiaohongshu",
                shop="家居店",
                price=49.9,
                viewers=3000,
                sales_24h=800,
            ),
        ]

        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.tasks.jobs.CrawlerManager") as mock_manager_cls,
            patch("app.database.base.get_async_session_factory", return_value=mock_factory),
            patch("app.services.product_service.ProductService", side_effect=RuntimeError("DB error")),
        ):
            mock_manager = AsyncMock()
            mock_manager.crawl = AsyncMock(return_value=mock_products)
            mock_manager.close_all = AsyncMock()
            mock_manager.register = lambda x: None
            mock_manager_cls.return_value = mock_manager

            from app.tasks.jobs import daily_crawl_job
            result = await daily_crawl_job(
                keywords=["水杯"],
                platforms=["xiaohongshu"],
                save_to_db=True,
            )

        assert result["raw_count"] == 1
        assert any("DB error" in e for e in result["errors"])

"""Tests for Phase 9.7.5 — CrawlLog model, repository, and crawler API.

Covers: CrawlLog ORM, CrawlLogRepository CRUD, GET /crawler/status, GET /crawler/logs.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database.base import Base
from app.models.crawl_log import CrawlLog
from app.database.crawl_log_repository import CrawlLogRepository


# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
async def session():
    """Create an in-memory SQLite async session for testing."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


# ── TestCrawlLogModel ─────────────────────────────────────────


class TestCrawlLogModel:
    """CrawlLog ORM model fields and defaults."""

    @pytest.mark.anyio
    async def test_create_basic(self, session):
        log = CrawlLog(keyword="蓝牙耳机", platform="xiaohongshu")
        session.add(log)
        await session.flush()
        assert log.id is not None

    @pytest.mark.anyio
    async def test_defaults(self, session):
        log = CrawlLog(keyword="测试", platform="xiaohongshu")
        session.add(log)
        await session.flush()
        assert log.total == 0
        assert log.success == 0
        assert log.failed == 0
        assert log.status == "RUNNING"
        assert log.error is None
        assert log.end_time is None

    @pytest.mark.anyio
    async def test_all_fields(self, session):
        log = CrawlLog(
            keyword="蓝牙耳机",
            platform="xiaohongshu",
            total=100,
            success=95,
            failed=5,
            status="SUCCESS",
            error=None,
        )
        session.add(log)
        await session.flush()

        stmt = select(CrawlLog).where(CrawlLog.id == log.id)
        result = await session.execute(stmt)
        fetched = result.scalar_one()
        assert fetched.keyword == "蓝牙耳机"
        assert fetched.platform == "xiaohongshu"
        assert fetched.total == 100
        assert fetched.success == 95
        assert fetched.failed == 5
        assert fetched.status == "SUCCESS"

    @pytest.mark.anyio
    async def test_repr(self):
        log = CrawlLog(id=1, keyword="test", platform="xhs", status="SUCCESS")
        assert "CrawlLog" in repr(log)
        assert "test" in repr(log)


# ── TestCrawlLogRepository ─────────────────────────────────────


class TestCrawlLogRepository:
    """CrawlLogRepository create/update/query."""

    @pytest.mark.anyio
    async def test_create(self, session):
        repo = CrawlLogRepository(session)
        log = CrawlLog(keyword="家居用品", platform="xiaohongshu")
        created = await repo.create(log)
        assert created.id is not None
        assert created.keyword == "家居用品"

    @pytest.mark.anyio
    async def test_update_status(self, session):
        repo = CrawlLogRepository(session)
        log = CrawlLog(keyword="test", platform="xhs", status="RUNNING")
        created = await repo.create(log)

        updated = await repo.update_status(
            created.id,
            status="SUCCESS",
            total=50,
            success=48,
            failed=2,
        )
        assert updated is not None
        assert updated.status == "SUCCESS"
        assert updated.total == 50
        assert updated.success == 48
        assert updated.failed == 2
        assert updated.end_time is not None

    @pytest.mark.anyio
    async def test_update_status_with_error(self, session):
        repo = CrawlLogRepository(session)
        log = CrawlLog(keyword="test", platform="xhs")
        created = await repo.create(log)

        updated = await repo.update_status(
            created.id,
            status="FAILED",
            error="timeout",
        )
        assert updated is not None
        assert updated.status == "FAILED"
        assert updated.error == "timeout"

    @pytest.mark.anyio
    async def test_update_nonexistent_returns_none(self, session):
        repo = CrawlLogRepository(session)
        result = await repo.update_status(9999, status="SUCCESS")
        assert result is None

    @pytest.mark.anyio
    async def test_get_logs_default(self, session):
        repo = CrawlLogRepository(session)
        for i in range(3):
            await repo.create(CrawlLog(keyword=f"kw{i}", platform="xhs"))

        logs = await repo.get_logs()
        assert len(logs) == 3

    @pytest.mark.anyio
    async def test_get_logs_limit(self, session):
        repo = CrawlLogRepository(session)
        for i in range(5):
            await repo.create(CrawlLog(keyword=f"kw{i}", platform="xhs"))

        logs = await repo.get_logs(limit=2)
        assert len(logs) == 2

    @pytest.mark.anyio
    async def test_get_logs_filter_platform(self, session):
        repo = CrawlLogRepository(session)
        await repo.create(CrawlLog(keyword="kw1", platform="xiaohongshu"))
        await repo.create(CrawlLog(keyword="kw2", platform="douyin"))
        await repo.create(CrawlLog(keyword="kw3", platform="xiaohongshu"))

        logs = await repo.get_logs(platform="xiaohongshu")
        assert len(logs) == 2
        for log in logs:
            assert log.platform == "xiaohongshu"

    @pytest.mark.anyio
    async def test_get_logs_ordered_desc(self, session):
        repo = CrawlLogRepository(session)
        # Use explicit timestamps to ensure deterministic ordering
        from datetime import timedelta
        base = datetime(2026, 7, 19, 8, 0, 0)
        for i, kw in enumerate(["first", "second", "third"]):
            log = CrawlLog(keyword=kw, platform="xhs", start_time=base + timedelta(seconds=i))
            await repo.create(log)

        logs = await repo.get_logs()
        # DESC order by start_time — last inserted first
        assert logs[0].keyword == "third"


# ── TestCrawlerAPI ─────────────────────────────────────────────


class _FakeSessionCtx:
    """Fake async context manager for session factory."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        return False


class TestCrawlerAPI:
    """GET /crawler/status and GET /crawler/logs API endpoints."""

    @pytest.mark.anyio
    async def test_crawler_status_endpoint(self):
        """Status endpoint returns serialized records."""
        fake_records = [
            MagicMock(
                id=1, platform="daily_crawl",
                last_run_time=datetime(2026, 7, 19, 8, 0),
                status="SUCCESS", total=100, success=95, failed=5,
                message=None,
            ),
        ]

        mock_session = AsyncMock()
        fake_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

        with patch("app.api.crawler.get_async_session_factory", return_value=fake_factory):
            with patch(
                "app.api.crawler.CrawlerStatusRepository"
            ) as MockRepo:
                instance = MockRepo.return_value
                instance.get_latest = AsyncMock(return_value=fake_records)

                from app.api.crawler import crawler_status
                result = await crawler_status()

        assert len(result) == 1
        assert result[0]["platform"] == "daily_crawl"
        assert result[0]["status"] == "SUCCESS"
        assert result[0]["total"] == 100

    @pytest.mark.anyio
    async def test_crawler_logs_endpoint(self):
        """Logs endpoint returns serialized records."""
        fake_records = [
            MagicMock(
                id=1, keyword="蓝牙耳机", platform="xiaohongshu",
                start_time=datetime(2026, 7, 19, 8, 0),
                end_time=datetime(2026, 7, 19, 8, 5),
                total=50, success=48, failed=2,
                status="SUCCESS", error=None,
            ),
        ]

        mock_session = AsyncMock()
        fake_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

        with patch("app.api.crawler.get_async_session_factory", return_value=fake_factory):
            with patch(
                "app.api.crawler.CrawlLogRepository"
            ) as MockRepo:
                instance = MockRepo.return_value
                instance.get_logs = AsyncMock(return_value=fake_records)

                from app.api.crawler import crawler_logs
                result = await crawler_logs(limit=20)

        assert len(result) == 1
        assert result[0]["keyword"] == "蓝牙耳机"
        assert result[0]["platform"] == "xiaohongshu"
        assert result[0]["total"] == 50

    @pytest.mark.anyio
    async def test_crawler_logs_with_platform_filter(self):
        """Logs endpoint passes platform filter."""
        mock_session = AsyncMock()
        fake_factory = MagicMock(return_value=_FakeSessionCtx(mock_session))

        with patch("app.api.crawler.get_async_session_factory", return_value=fake_factory):
            with patch(
                "app.api.crawler.CrawlLogRepository"
            ) as MockRepo:
                instance = MockRepo.return_value
                instance.get_logs = AsyncMock(return_value=[])

                from app.api.crawler import crawler_logs
                result = await crawler_logs(limit=10, platform="douyin")

        instance.get_logs.assert_called_once_with(limit=10, platform="douyin")
        assert result == []

    @pytest.mark.anyio
    async def test_crawler_status_error_returns_500(self):
        """Status endpoint returns 500 on exception."""
        fake_factory = MagicMock(side_effect=RuntimeError("db error"))

        with patch("app.api.crawler.get_async_session_factory", return_value=fake_factory):
            from app.api.crawler import crawler_status
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await crawler_status()
            assert exc_info.value.status_code == 500

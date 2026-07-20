"""Tests for CrawlerStatus model and repository."""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.crawler_status_repository import CrawlerStatusRepository
from app.models.crawler_status import CrawlerStatus

# ensure models registered
import app.models  # noqa: F401


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── Create ───────────────────────────────────────────────────


class TestCreate:
    """运行状态保存。"""

    @pytest.mark.anyio
    async def test_create_running(self, session):
        """应能创建 RUNNING 状态记录。"""
        repo = CrawlerStatusRepository(session)
        record = CrawlerStatus(
            platform="xiaohongshu",
            status="RUNNING",
            total=0,
        )
        created = await repo.create(record)
        await session.commit()

        assert created.id is not None
        assert created.platform == "xiaohongshu"
        assert created.status == "RUNNING"

    @pytest.mark.anyio
    async def test_create_with_message(self, session):
        """应能保存带 message 的记录。"""
        repo = CrawlerStatusRepository(session)
        record = CrawlerStatus(
            platform="douyin",
            status="FAILED",
            total=100,
            success=80,
            failed=20,
            message="Connection timeout",
        )
        created = await repo.create(record)
        await session.commit()

        assert created.message == "Connection timeout"
        assert created.failed == 20


# ── Update ───────────────────────────────────────────────────


class TestUpdate:
    """状态更新。"""

    @pytest.mark.anyio
    async def test_update_to_success(self, session):
        """RUNNING → SUCCESS。"""
        repo = CrawlerStatusRepository(session)
        record = CrawlerStatus(platform="xhs", status="RUNNING", total=0)
        created = await repo.create(record)
        await session.commit()

        updated = await repo.update_status(
            created.id,
            status="SUCCESS",
            total=100,
            success=95,
            failed=5,
        )
        await session.commit()

        assert updated is not None
        assert updated.status == "SUCCESS"
        assert updated.total == 100
        assert updated.success == 95
        assert updated.failed == 5

    @pytest.mark.anyio
    async def test_update_to_failed(self, session):
        """RUNNING → FAILED with message。"""
        repo = CrawlerStatusRepository(session)
        record = CrawlerStatus(platform="xhs", status="RUNNING", total=0)
        created = await repo.create(record)
        await session.commit()

        updated = await repo.update_status(
            created.id,
            status="FAILED",
            total=100,
            success=50,
            failed=50,
            message="Rate limit exceeded",
        )
        await session.commit()

        assert updated is not None
        assert updated.status == "FAILED"
        assert updated.message == "Rate limit exceeded"

    @pytest.mark.anyio
    async def test_update_nonexistent(self, session):
        """更新不存在的记录应返回 None。"""
        repo = CrawlerStatusRepository(session)
        result = await repo.update_status(9999, status="SUCCESS")
        assert result is None


# ── Query ────────────────────────────────────────────────────


class TestQuery:
    """查询最近记录。"""

    @pytest.mark.anyio
    async def test_get_latest_empty(self, session):
        """无记录时返回空列表。"""
        repo = CrawlerStatusRepository(session)
        records = await repo.get_latest()
        assert records == []

    @pytest.mark.anyio
    async def test_get_latest_ordered(self, session):
        """应按时间降序排列。"""
        repo = CrawlerStatusRepository(session)
        base_time = datetime(2026, 7, 19, 12, 0, 0)
        for i, platform in enumerate(["xhs", "douyin", "kuaishou"]):
            record = CrawlerStatus(
                platform=platform,
                status="SUCCESS",
                total=10,
                last_run_time=datetime(base_time.year, base_time.month, base_time.day, base_time.hour, base_time.minute, i),
            )
            await repo.create(record)
        await session.commit()

        records = await repo.get_latest()
        assert len(records) == 3
        # Latest first
        assert records[0].platform == "kuaishou"

    @pytest.mark.anyio
    async def test_get_latest_with_limit(self, session):
        """应支持 limit 参数。"""
        repo = CrawlerStatusRepository(session)
        for i in range(5):
            record = CrawlerStatus(platform=f"p{i}", status="SUCCESS", total=10)
            await repo.create(record)
        await session.commit()

        records = await repo.get_latest(limit=2)
        assert len(records) == 2

"""Tests for Phase 46.4 + 47.1 — Recommendation Publish Pipeline + Publisher Architecture.

覆盖：
- Repository: 创建记录、标记成功、标记失败、查询历史
- Service: NEW/REJECTED 禁止发布、APPROVED 可发布、失败保持 APPROVED
- API: POST publish、GET publish-history
- Publisher: MockPublisher success/failure、Factory routing、Service injection
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.models.daily_report import DailyReport, DailyReportItem
from app.models.product import Product
from app.models.recommendation_publish_record import (
    PublishStatus,
    RecommendationPublishRecord,
)
from app.models.recommendation_status import PoolStatus, RecommendationStatus
from app.database.recommendation_publish_repository import (
    RecommendationPublishRepository,
)
from app.services.recommendation.publish_service import (
    RecommendationPublishService,
)
from app.publishers.mock_publisher import MockPublisher, PublishContext, PublishResult

import app.models  # noqa: F401


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as sess:
        yield sess

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def publish_repo(session: AsyncSession) -> RecommendationPublishRepository:
    return RecommendationPublishRepository(session)


@pytest.fixture
def publish_service(session: AsyncSession) -> RecommendationPublishService:
    return RecommendationPublishService(session)


# ── Seed helpers ──────────────────────────────────────────


async def _seed_product(
    session: AsyncSession, name: str = "测试", **kw
) -> Product:
    p = Product(
        name=name,
        platform=kw.get("platform", "taobao"),
        shop=kw.get("shop", "测试店铺"),
        price=kw.get("price", 99.0),
    )
    session.add(p)
    await session.flush()
    return p


async def _seed_status(
    session: AsyncSession,
    product_id: int,
    report_date: date,
    status: PoolStatus,
) -> RecommendationStatus:
    rs = RecommendationStatus(
        product_id=product_id,
        report_date=report_date,
        status=status.value,
    )
    session.add(rs)
    await session.flush()
    return rs


async def _seed_daily_report(
    session: AsyncSession,
    report_date: date,
    product_id: int,
) -> None:
    report = DailyReport(
        report_date=report_date, total=1, hot_products=0,
        potential_products=0, average_score=0.0,
    )
    session.add(report)
    await session.flush()

    item = DailyReportItem(
        report_id=report.id,
        product_id=product_id,
        rank=1,
        name="Test",
        platform="taobao",
        image="",
        price=99.0,
        score=80,
        level="A",
        reasons="[]",
    )
    session.add(item)
    await session.flush()


# ═══════════════════════════════════════════════════════════════
# Repository Tests
# ═══════════════════════════════════════════════════════════════


class TestPublishRepository:
    """发布记录 Repository 测试。"""

    @pytest.mark.anyio
    async def test_create_record(self, publish_repo):
        record = await publish_repo.create_record(product_id=1, platform="taobao")
        assert record.id is not None
        assert record.product_id == 1
        assert record.status == PublishStatus.PENDING.value
        assert record.platform == "taobao"
        assert record.retry_count == 0

    @pytest.mark.anyio
    async def test_mark_success(self, publish_repo):
        record = await publish_repo.create_record(product_id=1)
        updated = await publish_repo.mark_success(record.id)
        assert updated.status == PublishStatus.SUCCESS.value
        assert updated.published_at is not None

    @pytest.mark.anyio
    async def test_mark_failed(self, publish_repo):
        record = await publish_repo.create_record(product_id=1)
        updated = await publish_repo.mark_failed(record.id, "test error")
        assert updated.status == PublishStatus.FAILED.value
        assert updated.error_message == "test error"
        assert updated.retry_count == 1

    @pytest.mark.anyio
    async def test_get_history(self, publish_repo):
        r1 = await publish_repo.create_record(product_id=10)
        r2 = await publish_repo.create_record(product_id=10)
        history = await publish_repo.get_history(product_id=10)
        assert len(history) == 2
        ids = {r.id for r in history}
        assert r1.id in ids and r2.id in ids

    @pytest.mark.anyio
    async def test_get_history_empty(self, publish_repo):
        history = await publish_repo.get_history(product_id=999)
        assert history == []

    @pytest.mark.anyio
    async def test_get_latest(self, publish_repo):
        await publish_repo.create_record(product_id=5)
        r2 = await publish_repo.create_record(product_id=5)
        latest = await publish_repo.get_latest(product_id=5)
        assert latest is not None
        assert latest.id == r2.id  # 最新记录按 id 降序

    @pytest.mark.anyio
    async def test_mark_success_nonexistent(self, publish_repo):
        with pytest.raises(ValueError, match="不存在"):
            await publish_repo.mark_success(99999)

    @pytest.mark.anyio
    async def test_mark_failed_nonexistent(self, publish_repo):
        with pytest.raises(ValueError, match="不存在"):
            await publish_repo.mark_failed(99999, "err")


# ═══════════════════════════════════════════════════════════════
# Service Tests
# ═══════════════════════════════════════════════════════════════


class TestPublishService:
    """PublishService 业务规则测试。"""

    @pytest.mark.anyio
    async def test_new_cannot_publish(self, session, publish_service):
        """NEW 状态禁止发布。"""
        p = await _seed_product(session, "NEW商品")
        today = date.today()
        await _seed_status(session, p.id, today, PoolStatus.NEW)
        await _seed_daily_report(session, today, p.id)

        with pytest.raises(ValueError, match="APPROVED"):
            await publish_service.publish(p.id)

    @pytest.mark.anyio
    async def test_rejected_cannot_publish(self, session, publish_service):
        """REJECTED 状态禁止发布。"""
        p = await _seed_product(session, "REJECTED商品")
        today = date.today()
        await _seed_status(session, p.id, today, PoolStatus.REJECTED)
        await _seed_daily_report(session, today, p.id)

        with pytest.raises(ValueError, match="APPROVED"):
            await publish_service.publish(p.id)

    @pytest.mark.anyio
    async def test_reviewed_cannot_publish(self, session, publish_service):
        """REVIEWED 状态禁止发布。"""
        p = await _seed_product(session, "REVIEWED商品")
        today = date.today()
        await _seed_status(session, p.id, today, PoolStatus.REVIEWED)
        await _seed_daily_report(session, today, p.id)

        with pytest.raises(ValueError, match="APPROVED"):
            await publish_service.publish(p.id)

    @pytest.mark.anyio
    async def test_published_cannot_publish(self, session, publish_service):
        """PUBLISHED 状态禁止重复发布。"""
        p = await _seed_product(session, "PUBLISHED商品")
        today = date.today()
        await _seed_status(session, p.id, today, PoolStatus.PUBLISHED)
        await _seed_daily_report(session, today, p.id)

        with pytest.raises(ValueError, match="APPROVED"):
            await publish_service.publish(p.id)

    @pytest.mark.anyio
    async def test_approved_publish_creates_record(self, session, publish_service):
        """APPROVED → 创建发布记录。"""
        p = await _seed_product(session, "可发布")
        today = date.today()
        await _seed_status(session, p.id, today, PoolStatus.APPROVED)
        await _seed_daily_report(session, today, p.id)

        result = await publish_service.publish(p.id)
        assert result["product_id"] == p.id
        assert "record_id" in result
        assert "publish_status" in result

        # 验证记录存在
        history = await publish_service.get_publish_history(p.id)
        assert len(history) >= 1

    @pytest.mark.anyio
    async def test_no_status_cannot_publish(self, session, publish_service):
        """无 recommendation_status → 禁止发布。"""
        p = await _seed_product(session, "无状态")
        today = date.today()
        await _seed_daily_report(session, today, p.id)

        with pytest.raises(ValueError, match="尚未进入推荐池"):
            await publish_service.publish(p.id)

    @pytest.mark.anyio
    async def test_get_publish_history(self, session, publish_service):
        """查询发布历史。"""
        p = await _seed_product(session, "历史商品")
        today = date.today()
        await _seed_status(session, p.id, today, PoolStatus.APPROVED)
        await _seed_daily_report(session, today, p.id)

        await publish_service.publish(p.id)

        history = await publish_service.get_publish_history(p.id)
        assert len(history) >= 1
        record = history[0]
        assert record["product_id"] == p.id
        assert "status" in record
        assert "platform" in record
        assert "created_at" in record


# ═══════════════════════════════════════════════════════════════
# API Tests
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
async def api_session_factory():
    """In-memory session factory for API tests (shared cache)."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///file::memory:?cache=shared&uri=true", echo=False
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    yield factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


class TestPublishAPI:
    """API 端点测试。"""

    @pytest.mark.anyio
    async def test_post_publish_not_approved(self, api_session_factory):
        """非 APPROVED 状态 → 422。"""
        today = date.today()

        async with api_session_factory() as sess:
            p = await _seed_product(sess, "未通过")
            await _seed_status(sess, p.id, today, PoolStatus.NEW)
            await _seed_daily_report(sess, today, p.id)
            await sess.commit()

        from app.api.main import app

        with patch(
            "app.api.recommendation_pool.get_async_session_factory",
            return_value=api_session_factory,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/recommendation-pool/{p.id}/publish",
                    params={"report_date": today.isoformat()},
                )
                assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_post_publish_approved(self, api_session_factory):
        """APPROVED → 200 + 发布记录。"""
        today = date.today()

        async with api_session_factory() as sess:
            p = await _seed_product(sess, "可发布API")
            await _seed_status(sess, p.id, today, PoolStatus.APPROVED)
            await _seed_daily_report(sess, today, p.id)
            await sess.commit()

        from app.api.main import app

        with patch(
            "app.api.recommendation_pool.get_async_session_factory",
            return_value=api_session_factory,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/recommendation-pool/{p.id}/publish",
                    params={"report_date": today.isoformat()},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert "success" in data
                assert "record_id" in data

    @pytest.mark.anyio
    async def test_get_publish_history(self, api_session_factory):
        """GET publish-history。"""
        today = date.today()

        async with api_session_factory() as sess:
            p = await _seed_product(sess, "历史API")
            await _seed_status(sess, p.id, today, PoolStatus.APPROVED)
            await _seed_daily_report(sess, today, p.id)

            # 创建一个发布记录
            from app.database.recommendation_publish_repository import (
                RecommendationPublishRepository,
            )
            repo = RecommendationPublishRepository(sess)
            await repo.create_record(p.id, "taobao")
            await sess.commit()

        from app.api.main import app

        with patch(
            "app.api.recommendation_pool.get_async_session_factory",
            return_value=api_session_factory,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.get(
                    f"/recommendation-pool/{p.id}/publish-history"
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["product_id"] == p.id
                assert data["total"] >= 1
                assert len(data["records"]) >= 1

    @pytest.mark.anyio
    async def test_get_publish_history_empty(self, api_session_factory):
        """无发布记录的商品 → 空列表。"""
        from app.api.main import app

        with patch(
            "app.api.recommendation_pool.get_async_session_factory",
            return_value=api_session_factory,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/recommendation-pool/99999/publish-history"
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["total"] == 0

    @pytest.mark.anyio
    async def test_publish_history_correct_date(self, api_session_factory):
        """验证发布历史时间戳不为空。"""
        today = date.today()

        async with api_session_factory() as sess:
            p = await _seed_product(sess, "时间戳测试")
            await _seed_status(sess, p.id, today, PoolStatus.APPROVED)
            await _seed_daily_report(sess, today, p.id)
            await sess.commit()

        from app.api.main import app

        with patch(
            "app.api.recommendation_pool.get_async_session_factory",
            return_value=api_session_factory,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                # Use mocked random to ensure success
                with patch("random.random", return_value=0.01):
                    resp = await client.post(
                        f"/recommendation-pool/{p.id}/publish",
                        params={"report_date": today.isoformat()},
                    )
                    assert resp.status_code == 200
                    data = resp.json()
                    assert data["success"] is True
                    assert data["published_at"] is not None


# ═══════════════════════════════════════════════════════════════
# Publisher Architecture Tests (Phase 47.1)
# ═══════════════════════════════════════════════════════════════


class TestMockPublisher:
    """MockPublisher 单元测试。"""

    @pytest.mark.anyio
    async def test_mock_publisher_success(self):
        """MockPublisher 成功场景。"""
        pub = MockPublisher(success_rate=1.0)
        ctx = PublishContext(
            product_id=1,
            platform="taobao",
            report_date=date.today(),
        )
        result = await pub.publish(ctx)
        assert result.success is True
        assert result.platform == "taobao"
        assert "成功" in result.message
        assert result.external_id is not None
        assert result.published_at is not None

    @pytest.mark.anyio
    async def test_mock_publisher_failure(self):
        """MockPublisher 失败场景。"""
        pub = MockPublisher(success_rate=0.0)
        ctx = PublishContext(
            product_id=2,
            platform="taobao",
            report_date=date.today(),
        )
        result = await pub.publish(ctx)
        assert result.success is False
        assert result.platform == "taobao"
        assert "失败" in result.message
        assert result.external_id is None
        assert result.published_at is None


class TestPublishServiceWithPublisherInjection:
    """PublishService + Publisher 注入测试。"""

    @pytest.mark.anyio
    async def test_injected_publisher_success(self, session):
        """注入 MockPublisher(success_rate=1.0) → 发布成功 + status→PUBLISHED。"""
        p = await _seed_product(session, "注入成功")
        today = date.today()
        await _seed_status(session, p.id, today, PoolStatus.APPROVED)
        await _seed_daily_report(session, today, p.id)

        pub = MockPublisher(success_rate=1.0)
        svc = RecommendationPublishService(session, publisher=pub)
        result = await svc.publish(p.id)

        assert result["success"] is True
        assert result["publish_status"] == PublishStatus.SUCCESS.value
        assert "published_at" in result

        # 验证 RecommendationStatus → PUBLISHED
        from app.database.recommendation_status_repository import (
            RecommendationStatusRepository,
        )
        status_repo = RecommendationStatusRepository(session)
        status = await status_repo.get_status(p.id, today)
        assert status is not None
        assert status.status == PoolStatus.PUBLISHED.value

    @pytest.mark.anyio
    async def test_injected_publisher_failure(self, session):
        """注入 MockPublisher(success_rate=0.0) → 发布失败 + status 保持 APPROVED。"""
        p = await _seed_product(session, "注入失败")
        today = date.today()
        await _seed_status(session, p.id, today, PoolStatus.APPROVED)
        await _seed_daily_report(session, today, p.id)

        pub = MockPublisher(success_rate=0.0)
        svc = RecommendationPublishService(session, publisher=pub)
        result = await svc.publish(p.id)

        assert result["success"] is False
        assert result["publish_status"] == PublishStatus.FAILED.value

        # 验证 RecommendationStatus 保持 APPROVED
        from app.database.recommendation_status_repository import (
            RecommendationStatusRepository,
        )
        status_repo = RecommendationStatusRepository(session)
        status = await status_repo.get_status(p.id, today)
        assert status is not None
        assert status.status == PoolStatus.APPROVED.value

    @pytest.mark.anyio
    async def test_injected_publisher_still_validates_status(self, session):
        """即使注入 Publisher，状态校验仍然生效。"""
        p = await _seed_product(session, "状态校验")
        today = date.today()
        await _seed_status(session, p.id, today, PoolStatus.NEW)
        await _seed_daily_report(session, today, p.id)

        pub = MockPublisher(success_rate=1.0)
        svc = RecommendationPublishService(session, publisher=pub)

        with pytest.raises(ValueError, match="APPROVED"):
            await svc.publish(p.id)

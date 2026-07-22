"""Tests for Phase 46.3 — RecommendationPoolInitializer.

覆盖：
- 空日报（无 DailyReportItem）
- 新商品初始化（全部创建 NEW）
- 已存在状态跳过（部分已在 recommendation_status）
- 幂等执行（重复调用不重复创建）
- API 端到端验证（同步后推荐池可查询）
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.models.daily_report import DailyReport, DailyReportItem
from app.models.product import Product
from app.models.recommendation_status import PoolStatus, RecommendationStatus
from app.services.recommendation.pool_initializer import (
    RecommendationPoolInitializer,
)

import app.models  # noqa: F401


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
async def session() -> AsyncSession:
    """In-memory SQLite session with all tables."""
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
def initializer(session: AsyncSession) -> RecommendationPoolInitializer:
    return RecommendationPoolInitializer(session)


# ── Seed helpers ──────────────────────────────────────────


async def _seed_product(session: AsyncSession, name: str = "测试", **kw) -> Product:
    p = Product(
        name=name,
        platform=kw.get("platform", "taobao"),
        shop=kw.get("shop", "测试店铺"),
        price=kw.get("price", 99.0),
        image=kw.get("image", "http://x.com/1.jpg"),
    )
    session.add(p)
    await session.flush()
    return p


async def _seed_report_with_items(
    session: AsyncSession,
    report_date: date,
    products: list[Product],
) -> DailyReport:
    """创建日报及其 items。"""
    report = DailyReport(
        report_date=report_date,
        total=len(products),
        hot_products=0,
        potential_products=0,
        average_score=0.0,
    )
    session.add(report)
    await session.flush()

    for rank, p in enumerate(products, 1):
        item = DailyReportItem(
            report_id=report.id,
            product_id=p.id,
            rank=rank,
            name=p.name,
            platform=p.platform,
            image=p.image or "",
            price=p.price,
            score=70,
            level="A",
            reasons='["热销"]',
        )
        session.add(item)
    await session.flush()
    return report


# ═══════════════════════════════════════════════════════════════
# Core Tests
# ═══════════════════════════════════════════════════════════════


class TestEmptyReport:
    """空日报 — 无数据时正常返回。"""

    @pytest.mark.anyio
    async def test_empty_report_returns_zero(self, initializer):
        future_date = date.today() + timedelta(days=365)
        result = await initializer.sync(future_date)
        assert result["total"] == 0
        assert result["synced"] == 0
        assert result["skipped"] == 0
        assert result["report_date"] == future_date.isoformat()


class TestNewProductInit:
    """新商品初始化 — 全量创建 NEW 状态。"""

    @pytest.mark.anyio
    async def test_new_products_all_created(self, session, initializer):
        today = date.today()
        p1 = await _seed_product(session, name="商品A")
        p2 = await _seed_product(session, name="商品B")
        p3 = await _seed_product(session, name="商品C")
        await _seed_report_with_items(session, today, [p1, p2, p3])

        result = await initializer.sync(today)
        assert result["total"] == 3
        assert result["synced"] == 3
        assert result["skipped"] == 0

        # 验证 DB 中存在 3 条 NEW 记录
        from sqlalchemy import select

        stmt = select(RecommendationStatus).where(
            RecommendationStatus.report_date == today
        )
        rows = (await session.execute(stmt)).scalars().all()
        assert len(rows) == 3
        for r in rows:
            assert r.status == PoolStatus.NEW.value
            assert r.product_id in {p1.id, p2.id, p3.id}

    @pytest.mark.anyio
    async def test_one_product(self, session, initializer):
        """单个商品也正常初始化。"""
        today = date.today()
        p = await _seed_product(session, name="单商品")
        await _seed_report_with_items(session, today, [p])

        result = await initializer.sync(today)
        assert result["total"] == 1
        assert result["synced"] == 1
        assert result["skipped"] == 0


class TestSkipExisting:
    """已有状态 — 跳过已存在的记录。"""

    @pytest.mark.anyio
    async def test_partial_skip(self, session, initializer):
        today = date.today()
        p1 = await _seed_product(session, name="新商品")
        p2 = await _seed_product(session, name="已审核")
        await _seed_report_with_items(session, today, [p1, p2])

        # 预置 p2 的 APPROVED 状态
        from app.database.recommendation_status_repository import (
            RecommendationStatusRepository,
        )
        repo = RecommendationStatusRepository(session)
        await repo.upsert_status(p2.id, today, PoolStatus.APPROVED)

        result = await initializer.sync(today)
        assert result["total"] == 2
        assert result["synced"] == 1  # 只有 p1
        assert result["skipped"] == 1

        # p2 状态未被覆盖
        status_p2 = await repo.get_status(p2.id, today)
        assert status_p2 is not None
        assert status_p2.status == PoolStatus.APPROVED.value

    @pytest.mark.anyio
    async def test_all_already_exist(self, session, initializer):
        """全部已有状态 → 全部跳过。"""
        today = date.today()
        p1 = await _seed_product(session, name="已审1")
        p2 = await _seed_product(session, name="已审2")
        await _seed_report_with_items(session, today, [p1, p2])

        from app.database.recommendation_status_repository import (
            RecommendationStatusRepository,
        )
        repo = RecommendationStatusRepository(session)
        await repo.upsert_status(p1.id, today, PoolStatus.APPROVED)
        await repo.upsert_status(p2.id, today, PoolStatus.REJECTED)

        result = await initializer.sync(today)
        assert result["total"] == 2
        assert result["synced"] == 0
        assert result["skipped"] == 2


class TestIdempotent:
    """幂等性 — 多次执行结果一致。"""

    @pytest.mark.anyio
    async def test_twice_same_result(self, session, initializer):
        today = date.today()
        p = await _seed_product(session, name="幂等测试")
        await _seed_report_with_items(session, today, [p])

        r1 = await initializer.sync(today)
        assert r1["synced"] == 1
        assert r1["skipped"] == 0

        r2 = await initializer.sync(today)
        assert r2["synced"] == 0
        assert r2["skipped"] == 1

        # DB 只有一条记录
        from sqlalchemy import select

        stmt = select(RecommendationStatus).where(
            RecommendationStatus.report_date == today
        )
        rows = (await session.execute(stmt)).scalars().all()
        assert len(rows) == 1

    @pytest.mark.anyio
    async def test_triple_same(self, session, initializer):
        """三次执行结果一致。"""
        today = date.today()
        p1 = await _seed_product(session, name="三_1")
        p2 = await _seed_product(session, name="三_2")
        await _seed_report_with_items(session, today, [p1, p2])

        for i in range(3):
            r = await initializer.sync(today)
            if i == 0:
                assert r["synced"] == 2
            else:
                assert r["synced"] == 0
                assert r["skipped"] == 2

    @pytest.mark.anyio
    async def test_different_dates(self, session, initializer):
        """不同日期各自初始化。"""
        d1 = date.today()
        d2 = d1 - timedelta(days=1)
        p = await _seed_product(session, name="跨日商品")
        await _seed_report_with_items(session, d1, [p])
        await _seed_report_with_items(session, d2, [p])

        r1 = await initializer.sync(d1)
        assert r1["synced"] == 1

        r2 = await initializer.sync(d2)
        assert r2["synced"] == 1

        # 两条记录，不同日期
        from sqlalchemy import select

        stmt = select(RecommendationStatus).where(
            RecommendationStatus.product_id == p.id
        )
        rows = (await session.execute(stmt)).scalars().all()
        assert len(rows) == 2


class TestServiceReturnsDict:
    """Service 返回 dict，不返回 ORM。"""

    @pytest.mark.anyio
    async def test_returns_dict(self, session, initializer):
        today = date.today()
        p = await _seed_product(session, name="dict测试")
        await _seed_report_with_items(session, today, [p])

        result = await initializer.sync(today)
        assert isinstance(result, dict)
        assert set(result.keys()) == {"synced", "skipped", "total", "report_date"}


# ═══════════════════════════════════════════════════════════════
# API 端到端验证
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
async def api_session_factory():
    """提供 API 测试的 session factory — 共享 in-memory DB（跨连接可见）。"""
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


class TestApiEndToEnd:
    """初始化后 API 推荐池返回值正确。"""

    @pytest.mark.anyio
    async def test_pool_empty_before_init(self, api_session_factory):
        """初始化前推荐池为空。"""
        from app.api.main import app

        with patch(
            "app.api.recommendation_pool.get_async_session_factory",
            return_value=api_session_factory,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.get("/recommendation-pool")
                assert resp.status_code == 200
                data = resp.json()
                # 无数据 → items 为空
                assert data["total"] == 0
                assert data["items"] == []

    @pytest.mark.anyio
    async def test_pool_after_init(self, api_session_factory):
        """初始化后推荐池可查询到正确数据。"""
        today = date.today()
        today_str = today.isoformat()

        # 种子数据
        async with api_session_factory() as sess:
            p1 = await _seed_product(sess, name="API商品1")
            p2 = await _seed_product(sess, name="API商品2")
            await _seed_report_with_items(sess, today, [p1, p2])

            # 初始化
            init = RecommendationPoolInitializer(sess)
            result = await init.sync(today)
            assert result["synced"] == 2
            await sess.commit()

        # API 查询
        from app.api.main import app

        with patch(
            "app.api.recommendation_pool.get_async_session_factory",
            return_value=api_session_factory,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                # 列表
                resp = await client.get(
                    f"/recommendation-pool?report_date={today_str}"
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["total"] == 2

                # 统计
                resp2 = await client.get(
                    f"/recommendation-pool/stats?report_date={today_str}"
                )
                assert resp2.status_code == 200
                stats = resp2.json()
                assert stats["status_counts"]["NEW"] == 2

    @pytest.mark.anyio
    async def test_pool_stats_before_and_after(self, api_session_factory):
        """同步前后验证: synced=1, 之后 stats 中 NEW 计数正确。"""
        today = date.today()
        today_str = today.isoformat()

        async with api_session_factory() as sess:
            p = await _seed_product(sess, name="Stats测试")
            await _seed_report_with_items(sess, today, [p])
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
                # Before: 推荐池有商品（由 DailyReportItem 驱动），但 stats 中 NEW=0
                resp_stats_before = await client.get(
                    f"/recommendation-pool/stats?report_date={today_str}"
                )
                stats_before = resp_stats_before.json()
                # 无 recommendation_status 记录 → 所有状态计数为 0
                assert stats_before["status_counts"]["NEW"] == 0

                # 初始化
                async with api_session_factory() as sess2:
                    init = RecommendationPoolInitializer(sess2)
                    r = await init.sync(today)
                    assert r["synced"] == 1
                    await sess2.commit()

                # After: stats 反映实际状态
                resp_stats_after = await client.get(
                    f"/recommendation-pool/stats?report_date={today_str}"
                )
                stats_after = resp_stats_after.json()
                assert stats_after["status_counts"]["NEW"] == 1

                # After: 列表也正常
                resp_pool = await client.get(
                    f"/recommendation-pool?report_date={today_str}"
                )
                pool = resp_pool.json()
                assert pool["total"] >= 1

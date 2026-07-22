"""Tests for Phase 46.1 — Recommendation Pool (Model → Repo → Service → API).

全覆盖层级：
- Model: PoolStatus 枚举 + RecommendationStatus ORM
- Repository: RecommendationStatusRepository + RecommendationPoolRepository
- Service: RecommendationPoolService（全链路 Enum、状态流转校验、report_date 默认值）
- API: 4 端点 + 错误场景（非法流转 / 不存在 / 日期格式错误）
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
from app.models.supplier_match import SupplierMatch
from app.database.recommendation_status_repository import (
    RecommendationStatusRepository,
)
from app.database.recommendation_pool_repository import (
    RecommendationPoolRepository,
)
from app.services.recommendation.pool_service import RecommendationPoolService

import app.models  # noqa: F401 — ensure all models registered


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
def status_repo(session: AsyncSession) -> RecommendationStatusRepository:
    return RecommendationStatusRepository(session)


@pytest.fixture
def pool_repo(session: AsyncSession) -> RecommendationPoolRepository:
    return RecommendationPoolRepository(session)


@pytest.fixture
def service(session: AsyncSession) -> RecommendationPoolService:
    return RecommendationPoolService(session)


# ── Seed helpers ──────────────────────────────────────────


async def _seed_product(
    session: AsyncSession,
    name: str = "测试商品",
    platform: str = "taobao",
    price: float = 99.0,
    **kwargs,
) -> Product:
    p = Product(
        name=name,
        platform=platform,
        shop=kwargs.get("shop", "测试店铺"),
        price=price,
        image=kwargs.get("image", "http://img.com/p.jpg"),
        url=kwargs.get("url", "http://item.com/1"),
        sales_24h=kwargs.get("sales_24h", 100),
        viewers=kwargs.get("viewers", 500),
    )
    session.add(p)
    await session.flush()
    return p


async def _seed_daily_report(
    session: AsyncSession,
    report_date: date | None = None,
    items_data: list[dict] | None = None,
) -> DailyReport:
    """创建 DailyReport + DailyReportItems。"""
    rd = report_date or date.today()
    report = DailyReport(
        report_date=rd,
        total=len(items_data) if items_data else 0,
        hot_products=0,
        potential_products=0,
        average_score=0.0,
    )
    session.add(report)
    await session.flush()

    if items_data:
        for item in items_data:
            session.add(DailyReportItem(
                report_id=report.id,
                product_id=item["product_id"],
                name=item.get("name", "测试商品"),
                platform=item.get("platform", "taobao"),
                price=item.get("price", 99.0),
                image=item.get("image", ""),
                rank=item.get("rank", 1),
                score=item.get("score", 80),
                level=item.get("level", "A"),
                reasons=item.get("reasons", '["HOT"]'),
            ))
        await session.flush()

    return report


async def _seed_supplier_match(
    session: AsyncSession,
    product_id: int,
    rank: int = 1,
    similarity_score: float = 0.85,
    **kwargs,
) -> SupplierMatch:
    sm = SupplierMatch(
        product_id=product_id,
        supplier_product_id=kwargs.get("supplier_product_id", 1000 + product_id),
        similarity_score=similarity_score,
        text_score=0.8,
        feature_score=0.7,
        image_score=0.9,
        rank=rank,
        supplier_title=kwargs.get("supplier_title", "供应商A"),
        supplier_price=kwargs.get("supplier_price", 25.0),
        estimated_profit=kwargs.get("estimated_profit", 50.0),
        profit_margin=kwargs.get("profit_margin", 0.5),
    )
    session.add(sm)
    await session.flush()
    return sm


# ═══════════════════════════════════════════════════════════════
# 1. Model — PoolStatus Enum
# ═══════════════════════════════════════════════════════════════


class TestPoolStatusEnum:
    """PoolStatus(str, Enum) 行为验证。"""

    def test_enum_values(self):
        """四个状态值正确。"""
        assert PoolStatus.NEW.value == "NEW"
        assert PoolStatus.REVIEWED.value == "REVIEWED"
        assert PoolStatus.APPROVED.value == "APPROVED"
        assert PoolStatus.REJECTED.value == "REJECTED"

    def test_enum_is_str(self):
        """str + Enum 双继承：可直接用于字符串比较。"""
        assert PoolStatus.NEW == "NEW"
        assert isinstance(PoolStatus.NEW, str)

    def test_from_string(self):
        """从字符串构造 Enum。"""
        assert PoolStatus("NEW") == PoolStatus.NEW
        assert PoolStatus("APPROVED") == PoolStatus.APPROVED

    def test_invalid_from_string(self):
        """非法字符串应抛 ValueError。"""
        with pytest.raises(ValueError):
            PoolStatus("INVALID")


# ═══════════════════════════════════════════════════════════════
# 2. Repository — RecommendationStatusRepository
# ═══════════════════════════════════════════════════════════════


class TestStatusRepository:
    """审核状态持久化 CRUD 测试。"""

    @pytest.mark.anyio
    async def test_upsert_new_record(self, status_repo, session):
        """首次 upsert → 创建新记录。"""
        record = await status_repo.upsert_status(
            product_id=1, report_date=date.today(), status=PoolStatus.NEW
        )
        assert record.id is not None
        assert record.product_id == 1
        assert record.status == "NEW"
        assert record.review_notes is None

    @pytest.mark.anyio
    async def test_upsert_update_existing(self, status_repo, session):
        """已存在的记录 → 更新 status。"""
        await status_repo.upsert_status(
            product_id=1, report_date=date.today(), status=PoolStatus.NEW
        )
        record = await status_repo.upsert_status(
            product_id=1, report_date=date.today(), status=PoolStatus.APPROVED, notes="可跟卖"
        )
        assert record.status == "APPROVED"
        assert record.review_notes == "可跟卖"
        assert record.reviewed_at is not None  # NEW→非NEW 记录时间

    @pytest.mark.anyio
    async def test_upsert_same_status_idempotent(self, status_repo, session):
        """相同 status upsert → 不改变状态，仅更新 notes。"""
        r1 = await status_repo.upsert_status(
            product_id=1, report_date=date.today(), status=PoolStatus.NEW, notes="备注1"
        )
        r2 = await status_repo.upsert_status(
            product_id=1, report_date=date.today(), status=PoolStatus.NEW, notes="备注2"
        )
        assert r2.id == r1.id
        assert r2.status == "NEW"
        assert r2.review_notes == "备注2"

    @pytest.mark.anyio
    async def test_get_status_found(self, status_repo, session):
        """get_status 命中返回记录。"""
        await status_repo.upsert_status(
            product_id=1, report_date=date.today(), status=PoolStatus.REVIEWED
        )
        record = await status_repo.get_status(1, date.today())
        assert record is not None
        assert PoolStatus(record.status) == PoolStatus.REVIEWED

    @pytest.mark.anyio
    async def test_get_status_not_found(self, status_repo):
        """get_status 未命中返回 None。"""
        record = await status_repo.get_status(999, date.today())
        assert record is None

    @pytest.mark.anyio
    async def test_batch_get_statuses(self, status_repo, session):
        """批量查询 → {product_id: RecommendationStatus}。"""
        today = date.today()
        await status_repo.upsert_status(1, today, PoolStatus.NEW)
        await status_repo.upsert_status(2, today, PoolStatus.APPROVED)
        # product_id=3 无状态记录

        result = await status_repo.batch_get_statuses([1, 2, 3], today)
        assert len(result) == 2
        assert result[1].status == "NEW"
        assert result[2].status == "APPROVED"
        assert 3 not in result

    @pytest.mark.anyio
    async def test_batch_get_empty_ids(self, status_repo):
        """空 product_ids → 返回空 dict。"""
        result = await status_repo.batch_get_statuses([], date.today())
        assert result == {}

    @pytest.mark.anyio
    async def test_count_by_status(self, status_repo, session):
        """按状态统计。"""
        today = date.today()
        await status_repo.upsert_status(1, today, PoolStatus.NEW)
        await status_repo.upsert_status(2, today, PoolStatus.NEW)
        await status_repo.upsert_status(3, today, PoolStatus.APPROVED)
        await status_repo.upsert_status(4, today, PoolStatus.REJECTED)

        counts = await status_repo.count_by_status(today)
        assert counts["NEW"] == 2
        assert counts["APPROVED"] == 1
        assert counts["REJECTED"] == 1
        assert counts["REVIEWED"] == 0

    @pytest.mark.anyio
    async def test_count_by_status_empty(self, status_repo):
        """无记录时所有计数为 0。"""
        counts = await status_repo.count_by_status(date.today())
        assert counts["NEW"] == 0
        assert counts["APPROVED"] == 0


# ═══════════════════════════════════════════════════════════════
# 3. Repository — RecommendationPoolRepository
# ═══════════════════════════════════════════════════════════════


class TestPoolRepository:
    """推荐池聚合查询测试。"""

    @pytest.mark.anyio
    async def test_get_latest_report_date_empty(self, pool_repo):
        """无 DailyReport → 返回 None。"""
        assert await pool_repo.get_latest_report_date() is None

    @pytest.mark.anyio
    async def test_get_latest_report_date(self, pool_repo, session):
        """返回最新 report_date。"""
        await _seed_daily_report(session, date(2026, 7, 20))
        await _seed_daily_report(session, date(2026, 7, 21))
        assert await pool_repo.get_latest_report_date() == date(2026, 7, 21)

    @pytest.mark.anyio
    async def test_list_pool_empty(self, pool_repo):
        """无数据 → 返回空列表。"""
        items = await pool_repo.list_pool()
        assert items == []

    @pytest.mark.anyio
    async def test_list_pool_basic(self, pool_repo, session):
        """正常聚合查询。"""
        p1 = await _seed_product(session, "商品1", "taobao", 99.0)
        p2 = await _seed_product(session, "商品2", "taobao", 129.0)
        today = date.today()
        await _seed_daily_report(session, today, items_data=[
            {"product_id": p1.id, "rank": 1, "score": 85.0, "level": "A"},
            {"product_id": p2.id, "rank": 2, "score": 72.0, "level": "B"},
        ])
        await _seed_supplier_match(session, p1.id, rank=1, similarity_score=0.9, estimated_profit=60.0)
        await _seed_supplier_match(session, p1.id, rank=2, similarity_score=0.7, estimated_profit=40.0)
        await _seed_supplier_match(session, p2.id, rank=1, similarity_score=0.6, estimated_profit=30.0)

        items = await pool_repo.list_pool()

        assert len(items) == 2
        assert items[0]["name"] == "商品1"
        assert items[0]["rank"] == 1
        assert items[0]["score"] == 85.0
        assert items[0]["supplier_count"] == 2
        assert items[0]["best_supplier_title"] == "供应商A"
        assert items[0]["estimated_profit"] == 60.0
        assert items[1]["name"] == "商品2"
        assert items[1]["supplier_count"] == 1

    @pytest.mark.anyio
    async def test_list_pool_status_filter(self, pool_repo, session):
        """按审核状态筛选。"""
        p1 = await _seed_product(session, "商品1", "taobao", 99.0)
        today = date.today()
        await _seed_daily_report(session, today, items_data=[
            {"product_id": p1.id, "rank": 1, "score": 80.0, "level": "A"},
        ])

        # 设置状态为 APPROVED
        status_repo = RecommendationStatusRepository(session)
        await status_repo.upsert_status(p1.id, today, PoolStatus.APPROVED)

        # 按 APPROVED 筛选 → 命中
        items = await pool_repo.list_pool(status="APPROVED")
        assert len(items) == 1

        # 按 NEW 筛选 → 不命中
        items = await pool_repo.list_pool(status="NEW")
        assert len(items) == 0

    @pytest.mark.anyio
    async def test_list_pool_min_score_filter(self, pool_repo, session):
        """按最低评分筛选。"""
        p1 = await _seed_product(session, "高分", "taobao", 99.0)
        p2 = await _seed_product(session, "低分", "taobao", 50.0)
        today = date.today()
        await _seed_daily_report(session, today, items_data=[
            {"product_id": p1.id, "rank": 1, "score": 90.0, "level": "A"},
            {"product_id": p2.id, "rank": 2, "score": 40.0, "level": "C"},
        ])

        items = await pool_repo.list_pool(min_score=60.0)
        assert len(items) == 1
        assert items[0]["name"] == "高分"

    @pytest.mark.anyio
    async def test_get_pool_detail(self, pool_repo, session):
        """单条详情含全部 supplier_matches。"""
        p1 = await _seed_product(session, "详情商品", "taobao", 199.0)
        today = date.today()
        await _seed_daily_report(session, today, items_data=[
            {"product_id": p1.id, "rank": 1, "score": 88.0, "level": "A", "reasons": '["HOT","可跟卖"]'},
        ])
        await _seed_supplier_match(session, p1.id, rank=1, similarity_score=0.9, supplier_title="优品供应商")
        await _seed_supplier_match(session, p1.id, rank=2, similarity_score=0.7, supplier_title="次选供应商")

        detail = await pool_repo.get_pool_detail(p1.id)
        assert detail is not None
        assert detail["name"] == "详情商品"
        assert detail["rank"] == 1
        assert len(detail["supplier_matches"]) == 2
        assert detail["supplier_matches"][0]["supplier_title"] == "优品供应商"
        assert detail["review_status"] == "NEW"

    @pytest.mark.anyio
    async def test_get_pool_detail_not_found(self, pool_repo):
        """商品不存在 → None。"""
        assert await pool_repo.get_pool_detail(99999) is None

    @pytest.mark.anyio
    async def test_list_pool_no_supplier_match(self, pool_repo, session):
        """无 supplier_match 时默认值正确。"""
        p1 = await _seed_product(session, "无匹配", "taobao", 79.0)
        today = date.today()
        await _seed_daily_report(session, today, items_data=[
            {"product_id": p1.id, "rank": 1, "score": 60.0, "level": "B"},
        ])

        items = await pool_repo.list_pool()
        assert len(items) == 1
        assert items[0]["supplier_count"] == 0
        assert items[0]["best_supplier_title"] == ""
        assert items[0]["estimated_profit"] == 0.0
        assert items[0]["profit_margin"] == 0.0


# ═══════════════════════════════════════════════════════════════
# 4. Service — RecommendationPoolService
# ═══════════════════════════════════════════════════════════════


class TestServiceListPool:
    """list_pool / get_pool_detail / stats。"""

    @pytest.mark.anyio
    async def test_list_pool_empty(self, service):
        """空数据库 → 空结果。"""
        result = await service.list_pool()
        assert result["report_date"] is None
        assert result["total"] == 0
        assert result["items"] == []

    @pytest.mark.anyio
    async def test_list_pool_with_data(self, service, session):
        """有数据时返回正确结构。"""
        p1 = await _seed_product(session, "商品A", "taobao", 99.0)
        today = date.today()
        await _seed_daily_report(session, today, items_data=[
            {"product_id": p1.id, "rank": 1, "score": 85.0, "level": "A"},
        ])

        result = await service.list_pool()
        assert result["report_date"] == today.isoformat()
        assert result["total"] == 1
        assert result["items"][0]["name"] == "商品A"

    @pytest.mark.anyio
    async def test_list_pool_status_filter_enum(self, service, session):
        """按 PoolStatus 枚举筛选。"""
        p1 = await _seed_product(session, "商品A", "taobao", 99.0)
        today = date.today()
        await _seed_daily_report(session, today, items_data=[
            {"product_id": p1.id, "rank": 1, "score": 80.0, "level": "A"},
        ])
        # 默认状态是 NEW（无 recommendation_status 记录 → "NEW"）
        result = await service.list_pool(status=PoolStatus.NEW)
        assert result["total"] == 1

        result = await service.list_pool(status=PoolStatus.APPROVED)
        assert result["total"] == 0

    @pytest.mark.anyio
    async def test_get_pool_detail_none(self, service):
        """无数据 → None。"""
        assert await service.get_pool_detail(1) is None

    @pytest.mark.anyio
    async def test_stats_empty(self, service):
        """空数据库 → 零计数。"""
        result = await service.stats()
        assert result["report_date"] is None
        assert result["status_counts"]["NEW"] == 0

    @pytest.mark.anyio
    async def test_stats_with_data(self, service, session):
        """有审核数据 → 正确计数。"""
        p1 = await _seed_product(session, "商品1", "taobao", 99.0)
        p2 = await _seed_product(session, "商品2", "taobao", 129.0)
        today = date.today()
        await _seed_daily_report(session, today)

        repo = RecommendationStatusRepository(session)
        await repo.upsert_status(p1.id, today, PoolStatus.APPROVED)
        await repo.upsert_status(p2.id, today, PoolStatus.NEW)

        result = await service.stats()
        assert result["report_date"] == today.isoformat()
        assert result["status_counts"]["APPROVED"] == 1
        assert result["status_counts"]["NEW"] == 1


class TestServiceStatusTransitions:
    """状态流转 + update_status。"""

    @pytest.mark.anyio
    async def test_update_status_default_date(self, service, session):
        """report_date 不传 → 默认最新一期。"""
        p1 = await _seed_product(session, "商品", "taobao", 99.0)
        today = date.today()
        await _seed_daily_report(session, today, items_data=[
            {"product_id": p1.id, "rank": 1, "score": 80.0, "level": "A"},
        ])

        result = await service.update_status(product_id=p1.id, status=PoolStatus.APPROVED, notes="可跟卖")
        assert result["success"] is True
        assert result["status"] == "APPROVED"
        assert result["report_date"] == today.isoformat()

    @pytest.mark.anyio
    async def test_update_status_no_data_raises(self, service):
        """无 DailyReport 时抛 ValueError。"""
        with pytest.raises(ValueError, match="暂无推荐数据"):
            await service.update_status(product_id=1, status=PoolStatus.APPROVED)

    @pytest.mark.anyio
    async def test_valid_transition_new_to_approved(self, service, session):
        """NEW → APPROVED 合法。"""
        p1 = await _seed_product(session, "商品", "taobao", 99.0)
        today = date.today()
        await _seed_daily_report(session, today, items_data=[
            {"product_id": p1.id, "rank": 1, "score": 80.0, "level": "A"},
        ])
        result = await service.update_status(p1.id, PoolStatus.APPROVED)
        assert result["status"] == "APPROVED"
        assert result["previous_status"] == "NEW"

    @pytest.mark.anyio
    async def test_valid_transition_approved_to_rejected(self, service, session):
        """APPROVED → REJECTED 合法。"""
        p1 = await _seed_product(session, "商品", "taobao", 99.0)
        today = date.today()
        await _seed_daily_report(session, today, items_data=[
            {"product_id": p1.id, "rank": 1, "score": 80.0, "level": "A"},
        ])
        await service.update_status(p1.id, PoolStatus.APPROVED)

        result = await service.update_status(p1.id, PoolStatus.REJECTED)
        assert result["status"] == "REJECTED"
        assert result["previous_status"] == "APPROVED"

    @pytest.mark.anyio
    async def test_valid_transition_reviewed_to_new(self, service, session):
        """REVIEWED → NEW 合法（打回重审）。"""
        p1 = await _seed_product(session, "商品", "taobao", 99.0)
        today = date.today()
        await _seed_daily_report(session, today, items_data=[
            {"product_id": p1.id, "rank": 1, "score": 80.0, "level": "A"},
        ])
        await service.update_status(p1.id, PoolStatus.REVIEWED)
        result = await service.update_status(p1.id, PoolStatus.NEW)
        assert result["status"] == "NEW"

    @pytest.mark.anyio
    async def test_invalid_transition(self, service, session):
        """非法流转抛 ValueError。"""
        p1 = await _seed_product(session, "商品", "taobao", 99.0)
        today = date.today()
        await _seed_daily_report(session, today, items_data=[
            {"product_id": p1.id, "rank": 1, "score": 80.0, "level": "A"},
        ])
        # 先设为 APPROVED
        await service.update_status(p1.id, PoolStatus.APPROVED)

        # APPROVED → NEW 非法
        with pytest.raises(ValueError, match="不允许从 APPROVED 流转到 NEW"):
            await service.update_status(p1.id, PoolStatus.NEW)

    @pytest.mark.anyio
    async def test_invalid_transition_rejected_to_approved(self, service, session):
        """REJECTED → APPROVED 非法。"""
        p1 = await _seed_product(session, "商品", "taobao", 99.0)
        today = date.today()
        await _seed_daily_report(session, today, items_data=[
            {"product_id": p1.id, "rank": 1, "score": 80.0, "level": "A"},
        ])
        await service.update_status(p1.id, PoolStatus.REJECTED)

        with pytest.raises(ValueError, match="不允许从 REJECTED 流转到 APPROVED"):
            await service.update_status(p1.id, PoolStatus.APPROVED)

    @pytest.mark.anyio
    async def test_same_status_no_error(self, service, session):
        """相同 status → 不抛异常（幂等）。"""
        p1 = await _seed_product(session, "商品", "taobao", 99.0)
        today = date.today()
        await _seed_daily_report(session, today, items_data=[
            {"product_id": p1.id, "rank": 1, "score": 80.0, "level": "A"},
        ])
        await service.update_status(p1.id, PoolStatus.APPROVED)
        # 再次 APPROVED → 不抛异常
        result = await service.update_status(p1.id, PoolStatus.APPROVED)
        assert result["status"] == "APPROVED"

    @pytest.mark.anyio
    async def test_explicit_report_date(self, service, session):
        """显式指定 report_date → 操作历史推荐。"""
        p1 = await _seed_product(session, "商品", "taobao", 99.0)
        history_date = date(2026, 7, 18)
        await _seed_daily_report(session, history_date, items_data=[
            {"product_id": p1.id, "rank": 1, "score": 80.0, "level": "A"},
        ])

        result = await service.update_status(
            p1.id, PoolStatus.REVIEWED, report_date=history_date
        )
        assert result["report_date"] == "2026-07-18"


# ═══════════════════════════════════════════════════════════════
# 5. API — integration tests
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
async def api_session_factory():
    """Create an in-memory session factory for API test isolation."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    yield factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def client(api_session_factory):
    """API client with mocked DB session factory."""
    from app.api.main import app

    with patch(
        "app.api.recommendation_pool.get_async_session_factory",
        return_value=api_session_factory,
    ):
        yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestRecommendationPoolAPI:
    """API 端点集成测试（httpx + ASGI transport）。"""

    @pytest.mark.anyio
    async def test_get_pool_empty(self, client):
        """空数据库 → 200 + items=[]。"""
        resp = await client.get("/recommendation-pool")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    @pytest.mark.anyio
    async def test_get_pool_with_status_filter(self, client):
        """status 参数通过 Enum 校验。"""
        # 合法 Enum 值
        resp = await client.get("/recommendation-pool?status=NEW")
        assert resp.status_code == 200

        # 非法 Enum 值 → FastAPI 返回 422
        resp = await client.get("/recommendation-pool?status=INVALID")
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_get_pool_min_score_validation(self, client):
        """min_score 范围校验。"""
        resp = await client.get("/recommendation-pool?min_score=-1")
        assert resp.status_code == 422

        resp = await client.get("/recommendation-pool?min_score=101")
        assert resp.status_code == 422

        resp = await client.get("/recommendation-pool?min_score=50")
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_get_pool_stats_empty(self, client):
        """stats 空库 → 200。"""
        resp = await client.get("/recommendation-pool/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["report_date"] is None

    @pytest.mark.anyio
    async def test_get_pool_detail_not_found(self, client):
        """不存在的商品 → 404。"""
        resp = await client.get("/recommendation-pool/99999")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_update_status_no_data(self, client):
        """无推荐数据时更新 → 422。"""
        resp = await client.patch(
            "/recommendation-pool/1/status",
            json={"status": "APPROVED"},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_update_status_invalid_enum(self, client):
        """非法 Enum 值 → 422（FastAPI 自动校验）。"""
        resp = await client.patch(
            "/recommendation-pool/1/status",
            json={"status": "GARBAGE"},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_update_status_invalid_date(self, client):
        """非法日期格式 → 422。"""
        resp = await client.patch(
            "/recommendation-pool/1/status",
            json={"status": "APPROVED", "report_date": "not-a-date"},
        )
        assert resp.status_code == 422

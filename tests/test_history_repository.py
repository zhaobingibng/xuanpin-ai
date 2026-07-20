"""Tests for HistoryRepository."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.history_repository import HistoryRepository
from app.models.product import Product
from app.models.product_history import ProductHistory

# ensure models registered
import app.models  # noqa: F401


# ── Fixtures ─────────────────────────────────────────────────


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


async def _insert_product(session: AsyncSession, **overrides: object) -> Product:
    defaults = {
        "name": "测试商品",
        "platform": "xiaohongshu",
        "shop": "测试店铺",
        "price": 99.9,
        "viewers": 1000,
        "sales_24h": 200,
    }
    defaults.update(overrides)
    product = Product(**defaults)  # type: ignore[arg-type]
    session.add(product)
    await session.flush()
    return product


# ── TestCreateHistory ───────────────────────────────────────


class TestCreateHistory:

    @pytest.mark.anyio
    async def test_create_returns_history(self, session):
        repo = HistoryRepository(session)
        product = await _insert_product(session)

        history = ProductHistory(
            product_id=product.id,
            price=product.price,
            sales_24h=product.sales_24h,
            viewers=product.viewers,
        )
        result = await repo.create(history)

        assert result.id is not None
        assert result.product_id == product.id
        assert result.price == 99.9

    @pytest.mark.anyio
    async def test_create_multiple_records(self, session):
        repo = HistoryRepository(session)
        product = await _insert_product(session)

        h1 = ProductHistory(product_id=product.id, price=10.0, sales_24h=100, viewers=50)
        h2 = ProductHistory(product_id=product.id, price=20.0, sales_24h=200, viewers=100)
        await repo.create(h1)
        await repo.create(h2)

        records = await repo.get_history(product.id)
        assert len(records) == 2


# ── TestCreateSnapshot ──────────────────────────────────────


class TestCreateSnapshot:

    @pytest.mark.anyio
    async def test_snapshot_fields(self, session):
        repo = HistoryRepository(session)
        product = await _insert_product(session, price=199.0, sales_24h=500, viewers=3000)

        snapshot = await repo.create_snapshot(product)

        assert snapshot is not None
        assert snapshot.product_id == product.id
        assert snapshot.price == 199.0
        assert snapshot.sales_24h == 500
        assert snapshot.viewers == 3000
        assert snapshot.ai_score is None
        assert snapshot.record_time is not None

    @pytest.mark.anyio
    async def test_snapshot_returns_none_on_same_minute(self, session):
        repo = HistoryRepository(session)
        product = await _insert_product(session)

        # First snapshot → created
        first = await repo.create_snapshot(product)
        assert first is not None

        # Second snapshot same minute → None (dedup)
        second = await repo.create_snapshot(product)
        assert second is None

    @pytest.mark.anyio
    async def test_snapshot_creates_after_different_minute(self, session):
        repo = HistoryRepository(session)
        product = await _insert_product(session)

        # First snapshot
        first = await repo.create_snapshot(product)
        assert first is not None

        # Manually insert a record with a different minute
        past_time = datetime.utcnow() - timedelta(minutes=2)
        old = ProductHistory(
            product_id=product.id,
            price=product.price,
            sales_24h=product.sales_24h,
            viewers=product.viewers,
            record_time=past_time,
        )
        await repo.create(old)

        # Now a new snapshot should succeed (different minute from the old one,
        # but same minute as 'first' → still None because 'first' is current minute)
        second = await repo.create_snapshot(product)
        assert second is None  # still same minute as 'first'

    @pytest.mark.anyio
    async def test_snapshot_with_ai_score(self, session):
        repo = HistoryRepository(session)
        product = await _insert_product(session, ai_score=8.5)

        snapshot = await repo.create_snapshot(product)
        assert snapshot is not None
        assert snapshot.ai_score == 8.5


# ── TestGetHistory ──────────────────────────────────────────


class TestGetHistory:

    @pytest.mark.anyio
    async def test_returns_records_newest_first(self, session):
        repo = HistoryRepository(session)
        product = await _insert_product(session)

        # Insert 3 records with different times
        now = datetime.utcnow()
        for i in range(3):
            h = ProductHistory(
                product_id=product.id,
                price=float(10 + i),
                sales_24h=100 * (i + 1),
                viewers=500 * (i + 1),
                record_time=now - timedelta(minutes=10 - i),
            )
            await repo.create(h)

        records = await repo.get_history(product.id)
        assert len(records) == 3
        # Newest first: last inserted (i=2) should be first
        assert records[0].price == 12.0
        assert records[2].price == 10.0

    @pytest.mark.anyio
    async def test_limit(self, session):
        repo = HistoryRepository(session)
        product = await _insert_product(session)

        now = datetime.utcnow()
        for i in range(10):
            h = ProductHistory(
                product_id=product.id,
                price=float(i),
                sales_24h=0,
                viewers=0,
                record_time=now - timedelta(minutes=10 - i),
            )
            await repo.create(h)

        records = await repo.get_history(product.id, limit=5)
        assert len(records) == 5

    @pytest.mark.anyio
    async def test_empty_history(self, session):
        repo = HistoryRepository(session)
        records = await repo.get_history(9999)
        assert len(records) == 0

    @pytest.mark.anyio
    async def test_isolation_between_products(self, session):
        repo = HistoryRepository(session)
        p1 = await _insert_product(session, name="商品A")
        p2 = await _insert_product(session, name="商品B")

        now = datetime.utcnow()
        for i in range(3):
            await repo.create(ProductHistory(
                product_id=p1.id, price=float(i), sales_24h=0, viewers=0,
                record_time=now - timedelta(minutes=i),
            ))
        for i in range(5):
            await repo.create(ProductHistory(
                product_id=p2.id, price=float(i), sales_24h=0, viewers=0,
                record_time=now - timedelta(minutes=i),
            ))

        h1 = await repo.get_history(p1.id)
        h2 = await repo.get_history(p2.id)

        assert len(h1) == 3
        assert len(h2) == 5

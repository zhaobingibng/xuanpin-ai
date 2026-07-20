"""Integration tests for ProductHistory auto-generation during ingestion.

Flow: Crawler → RawProduct → ProductService → Product + ProductHistory → SQLite.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.crawler.models.schemas import RawProduct
from app.database.base import Base
from app.database.history_repository import HistoryRepository
from app.models.product import Product
from app.models.product_history import ProductHistory
from app.services.product_service import ProductService

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


def _raw(**overrides: object) -> RawProduct:
    defaults = {
        "name": "蓝牙耳机降噪",
        "platform": "xiaohongshu",
        "shop": "数码旗舰店",
        "price": 99.9,
        "viewers": 1200,
        "sales_24h": 350,
        "url": "https://xhslink.com/p/1",
    }
    defaults.update(overrides)
    return RawProduct(**defaults)


# ── TestHistoryAutoGeneration ───────────────────────────────


class TestHistoryAutoGeneration:

    @pytest.mark.anyio
    async def test_save_creates_history(self, session):
        """Saving a product automatically creates a history snapshot."""
        svc = ProductService(session)
        await svc.save_raw_products([_raw()])

        # Verify product exists
        products = await svc.list_all()
        assert len(products) == 1
        product = products[0]

        # Verify history was created
        repo = HistoryRepository(session)
        history = await repo.get_history(product.id)
        assert len(history) == 1
        assert history[0].price == 99.9
        assert history[0].sales_24h == 350
        assert history[0].viewers == 1200

    @pytest.mark.anyio
    async def test_save_creates_history_for_multiple_products(self, session):
        svc = ProductService(session)
        raws = [
            _raw(name="商品A", url="https://xhslink.com/a"),
            _raw(name="商品B", url="https://xhslink.com/b"),
            _raw(name="商品C", url="https://xhslink.com/c"),
        ]
        await svc.save_raw_products(raws)

        products = await svc.list_all()
        assert len(products) == 3

        repo = HistoryRepository(session)
        for p in products:
            h = await repo.get_history(p.id)
            assert len(h) == 1

    @pytest.mark.anyio
    async def test_empty_save_no_history(self, session):
        svc = ProductService(session)
        await svc.save_raw_products([])

        stmt = select(ProductHistory)
        result = await session.execute(stmt)
        assert len(result.scalars().all()) == 0


# ── TestMultipleCrawlsGenerateMultipleHistory ───────────────


class TestMultipleCrawlsHistory:

    @pytest.mark.anyio
    async def test_different_minutes_create_multiple_records(self, session):
        """Simulate two crawls at different minutes → two history records."""
        svc = ProductService(session)

        # First crawl
        await svc.save_raw_products([
            _raw(price=99.9, sales_24h=100, url="https://xhslink.com/p/1"),
        ])

        # Manually shift the existing history record to 2 minutes ago
        stmt = select(ProductHistory)
        result = await session.execute(stmt)
        for h in result.scalars().all():
            h.record_time = datetime.utcnow() - timedelta(minutes=2)
        await session.commit()

        # Second crawl — same product, different data
        await svc.save_raw_products([
            _raw(price=199.0, sales_24h=200, url="https://xhslink.com/p/1"),
        ])

        # Should have 2 history records
        products = await svc.list_all()
        product = products[0]

        repo = HistoryRepository(session)
        history = await repo.get_history(product.id)
        assert len(history) == 2

        # Newest first
        assert history[0].sales_24h == 200  # second crawl
        assert history[1].sales_24h == 100  # first crawl

    @pytest.mark.anyio
    async def test_same_minute_dedup(self, session):
        """Two saves within the same minute → only one history record."""
        svc = ProductService(session)

        # First save
        await svc.save_raw_products([
            _raw(price=99.9, url="https://xhslink.com/p/1"),
        ])

        # Second save — same minute, same product (updated price)
        await svc.save_raw_products([
            _raw(price=199.0, url="https://xhslink.com/p/1"),
        ])

        # Product should be updated
        products = await svc.list_all()
        assert len(products) == 1
        assert products[0].price == 199.0

        # But only 1 history record (same minute dedup)
        repo = HistoryRepository(session)
        history = await repo.get_history(products[0].id)
        assert len(history) == 1


# ── TestHistoryIsolation ────────────────────────────────────


class TestHistoryIsolation:

    @pytest.mark.anyio
    async def test_different_products_isolated(self, session):
        """Each product has its own history, no cross-contamination."""
        svc = ProductService(session)

        await svc.save_raw_products([
            _raw(name="商品A", url="https://xhslink.com/a", sales_24h=100),
            _raw(name="商品B", url="https://xhslink.com/b", sales_24h=200),
        ])

        products = await svc.list_all()
        assert len(products) == 2

        repo = HistoryRepository(session)
        for p in products:
            h = await repo.get_history(p.id)
            assert len(h) == 1
            # Each history matches its own product
            assert h[0].product_id == p.id

    @pytest.mark.anyio
    async def test_history_snapshots_current_values(self, session):
        """History captures the values at the time of save, not later updates."""
        svc = ProductService(session)

        # First save with specific values
        await svc.save_raw_products([
            _raw(price=50.0, sales_24h=10, viewers=100, url="https://xhslink.com/p/1"),
        ])

        # Shift history to past
        stmt = select(ProductHistory)
        result = await session.execute(stmt)
        for h in result.scalars().all():
            h.record_time = datetime.utcnow() - timedelta(minutes=2)
        await session.commit()

        # Second save with different values
        await svc.save_raw_products([
            _raw(price=80.0, sales_24h=50, viewers=500, url="https://xhslink.com/p/1"),
        ])

        products = await svc.list_all()
        product = products[0]

        repo = HistoryRepository(session)
        history = await repo.get_history(product.id)
        assert len(history) == 2

        # Newest first: second save values
        assert history[0].price == 80.0
        assert history[0].sales_24h == 50
        assert history[0].viewers == 500

        # Older: first save values
        assert history[1].price == 50.0
        assert history[1].sales_24h == 10
        assert history[1].viewers == 100

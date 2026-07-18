"""Tests for ProductHistory model."""

from datetime import datetime

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.product import Product
from app.models.product_history import ProductHistory


def _make_engine():
    """Create an in-memory SQLite engine for testing."""
    return create_engine("sqlite:///:memory:", echo=False)


class TestProductHistoryTable:
    """Verify product_history table structure and behaviour."""

    def test_table_creation(self):
        """product_history table should be created alongside products."""
        engine = _make_engine()
        Base.metadata.create_all(engine)

        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "product_history" in tables
        assert "products" in tables

    def test_table_columns(self):
        """All expected columns should exist on product_history."""
        engine = _make_engine()
        Base.metadata.create_all(engine)

        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("product_history")}

        expected = {
            "id", "product_id", "price", "sales_24h",
            "viewers", "ai_score", "record_time",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

    def test_insert_and_query(self):
        """A ProductHistory row should be insertable and queryable."""
        engine = _make_engine()
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            product = Product(
                name="蓝牙耳机", platform="抖音", shop="数码店", price=99.0,
            )
            session.add(product)
            session.flush()

            snapshot = ProductHistory(
                product_id=product.id,
                price=99.0,
                sales_24h=120,
                viewers=500,
                ai_score=78.5,
            )
            session.add(snapshot)
            session.commit()

            result = session.query(ProductHistory).first()
            assert result is not None
            assert result.product_id == product.id
            assert result.price == 99.0
            assert result.sales_24h == 120
            assert result.viewers == 500
            assert result.ai_score == 78.5
            assert result.record_time is not None

    def test_multiple_snapshots_per_product(self):
        """A product can have multiple history snapshots over time."""
        engine = _make_engine()
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            product = Product(
                name="保温杯", platform="小红书", shop="家居店", price=49.0,
            )
            session.add(product)
            session.flush()

            for price, sales, viewers in [(49.0, 20, 100), (45.0, 50, 200), (42.0, 90, 350)]:
                session.add(ProductHistory(
                    product_id=product.id, price=price, sales_24h=sales, viewers=viewers,
                ))
            session.commit()

            rows = session.query(ProductHistory).filter_by(product_id=product.id).all()
            assert len(rows) == 3
            prices = [r.price for r in rows]
            assert prices == [49.0, 45.0, 42.0]

    def test_cascade_delete(self):
        """Deleting a product should cascade-delete its history rows."""
        engine = _make_engine()
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            session.execute(text("PRAGMA foreign_keys=ON"))

            product = Product(
                name="手机壳", platform="快手", shop="配件店", price=19.9,
            )
            session.add(product)
            session.flush()

            session.add(ProductHistory(
                product_id=product.id, price=19.9, sales_24h=10, viewers=50,
            ))
            session.commit()

            assert session.query(ProductHistory).count() == 1

            session.delete(product)
            session.commit()

            assert session.query(ProductHistory).count() == 0

    def test_indexes(self):
        """product_id, record_time, and composite index should exist."""
        engine = _make_engine()
        Base.metadata.create_all(engine)

        inspector = inspect(engine)
        indexes = inspector.get_indexes("product_history")

        indexed_columns = set()
        for idx in indexes:
            indexed_columns.update(idx["column_names"])

        assert "product_id" in indexed_columns, "Missing index on product_id"
        assert "record_time" in indexed_columns, "Missing index on record_time"

        # Composite index (product_id, record_time)
        composite_found = any(
            idx["column_names"] == ["product_id", "record_time"]
            for idx in indexes
        )
        assert composite_found, "Missing composite index on (product_id, record_time)"

    def test_repr(self):
        """__repr__ should return a readable string."""
        snapshot = ProductHistory(
            id=1, product_id=5, price=99.0,
            sales_24h=0, viewers=0,
            record_time=datetime(2026, 7, 18, 12, 0, 0),
        )
        r = repr(snapshot)
        assert "ProductHistory" in r
        assert "product_id=5" in r
        assert "price=99.0" in r

    def test_nullable_ai_score(self):
        """ai_score should accept None."""
        engine = _make_engine()
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            product = Product(
                name="测试商品", platform="抖音", shop="测试店铺", price=50.0,
            )
            session.add(product)
            session.flush()

            snapshot = ProductHistory(
                product_id=product.id, price=50.0, sales_24h=5, viewers=10,
                ai_score=None,
            )
            session.add(snapshot)
            session.commit()

            result = session.query(ProductHistory).first()
            assert result.ai_score is None

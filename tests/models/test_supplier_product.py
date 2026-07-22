"""Tests for Phase 26: SupplierProductDB model."""

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.supplier_product import SupplierProductDB


def _make_engine():
    """Create an in-memory SQLite engine for testing."""
    return create_engine("sqlite:///:memory:", echo=False)


class TestSupplierProductTable:
    """Verify supplier_products table creation and columns."""

    def test_table_creation(self):
        """Table should be created without errors."""
        engine = _make_engine()
        Base.metadata.create_all(engine)

        inspector = inspect(engine)
        assert "supplier_products" in inspector.get_table_names()

    def test_table_columns(self):
        """All expected columns should exist."""
        engine = _make_engine()
        Base.metadata.create_all(engine)

        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("supplier_products")}

        expected = {
            "id", "source", "offer_id", "title", "price",
            "sales", "shop_name", "url", "image",
            "created_at", "updated_at",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

    def test_insert_and_query(self):
        """Should be able to insert and query records."""
        engine = _make_engine()
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            product = SupplierProductDB(
                source="1688",
                offer_id="test_001",
                title="测试商品",
                price=29.9,
                sales=100,
                shop_name="测试供应商",
                url="https://detail.1688.com/offer/test_001.html",
                image="https://cbu01.alicdn.com/test.jpg",
            )
            session.add(product)
            session.commit()

            # Query back
            result = session.query(SupplierProductDB).first()
            assert result is not None
            assert result.offer_id == "test_001"
            assert result.title == "测试商品"
            assert result.price == 29.9
            assert result.sales == 100
            assert result.shop_name == "测试供应商"
            assert result.source == "1688"

    def test_default_values(self):
        """Default values should be applied."""
        engine = _make_engine()
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            product = SupplierProductDB(
                offer_id="test_002",
                title="默认值测试",
            )
            session.add(product)
            session.commit()

            result = session.query(SupplierProductDB).first()
            assert result is not None
            assert result.source == "1688"
            assert result.price == 0.0
            assert result.sales == 0
            assert result.shop_name == ""

    def test_unique_offer_id(self):
        """offer_id should be unique."""
        engine = _make_engine()
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            p1 = SupplierProductDB(offer_id="unique_001", title="商品1")
            session.add(p1)
            session.commit()

            p2 = SupplierProductDB(offer_id="unique_001", title="商品2")
            session.add(p2)

            import pytest
            with pytest.raises(Exception):  # IntegrityError
                session.commit()

    def test_repr(self):
        """__repr__ should return a readable string."""
        product = SupplierProductDB(
            offer_id="repr_001",
            title="_repr测试商品" * 5,  # Long title
            price=19.9,
        )
        repr_str = repr(product)
        assert "repr_001" in repr_str
        assert "19.9" in repr_str

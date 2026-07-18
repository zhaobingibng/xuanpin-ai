"""Tests for Product model and table initialization."""

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.product import Product


def _make_engine():
    """Create an in-memory SQLite engine for testing."""
    return create_engine("sqlite:///:memory:", echo=False)


class TestProductTable:
    """Verify products table can be created and used."""

    def test_table_creation(self):
        """Tables should be created without errors."""
        engine = _make_engine()
        Base.metadata.create_all(engine)

        inspector = inspect(engine)
        assert "products" in inspector.get_table_names()

    def test_table_columns(self):
        """All expected columns should exist on the products table."""
        engine = _make_engine()
        Base.metadata.create_all(engine)

        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("products")}

        expected = {
            "id", "name", "platform", "shop", "image",
            "price", "viewers", "sales_24h", "ai_score",
            "created_at", "updated_at",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

    def test_insert_and_query(self):
        """A Product row should be insertable and queryable."""
        engine = _make_engine()
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            product = Product(
                name="测试商品",
                platform="抖音",
                shop="测试店铺",
                image="https://example.com/img.jpg",
                price=99.9,
                viewers=150,
                sales_24h=42,
                ai_score=8.5,
            )
            session.add(product)
            session.commit()

            result = session.query(Product).first()
            assert result is not None
            assert result.name == "测试商品"
            assert result.platform == "抖音"
            assert result.shop == "测试店铺"
            assert result.price == 99.9
            assert result.viewers == 150
            assert result.sales_24h == 42
            assert result.ai_score == 8.5
            assert result.id == 1

    def test_table_indexes(self):
        """Indexes should exist on name and platform columns."""
        engine = _make_engine()
        Base.metadata.create_all(engine)

        inspector = inspect(engine)
        indexes = inspector.get_indexes("products")
        indexed_columns = set()
        for idx in indexes:
            indexed_columns.update(idx["column_names"])

        assert "name" in indexed_columns, "Missing index on 'name'"
        assert "platform" in indexed_columns, "Missing index on 'platform'"

    def test_repr(self):
        """__repr__ should return a readable string."""
        product = Product(id=1, name="商品A", platform="快手")
        assert repr(product) == "<Product(id=1, name='商品A', platform='快手')>"

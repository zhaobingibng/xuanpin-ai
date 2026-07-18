"""Statistics API endpoints."""

from fastapi import APIRouter

from app.database.base import get_session_factory
from app.models.product import Product
from app.services.cleaner.product_cleaner import ProductCleaner

router = APIRouter()

_cleaner = ProductCleaner()


@router.get("/stats/category")
async def category_stats() -> dict[str, int]:
    """返回各分类的商品数量统计。"""
    Session = get_session_factory()
    try:
        with Session() as session:
            products = session.query(Product).all()
            counts: dict[str, int] = {}
            for p in products:
                cat = _cleaner.classify(p.name)
                counts[cat] = counts.get(cat, 0) + 1
            return counts
    except Exception:
        return {}


@router.get("/stats/platform")
async def platform_stats() -> dict[str, int]:
    """返回各平台的商品数量统计。"""
    Session = get_session_factory()
    try:
        with Session() as session:
            products = session.query(Product).all()
            counts: dict[str, int] = {}
            for p in products:
                counts[p.platform] = counts.get(p.platform, 0) + 1
            return counts
    except Exception:
        return {}

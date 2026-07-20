"""Data schemas for crawler output."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawProduct:
    """Raw product data extracted by a crawler before persistence."""

    name: str
    platform: str
    shop: str
    price: float
    viewers: int = 0
    sales_24h: int = 0
    image: str | None = None
    url: str | None = None
    category: str = ""
    favorites: int = 0
    comments: int = 0
    publish_time: str | None = None
    crawled_at: datetime = field(default_factory=datetime.now)

    def to_db_kwargs(self) -> dict:
        """Convert to keyword arguments suitable for ProductService.create()."""
        return {
            "name": self.name,
            "platform": self.platform,
            "shop": self.shop,
            "price": self.price,
            "viewers": self.viewers,
            "sales_24h": self.sales_24h,
            "image": self.image,
            "url": self.url,
            "category": self.category or None,
        }

"""Pydantic schemas for daily report API response."""

from pydantic import BaseModel


class ReportItem(BaseModel):
    """单条商品评分结果。"""

    rank: int
    product_id: int
    name: str
    platform: str
    image: str
    price: float
    score: int
    level: str
    reasons: list[str]


class DailyReportResponse(BaseModel):
    """每日选品报告响应。"""

    date: str
    total: int
    hot_products: int
    potential_products: int
    average_score: float
    items: list[ReportItem]


class ReportSummary(BaseModel):
    """历史日报摘要（不含 items）。"""

    id: int
    report_date: str
    total: int
    hot_products: int
    potential_products: int
    average_score: float


class ReportDetailItem(BaseModel):
    """日报详情中的单条商品。"""

    id: int
    product_id: int
    rank: int
    name: str
    platform: str
    image: str
    price: float
    score: int
    level: str
    reasons: list[str]


class ReportDetailResponse(BaseModel):
    """日报详情响应。"""

    id: int
    report_date: str
    total: int
    hot_products: int
    potential_products: int
    average_score: float
    items: list[ReportDetailItem]

"""Models package."""

from app.models.assistant_history import AssistantHistory
from app.models.crawl_log import CrawlLog
from app.models.crawler_status import CrawlerStatus
from app.models.daily_report import DailyReport, DailyReportItem
from app.models.failed_task import FailedTask
from app.models.product import Product
from app.models.product_history import ProductHistory
from app.models.product_strategy import ProductStrategy
from app.models.product_tag import ProductTag
from app.models.product_tag_relation import ProductTagRelation
from app.models.recommendation_review import RecommendationReview
from app.models.scoring_config import ScoringConfig
from app.models.shop_registry import ShopRegistry
from app.models.task_execution import TaskExecution

__all__ = [
    "AssistantHistory",
    "CrawlLog",
    "Product",
    "ProductHistory",
    "ProductStrategy",
    "ProductTag",
    "ProductTagRelation",
    "DailyReport",
    "DailyReportItem",
    "CrawlerStatus",
    "RecommendationReview",
    "ScoringConfig",
    "ShopRegistry",
    "TaskExecution",
    "FailedTask",
]

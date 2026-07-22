"""Models package."""

from app.models.assistant_history import AssistantHistory
from app.models.crawl_log import CrawlLog
from app.models.crawler_status import CrawlerStatus
from app.models.daily_report import DailyReport, DailyReportItem
from app.models.daily_task_log import DailyTaskLog
from app.models.failed_task import FailedTask
from app.models.login_session import LoginSession, LoginStatus
from app.models.opportunity_score import OpportunityScore
from app.models.product import Product
from app.models.product_history import ProductHistory
from app.models.product_score import ProductScore
from app.models.product_strategy import ProductStrategy
from app.models.product_tag import ProductTag
from app.models.product_tag_relation import ProductTagRelation
from app.models.recommendation_review import RecommendationReview
from app.models.recommendation_publish_record import (
    PublishStatus,
    RecommendationPublishRecord,
)
from app.models.recommendation_status import PoolStatus, RecommendationStatus
from app.models.scoring_config import ScoringConfig
from app.models.shop_registry import ShopRegistry, ShopStatus
from app.models.supplier_match import SupplierMatch
from app.models.supplier_product import SupplierProductDB
from app.models.supply_chain_match import SupplyChainMatch
from app.models.task_execution import TaskExecution

__all__ = [
    "AssistantHistory",
    "CrawlLog",
    "OpportunityScore",
    "Product",
    "ProductHistory",
    "ProductScore",
    "ProductStrategy",
    "ProductTag",
    "ProductTagRelation",
    "DailyReport",
    "DailyReportItem",
    "DailyTaskLog",
    "CrawlerStatus",
    "LoginSession",
    "LoginStatus",
    "RecommendationReview",
    "PublishStatus",
    "RecommendationPublishRecord",
    "PoolStatus",
    "RecommendationStatus",
    "ScoringConfig",
    "ShopRegistry",
    "ShopStatus",
    "SupplierMatch",
    "SupplierProductDB",
    "SupplyChainMatch",
    "TaskExecution",
    "FailedTask",
]

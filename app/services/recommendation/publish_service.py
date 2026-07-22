"""RecommendationPublishService — 推荐商品发布服务 (Phase 46.4 + 47.1).

职责（编排层，不含平台逻辑）：
- 输入 product_id，校验 APPROVED → 可发布
- 创建 PENDING 发布记录
- 构造 PublishContext → 调用 Publisher
- 成功: status→PUBLISHED + record→SUCCESS
- 失败: status 保持 APPROVED + record→FAILED

平台逻辑全部在 app.publishers 中，PublishService 不 import random。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.recommendation_pool_repository import RecommendationPoolRepository
from app.database.recommendation_publish_repository import (
    RecommendationPublishRepository,
)
from app.database.recommendation_status_repository import (
    RecommendationStatusRepository,
)
from app.models.recommendation_publish_record import PublishStatus
from app.models.recommendation_status import PoolStatus
from app.publishers.mock_publisher import MockPublisher, PublishContext, PublishResult
from app.core.exceptions import PublishException


class RecommendationPublishService:
    """推荐商品发布服务 —— 编排层。

    Usage::

        svc = RecommendationPublishService(session)
        result = await svc.publish(product_id=42, platform="taobao")

    测试注入::

        mock_pub = MockPublisher(success_rate=1.0)
        svc = RecommendationPublishService(session, publisher=mock_pub)
    """

    def __init__(
        self,
        session: AsyncSession,
        publisher: MockPublisher | None = None,
    ) -> None:
        """初始化。

        Args:
            session: 数据库会话。
            publisher: MockPublisher 实例（None → 自动创建 MockPublisher）。
        """
        self._session = session
        self._pool_repo = RecommendationPoolRepository(session)
        self._status_repo = RecommendationStatusRepository(session)
        self._publish_repo = RecommendationPublishRepository(session)
        self._publisher = publisher  # 测试注入点

    # ── Public API ────────────────────────────────────────────

    async def publish(
        self,
        product_id: int,
        platform: str = "taobao",
        report_date: date | None = None,
    ) -> dict[str, Any]:
        """发布推荐商品。

        流程（不含平台逻辑）：
        1. 查询当前审核状态 → 必须为 APPROVED
        2. 创建 PENDING 发布记录
        3. 构造 PublishContext
        4. 调用 Publisher.publish(context) → PublishResult
        5. 成功 → record→SUCCESS, status→PUBLISHED
        6. 失败 → record→FAILED, status 保持 APPROVED

        Args:
            product_id: 商品 ID。
            platform: 目标平台 (默认 taobao)。
            report_date: 推荐日期（None = 最新一期）。

        Returns:
            {"success": bool, "publish_status": str, "message": str,
             "record_id": int, "product_id": int, "published_at": str|None}

        Raises:
            ValueError: 状态不是 APPROVED 或商品不存在。
        """
        # 1. 确定 report_date
        effective_date = report_date
        if effective_date is None:
            effective_date = await self._pool_repo.get_latest_report_date()
        if effective_date is None:
            raise PublishException(
                code="NO_RECOMMENDATION_DATA",
                message="暂无推荐数据",
            )

        # 2. 查询审核状态
        current_status = await self._status_repo.get_status(
            product_id, effective_date
        )

        if current_status is None:
            raise PublishException(
                code="NOT_IN_POOL",
                message=f"商品 {product_id} 尚未进入推荐池，无法发布",
            )

        if PoolStatus(current_status.status) != PoolStatus.APPROVED:
            raise PublishException(
                code="NOT_APPROVED",
                message=f"只有 APPROVED 状态的商品可以发布，"
                f"当前状态: {current_status.status}",
            )

        # 3. 创建 PENDING 发布记录
        record = await self._publish_repo.create_record(
            product_id=product_id, platform=platform
        )
        await self._session.flush()

        # 4. 构造 PublishContext
        context = PublishContext(
            product_id=product_id,
            platform=platform,
            report_date=effective_date,
            product=None,          # 未来: 从 pool_repo.get_pool_detail 填充
            supplier_match=None,    # 未来: 查询 SupplierMatch
            supplier_product=None,  # 未来: 查询 SupplierProduct
        )

        # 5. 调用 MockPublisher
        publisher = self._publisher or MockPublisher()
        result: PublishResult = await publisher.publish(context)

        # 6. 根据结果持久化
        if result.success:
            await self._publish_repo.mark_success(record.id)
            await self._status_repo.upsert_status(
                product_id=product_id,
                report_date=effective_date,
                status=PoolStatus.PUBLISHED,
                notes=f"发布成功 — {platform}",
            )
            await self._session.flush()

            logger.info(
                "[Publish] product_id={}: APPROVED → PUBLISHED ({})",
                product_id, platform,
            )
            return {
                "success": True,
                "publish_status": PublishStatus.SUCCESS.value,
                "message": result.message,
                "record_id": record.id,
                "product_id": product_id,
                "published_at": result.published_at.isoformat()
                if result.published_at
                else datetime.now().isoformat(),
            }
        else:
            await self._publish_repo.mark_failed(record.id, result.message)
            await self._session.flush()

            logger.warning(
                "[Publish] product_id={}: publish FAILED — {}",
                product_id, result.message,
            )
            return {
                "success": False,
                "publish_status": PublishStatus.FAILED.value,
                "message": result.message,
                "record_id": record.id,
                "product_id": product_id,
            }

    async def get_publish_history(
        self, product_id: int, limit: int = 20
    ) -> list[dict[str, Any]]:
        """查询发布历史。"""
        records = await self._publish_repo.get_history(product_id, limit=limit)
        return [
            {
                "id": r.id,
                "product_id": r.product_id,
                "status": r.status,
                "platform": r.platform,
                "error_message": r.error_message,
                "retry_count": r.retry_count,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "published_at": r.published_at.isoformat() if r.published_at else None,
            }
            for r in records
        ]

"""Knowledge builder — auto-generate tags from review feedback."""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.knowledge_repository import KnowledgeRepository
from app.database.product_repository import ProductRepository
from app.database.review_repository import ReviewRepository


class KnowledgeBuilder:
    """知识库构建器 — 从复盘结果自动沉淀经验标签。

    规则：
      - SUCCESS 复盘 → 生成 SUCCESS_PATTERN 标签
        - sales_change >= 50  → "高速增长商品"
        - sales_change < 50   → "稳定增长商品"
        - market_level == LOW → "蓝海商品"
      - FAILED 复盘 → 生成 FAIL_PATTERN 标签
        - sales_change <= -30 → "红海风险商品"
        - trend_change <= -20 → "趋势衰减商品"

    Usage::

        builder = KnowledgeBuilder(session)
        result = await builder.learn_from_reviews()
    """

    # ── Tag definitions ──────────────────────────────────────

    _SUCCESS_TAGS: dict[str, str] = {
        "高速增长商品": "24小时销量增幅超过50%，具有爆发潜力",
        "稳定增长商品": "销量稳步上升，适合持续推荐",
        "蓝海商品": "竞争程度低，市场空间大",
    }

    _FAIL_TAGS: dict[str, str] = {
        "红海风险商品": "竞争激烈且销量下滑，不建议推荐",
        "趋势衰减商品": "趋势评分持续走低，市场热度下降",
    }

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._knowledge_repo = KnowledgeRepository(session)
        self._review_repo = ReviewRepository(session)
        self._product_repo = ProductRepository(session)

    # ── Public API ────────────────────────────────────────────

    async def learn_from_reviews(self) -> dict[str, Any]:
        """从复盘记录中学习，自动生成/绑定标签。

        Returns:
            {
                "processed": int,  # 处理的复盘记录数
                "success_tags": int,  # 生成的成功模式标签数
                "fail_tags": int,  # 生成的失败模式标签数
                "bindings": int,  # 新增绑定数
            }
        """
        reviews = list(await self._review_repo.get_reviews(limit=100))
        if not reviews:
            logger.info("[Knowledge] 无复盘记录，跳过学习")
            return {"processed": 0, "success_tags": 0, "fail_tags": 0, "bindings": 0}

        success_tags = 0
        fail_tags = 0
        bindings = 0

        for review in reviews:
            if review.result == "SUCCESS":
                tags_to_bind = self._analyze_success(review)
                for tag_name, description in tags_to_bind:
                    tag = await self._knowledge_repo.add_tag(
                        name=tag_name,
                        tag_type="SUCCESS_PATTERN",
                        description=description,
                    )
                    await self._knowledge_repo.bind_product_tag(
                        product_id=review.product_id,
                        tag_id=tag.id,
                        confidence=1.0,
                        source="LEARNING",
                    )
                    success_tags += 1
                    bindings += 1

            elif review.result == "FAILED":
                tags_to_bind = self._analyze_failure(review)
                for tag_name, description in tags_to_bind:
                    tag = await self._knowledge_repo.add_tag(
                        name=tag_name,
                        tag_type="FAIL_PATTERN",
                        description=description,
                    )
                    await self._knowledge_repo.bind_product_tag(
                        product_id=review.product_id,
                        tag_id=tag.id,
                        confidence=1.0,
                        source="LEARNING",
                    )
                    fail_tags += 1
                    bindings += 1

        try:
            await self._session.commit()
        except Exception as e:
            logger.warning("[Knowledge] 提交事务失败: {}", e)

        result = {
            "processed": len(reviews),
            "success_tags": success_tags,
            "fail_tags": fail_tags,
            "bindings": bindings,
        }
        logger.info(
            "[Knowledge] 学习完成: processed={}, success={}, fail={}, bindings={}",
            result["processed"], success_tags, fail_tags, bindings,
        )
        return result

    # ── Analysis helpers ──────────────────────────────────────

    def _analyze_success(self, review: Any) -> list[tuple[str, str]]:
        """分析成功复盘，返回应绑定的 (tag_name, description) 列表。"""
        tags: list[tuple[str, str]] = []

        if review.sales_change >= 50:
            tags.append(("高速增长商品", self._SUCCESS_TAGS["高速增长商品"]))
        else:
            tags.append(("稳定增长商品", self._SUCCESS_TAGS["稳定增长商品"]))

        return tags

    def _analyze_failure(self, review: Any) -> list[tuple[str, str]]:
        """分析失败复盘，返回应绑定的 (tag_name, description) 列表。"""
        tags: list[tuple[str, str]] = []

        if review.sales_change <= -30:
            tags.append(("红海风险商品", self._FAIL_TAGS["红海风险商品"]))
        if review.trend_change <= -20:
            tags.append(("趋势衰减商品", self._FAIL_TAGS["趋势衰减商品"]))

        # 兜底：如果没有具体标签，给一个通用失败标签
        if not tags:
            tags.append(("红海风险商品", self._FAIL_TAGS["红海风险商品"]))

        return tags

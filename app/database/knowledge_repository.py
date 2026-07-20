"""KnowledgeRepository — CRUD for tags and product↔tag relations."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_tag import ProductTag
from app.models.product_tag_relation import ProductTagRelation


class KnowledgeRepository:
    """知识库数据访问层。

    负责标签的创建、查询以及商品与标签的绑定关系管理。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Tag CRUD ──────────────────────────────────────────────

    async def add_tag(
        self, name: str, tag_type: str, description: str = ""
    ) -> ProductTag:
        """创建或获取标签（幂等：名称已存在则返回已有记录）。"""
        stmt = select(ProductTag).where(ProductTag.name == name)
        result = await self._session.execute(stmt)
        tag = result.scalar_one_or_none()
        if tag is not None:
            return tag
        tag = ProductTag(name=name, type=tag_type, description=description)
        self._session.add(tag)
        await self._session.flush()
        return tag

    async def get_all_tags(self) -> Sequence[ProductTag]:
        """获取所有标签。"""
        stmt = select(ProductTag).order_by(ProductTag.type, ProductTag.name)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_tag_by_name(self, name: str) -> ProductTag | None:
        """按名称查询标签。"""
        stmt = select(ProductTag).where(ProductTag.name == name)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ── Product ↔ Tag binding ─────────────────────────────────

    async def bind_product_tag(
        self,
        product_id: int,
        tag_id: int,
        confidence: float = 1.0,
        source: str = "AI",
    ) -> ProductTagRelation:
        """绑定商品与标签（幂等：已存在则更新 confidence）。"""
        stmt = select(ProductTagRelation).where(
            ProductTagRelation.product_id == product_id,
            ProductTagRelation.tag_id == tag_id,
        )
        result = await self._session.execute(stmt)
        relation = result.scalar_one_or_none()
        if relation is not None:
            relation.confidence = confidence
            relation.source = source
            await self._session.flush()
            return relation
        relation = ProductTagRelation(
            product_id=product_id,
            tag_id=tag_id,
            confidence=confidence,
            source=source,
        )
        self._session.add(relation)
        await self._session.flush()
        return relation

    async def get_product_tags(self, product_id: int) -> list[dict]:
        """获取商品的所有标签（含标签详情）。"""
        stmt = (
            select(ProductTagRelation, ProductTag)
            .join(ProductTag, ProductTagRelation.tag_id == ProductTag.id)
            .where(ProductTagRelation.product_id == product_id)
        )
        result = await self._session.execute(stmt)
        rows = result.all()
        return [
            {
                "tag_id": rel.tag_id,
                "name": tag.name,
                "type": tag.type,
                "confidence": rel.confidence,
                "source": rel.source,
            }
            for rel, tag in rows
        ]

    async def search_by_tag(self, tag_name: str) -> list[int]:
        """按标签名搜索绑定该标签的所有商品 ID。"""
        stmt = (
            select(ProductTagRelation.product_id)
            .join(ProductTag, ProductTagRelation.tag_id == ProductTag.id)
            .where(ProductTag.name == tag_name)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_success_patterns(self) -> list[dict]:
        """获取所有成功模式标签及其绑定数量。"""
        from sqlalchemy import func

        stmt = (
            select(ProductTag, func.count(ProductTagRelation.id).label("product_count"))
            .outerjoin(
                ProductTagRelation, ProductTagRelation.tag_id == ProductTag.id
            )
            .where(ProductTag.type == "SUCCESS_PATTERN")
            .group_by(ProductTag.id)
            .order_by(func.count(ProductTagRelation.id).desc())
        )
        result = await self._session.execute(stmt)
        rows = result.all()
        return [
            {"tag_id": tag.id, "name": tag.name, "description": tag.description, "product_count": count}
            for tag, count in rows
        ]

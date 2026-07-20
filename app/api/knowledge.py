"""Knowledge API endpoints — product tags and knowledge base."""

from fastapi import APIRouter, HTTPException

from app.database.base import get_async_session_factory
from app.database.knowledge_repository import KnowledgeRepository
from app.services.knowledge.builder import KnowledgeBuilder

router = APIRouter()


@router.get("/knowledge/tags")
async def knowledge_tags() -> list[dict]:
    """获取所有标签列表。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            repo = KnowledgeRepository(session)
            tags = await repo.get_all_tags()
            return [
                {
                    "id": t.id,
                    "name": t.name,
                    "type": t.type,
                    "description": t.description,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in tags
            ]
    except Exception:
        raise HTTPException(status_code=500, detail="获取标签列表失败")


@router.get("/knowledge/products/{product_id}")
async def knowledge_product(product_id: int) -> dict:
    """获取指定商品的知识库标签。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            repo = KnowledgeRepository(session)
            tags = await repo.get_product_tags(product_id)
            return {
                "product_id": product_id,
                "tags": tags,
                "tag_count": len(tags),
            }
    except Exception:
        raise HTTPException(status_code=500, detail="获取商品标签失败")


@router.post("/knowledge/learn")
async def knowledge_learn() -> dict:
    """手动触发知识库学习（从复盘记录生成标签）。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            builder = KnowledgeBuilder(session)
            return await builder.learn_from_reviews()
    except Exception:
        raise HTTPException(status_code=500, detail="知识库学习失败")

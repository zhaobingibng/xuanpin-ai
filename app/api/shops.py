"""Shops API — shop registry CRUD endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database.base import get_async_session_factory
from app.services.shop_service import ShopService

router = APIRouter()


# ── Request / Response schemas ────────────────────────────────


class ShopCreateRequest(BaseModel):
    """创建店铺请求。"""
    platform: str = Field(..., max_length=100, description="平台名称")
    shop_id: str = Field(..., max_length=200, description="平台店铺标识")
    shop_name: str = Field(..., max_length=500, description="店铺名称")
    shop_url: str | None = Field(default=None, description="店铺链接")
    category: str | None = Field(default=None, max_length=200, description="主营品类")
    fans: int = Field(default=0, ge=0, description="粉丝数")
    priority: int = Field(default=1, ge=1, le=3, description="优先级 1-3")
    enabled: bool = Field(default=True, description="是否启用")
    monitor_strategy: str = Field(default="daily", max_length=50, description="监控策略")


class ShopUpdateRequest(BaseModel):
    """更新店铺请求。所有字段可选。"""
    shop_name: str | None = Field(default=None, max_length=500)
    shop_url: str | None = None
    category: str | None = Field(default=None, max_length=200)
    fans: int | None = Field(default=None, ge=0)
    priority: int | None = Field(default=None, ge=1, le=3)
    enabled: bool | None = None
    monitor_strategy: str | None = Field(default=None, max_length=50)


def _shop_to_dict(shop) -> dict:
    """Serialize ShopRegistry to dict."""
    return {
        "id": shop.id,
        "platform": shop.platform,
        "shop_id": shop.shop_id,
        "shop_name": shop.shop_name,
        "shop_url": shop.shop_url,
        "category": shop.category,
        "fans": shop.fans,
        "priority": shop.priority,
        "enabled": shop.enabled,
        "last_scan_at": shop.last_scan_at.isoformat() if shop.last_scan_at else None,
        "monitor_strategy": shop.monitor_strategy,
        "created_at": shop.created_at.isoformat() if shop.created_at else None,
        "updated_at": shop.updated_at.isoformat() if shop.updated_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────


@router.get("/api/shops")
async def list_shops() -> list[dict]:
    """获取所有店铺列表。"""
    try:
        factory = get_async_session_factory()
        async with factory() as session:
            svc = ShopService(session)
            shops = await svc.list_all_shops()
            return [_shop_to_dict(s) for s in shops]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取店铺列表失败: {e}")


@router.post("/api/shops")
async def create_shop(req: ShopCreateRequest) -> dict:
    """创建新店铺。"""
    try:
        factory = get_async_session_factory()
        async with factory() as session:
            svc = ShopService(session)

            # Check duplicate
            existing = await svc.find_by_shop_id(req.platform, req.shop_id)
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=f"店铺已存在: platform={req.platform}, shop_id={req.shop_id}",
                )

            shop = await svc.create_shop(
                platform=req.platform,
                shop_id=req.shop_id,
                shop_name=req.shop_name,
                shop_url=req.shop_url,
                category=req.category,
                fans=req.fans,
                priority=req.priority,
                enabled=req.enabled,
                monitor_strategy=req.monitor_strategy,
            )
            return _shop_to_dict(shop)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建店铺失败: {e}")


@router.patch("/api/shops/{shop_pk}")
async def update_shop(shop_pk: int, req: ShopUpdateRequest) -> dict:
    """更新店铺信息。"""
    try:
        factory = get_async_session_factory()
        async with factory() as session:
            svc = ShopService(session)
            update_data = req.model_dump(exclude_none=True)
            if not update_data:
                raise HTTPException(status_code=400, detail="没有需要更新的字段")
            shop = await svc.update_shop(shop_pk, **update_data)
            if shop is None:
                raise HTTPException(status_code=404, detail=f"店铺 {shop_pk} 不存在")
            return _shop_to_dict(shop)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新店铺失败: {e}")


@router.delete("/api/shops/{shop_pk}")
async def delete_shop(shop_pk: int) -> dict:
    """删除店铺。"""
    try:
        factory = get_async_session_factory()
        async with factory() as session:
            svc = ShopService(session)
            deleted = await svc.delete_shop(shop_pk)
            if not deleted:
                raise HTTPException(status_code=404, detail=f"店铺 {shop_pk} 不存在")
            return {"message": f"店铺 {shop_pk} 已删除"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除店铺失败: {e}")

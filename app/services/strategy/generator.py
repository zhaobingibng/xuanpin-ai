"""ProductStrategyGenerator — auto-generate marketing strategy for products."""

from __future__ import annotations

import json
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.knowledge_repository import KnowledgeRepository
from app.database.strategy_repository import StrategyRepository
from app.models.product_strategy import ProductStrategy


# ── Audience / scene pools ─────────────────────────────────────

_AUDIENCE_PREFIXES = ["学生党必备", "打工人必入", "宝妈推荐", "居家好物", "潮流达人"]
_SCENE_PREFIXES = ["通勤路上", "办公室神器", "宿舍好物", "旅行必备", "送礼首选"]


class ProductStrategyGenerator:
    """AI商品运营方案生成器。

    根据商品数据自动生成完整运营方案：
      - 营销标题（关键词 + 卖点 + 场景）
      - 3-5 条核心卖点
      - 小红书种草文案
      - 闲鱼转让文案
      - 价格策略与利润分析

    输入参数 (product dict)::

        {
            "product_id": 1,
            "name": "蓝牙耳机",
            "price": 99.0,
            "sales_24h": 500,
            "trend_score": 75.0,
            "lifecycle": "HOT",
            "competition_score": 60,
            "knowledge_tags": [{"name": "高速增长商品", "type": "SUCCESS_PATTERN"}],
        }

    Usage::

        generator = ProductStrategyGenerator(session)
        strategy = await generator.generate(product_info)
    """

    _COST_RATIO = 0.6

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._strategy_repo = StrategyRepository(session)
        self._knowledge_repo = KnowledgeRepository(session)

    # ── Public API ────────────────────────────────────────────

    async def generate(self, product: dict[str, Any]) -> dict[str, Any]:
        """为指定商品生成运营方案并持久化。

        Args:
            product: 商品信息字典。

        Returns:
            生成的运营方案字典。
        """
        product_id = product.get("product_id", 0)
        name = product.get("name", "商品")
        price = float(product.get("price", 0))
        sales = int(product.get("sales_24h", 0))
        trend = float(product.get("trend_score", 50))
        lifecycle = product.get("lifecycle", "NEW")
        tags = product.get("knowledge_tags", [])

        # 生成各部分
        selling_points = self._generate_selling_points(name, sales, trend, lifecycle, tags)
        title = self._generate_title(name, selling_points)
        xiaohongshu = self._generate_xiaohongshu_copy(name, selling_points, tags)
        xianyu = self._generate_xianyu_copy(name, selling_points, price)
        price_strategy = self._generate_price_strategy(price)
        profit = self._generate_profit_analysis(price, price_strategy)

        # 持久化
        record = ProductStrategy(
            product_id=product_id,
            title=title,
            selling_points=json.dumps(selling_points, ensure_ascii=False),
            xiaohongshu_copy=xiaohongshu,
            xianyu_copy=xianyu,
            price_strategy=json.dumps(price_strategy, ensure_ascii=False),
            profit_analysis=json.dumps(profit, ensure_ascii=False),
        )
        await self._strategy_repo.save_strategy(record)
        try:
            await self._session.commit()
        except Exception as e:
            logger.warning("[Strategy] 保存失败: {}", e)

        result = {
            "product_id": product_id,
            "title": title,
            "selling_points": selling_points,
            "xiaohongshu_copy": xiaohongshu,
            "xianyu_copy": xianyu,
            "price_strategy": price_strategy,
            "profit_analysis": profit,
        }

        logger.info("[Strategy] product_id={}, title='{}'", product_id, title)
        return result

    # ── Title ─────────────────────────────────────────────────

    @staticmethod
    def _generate_title(name: str, selling_points: list[str]) -> str:
        """生成运营标题：场景前缀 + 核心卖点 + 商品名。"""
        # 选择前缀
        prefix = _AUDIENCE_PREFIXES[hash(name) % len(_AUDIENCE_PREFIXES)]
        # 取第一个卖点关键词
        hook = selling_points[0] if selling_points else ""
        return f"{prefix}{hook} {name}"

    # ── Selling points ────────────────────────────────────────

    @staticmethod
    def _generate_selling_points(
        name: str,
        sales: int,
        trend: float,
        lifecycle: str,
        tags: list[dict[str, Any]],
    ) -> list[str]:
        """生成 3-5 条卖点。"""
        points: list[str] = []

        # 销量卖点
        if sales >= 500:
            points.append("销量爆款，千人抢购")
        elif sales >= 100:
            points.append("热销商品，口碑验证")
        else:
            points.append("小众精选，独特品味")

        # 趋势卖点
        if trend >= 70:
            points.append("趋势上涨，入手好时机")
        elif trend >= 50:
            points.append("稳定增长，持续热卖")

        # 生命周期卖点
        if lifecycle == "HOT":
            points.append("爆款阶段，供不应求")
        elif lifecycle == "RISING":
            points.append("新锐上升，潜力无限")

        # 知识库标签卖点
        success_tags = [t for t in tags if t.get("type") == "SUCCESS_PATTERN"]
        if success_tags:
            points.append(f"AI认证：{success_tags[0].get('name', '优质商品')}")

        # 兜底
        if len(points) < 3:
            points.append("高性价比之选")
        if len(points) < 3:
            points.append("品质保障，售后无忧")

        return points[:5]

    # ── Xiaohongshu copy ──────────────────────────────────────

    @staticmethod
    def _generate_xiaohongshu_copy(
        name: str,
        selling_points: list[str],
        tags: list[dict[str, Any]],
    ) -> str:
        """生成小红书种草文案。"""
        scene = _SCENE_PREFIXES[hash(name) % len(_SCENE_PREFIXES)]
        sp_text = "\n".join(f"✅ {sp}" for sp in selling_points)

        # 话题标签
        hashtag_topics = ["好物推荐", "种草", "必买清单"]
        if tags:
            tag_names = [t.get("name", "") for t in tags[:2] if t.get("name")]
            hashtag_topics.extend(tag_names)
        hashtags = " ".join(f"#{t}" for t in hashtag_topics)

        return (
            f"📢 {scene}｜{name}\n\n"
            f"姐妹们！今天必须安利这款 {name}！\n\n"
            f"{sp_text}\n\n"
            f"真的太好用了，闭眼入不踩雷！\n\n"
            f"{hashtags}"
        )

    # ── Xianyu copy ───────────────────────────────────────────

    @staticmethod
    def _generate_xianyu_copy(
        name: str,
        selling_points: list[str],
        price: float,
    ) -> str:
        """生成闲鱼转让文案。"""
        sp_text = "、".join(selling_points[:3])
        discount = int(price * 0.85)

        return (
            f"【转让】{name}\n\n"
            f"商品描述：全新未拆封 {name}，{selling_points[0] if selling_points else '品质保证'}。\n\n"
            f"核心卖点：{sp_text}\n\n"
            f"成交话术：原价{price:.0f}，现在{discount:.0f}包邮带走，先到先得！"
        )

    # ── Price strategy ────────────────────────────────────────

    @classmethod
    def _generate_price_strategy(cls, price: float) -> dict[str, float]:
        """生成价格策略。"""
        cost = round(price * cls._COST_RATIO, 2)
        return {
            "cost": cost,
            "sell": round(price, 2),
            "profit": round(price - cost, 2),
        }

    # ── Profit analysis ───────────────────────────────────────

    @classmethod
    def _generate_profit_analysis(
        cls, price: float, price_strategy: dict[str, float]
    ) -> dict[str, Any]:
        """生成利润分析。"""
        cost = price_strategy["cost"]
        profit = price_strategy["profit"]
        margin = round(profit / price * 100, 1) if price > 0 else 0.0

        return {
            "cost": cost,
            "sell": price_strategy["sell"],
            "profit_per_unit": profit,
            "profit_margin": f"{margin}%",
            "daily_estimate": round(profit * 10, 2),  # 假设日销10件
            "monthly_estimate": round(profit * 10 * 30, 2),  # 假设月销300件
        }

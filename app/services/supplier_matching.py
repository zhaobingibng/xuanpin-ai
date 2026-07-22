"""Supplier Matching Service — 淘宝新品 → 1688供应链匹配服务.

统一匹配入口：match_products_with_matcher()
   └── 内部调用 ProductMatcher → supplier_products 表
   └── 自动计算利润
   └── 返回 SupplierMatch 记录列表

旧方法（已弃用，仅保留兼容）：
  - match_product()           — Jaccard 2-gram 相似度
  - create_match_record()     — 手动创建匹配记录
  - clean_title()             — 品牌词清洗
  - generate_search_keyword() — 搜索关键词生成
  - calculate_similarity()    — 旧相似度算法
"""

from __future__ import annotations

import re
import warnings
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.supplier_match import SupplierMatch


# ── 品牌词列表（用于标题清洗）─────────────────────────────────

BRAND_WORDS = [
    # 食品类
    "三只松鼠", "良品铺子", "百草味", "来伊份", "洽洽",
    "旺旺", "乐事", "奥利奥", "德芙", "费列罗",
    # 美妆类
    "完美日记", "花西子", "雅诗兰黛", "兰蔻", "欧莱雅",
    "资生堂", "sk2", "mac", "迪奥", "香奈儿",
    # 服饰类
    "优衣库", "zara", "hm", "耐克", "阿迪达斯", "安踏",
    "李宁", "彪马", "新百伦",
    # 数码类
    "华为", "小米", "苹果", "oppo", "vivo", "三星",
    # 通用
    "同款", "网红", "爆款", "热卖", "包邮", "特价",
]

# ── 促销词 ─────────────────────────────────────────────────

PROMO_WORDS = [
    "促销", "特价", "包邮", "秒杀", "限时", "抢购",
    "新品", "上新", "热卖", "爆款", "同款", "网红",
    "现货", "直发", "工厂", "直销", "批发",
]

# ── 特殊符号正则 ───────────────────────────────────────────

SPECIAL_CHARS_PATTERN = re.compile(r"[【】\[\]()（）{}<>《》「」『』★☆♪♫#+@&$%€£¥]")
NUMBER_PATTERN = re.compile(r"\d+[gGmMlL斤两克毫升片包袋盒罐瓶支条双件套]")


class SupplierMatchingService:
    """供应链匹配服务 — 统一入口为 match_products_with_matcher()。

    Usage::

        # ★ 推荐：统一入口（ProductMatcher + DB + 利润计算 + SupplierMatch 记录）
        service = SupplierMatchingService()
        matches = await service.match_products_with_matcher(session, product, top_k=3)
        for m in matches:
            print(m.supplier_title, m.final_score, m.profit_margin)

        # 兼容保留：旧接口（Jaccard 相似度）
        result = service.match_product(product, supplier_products)

        # 兼容保留：DB 匹配（仅返回原始数据）
        results = await service.match_with_db(session, product, top_k=3)
    """

    def __init__(self, alibaba_crawler: Any = None):
        """初始化匹配服务。

        Args:
            alibaba_crawler: 1688爬虫实例（可选），用于搜索供应商。
        """
        self._alibaba_crawler = alibaba_crawler

    # ── Public API ──────────────────────────────────────────

    def match_product(
        self,
        product: Product,
        supplier_products: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """为淘宝商品匹配1688供应商。

        Args:
            product: 淘宝商品 ORM 实例。
            supplier_products: 1688候选商品列表，格式:
                [{"title": "...", "url": "...", "price": 18.0}, ...]

        Returns:
            匹配结果字典，或 None（无匹配）。
        """
        if not product or not product.name:
            return None

        # Step 1: 清洗标题
        cleaned_title = self.clean_title(product.name)

        # Step 2: 生成搜索关键词
        search_keyword = self.generate_search_keyword(cleaned_title)

        # Step 3: 获取候选供应商（如果未提供且配置了爬虫，则调用爬虫）
        if supplier_products is None and self._alibaba_crawler:
            # 异步调用会在集成层处理
            supplier_products = []

        if not supplier_products:
            logger.warning("[SupplierMatching] No supplier products for: {}", product.name[:30])
            return None

        # Step 4: 计算相似度并找到最佳匹配
        best_match = self._find_best_match(cleaned_title, supplier_products)

        if not best_match:
            return None

        # Step 5: 计算利润
        profit_data = self.calculate_profit(product.price, best_match["price"])

        return {
            "supplier_title": best_match["title"],
            "supplier_url": best_match.get("url"),
            "supplier_price": best_match["price"],
            "similarity_score": best_match["similarity"],
            "estimated_profit": profit_data["estimated_profit"],
            "profit_margin": profit_data["profit_margin"],
        }

    # ── DB-based matching (Phase 28 ProductMatcher) ──────────

    async def match_with_db(
        self,
        session: AsyncSession,
        product: Product,
        top_k: int = 3,
        image: "str | Path | bytes | None" = None,
    ) -> list[dict[str, Any]]:
        """使用 ProductMatcher 从 supplier_products 表匹配。

        Args:
            session: 异步数据库会话。
            product: 淘宝商品 ORM 实例。
            top_k: 返回 top-k 结果数量。
            image: 可选查询商品图片，支持 URL/PIL Image/bytes/Path。
                None → 纯文本匹配。

        Returns:
            匹配结果列表，每项包含:
            - supplier_product_id: 1688 商品数据库 ID
            - title: 1688 商品标题
            - price: 1688 价格
            - url: 1688 商品链接
            - offer_id: 1688 offer ID
            - shop_name: 店铺名称
            - image: 商品图片
            - similarity_score: 融合最终评分 [0,1]
            - text_score: 文本相似度 [0,1]
            - feature_score: 特征匹配评分 [0,1]
            - image_score: 图片相似度 [0,1] 或 None
            - final_score: 融合最终评分 [0,1]（同 similarity_score）
        """
        from pathlib import Path as _Path
        from app.matching.product_matcher import ProductMatcher

        if not product or not product.name:
            logger.warning("[SupplierMatching.match_with_db] Empty product")
            return []

        matcher = ProductMatcher(session)
        results = await matcher.match_product(product.name, image=image, top_k=top_k)
        return results

    # ── Unified entry (Phase 30) ─────────────────────────────

    async def match_products_with_matcher(
        self,
        session: AsyncSession,
        product: Product,
        top_k: int = 3,
        image: "str | Path | bytes | None" = None,
    ) -> list[SupplierMatch]:
        """★ 统一匹配入口 — 匹配 + 利润计算 + 创建 SupplierMatch 记录。

        调用链：
            ProductMatcher.match_product() → 匹配 top-k 候选商品
            → calculate_profit() 逐条计算利润
            → 创建 SupplierMatch 记录

        Args:
            session: 异步数据库会话。
            product: 淘宝商品 ORM 实例。
            top_k: 匹配结果数量（默认 3）。
            image: 可选查询商品图片，支持 URL/PIL Image/bytes/Path。
                None → 纯文本匹配。

        Returns:
            SupplierMatch 记录列表（已设置所有字段，未 flush）。

        Example:
            service = SupplierMatchingService()
            matches = await service.match_products_with_matcher(session, product)
            for m in matches:
                session.add(m)
            await session.commit()
        """
        # Step 1: 调用 ProductMatcher 获取匹配结果
        raw_results = await self.match_with_db(
            session, product, top_k=top_k, image=image,
        )

        if not raw_results:
            logger.info(
                "[SupplierMatching] 无匹配: product_id={}, title={}",
                product.id, str(product.name)[:30],
            )
            return []

        # Step 2: 逐条计算利润并创建 SupplierMatch 记录
        matches: list[SupplierMatch] = []
        for rank, r in enumerate(raw_results, 1):
            supplier_price = r.get("price", 0.0)
            profit_data = self.calculate_profit(product.price, supplier_price)

            match = SupplierMatch(
                product_id=product.id,
                supplier_product_id=r.get("supplier_product_id"),
                supplier_title=r.get("title", ""),
                supplier_url=r.get("url"),
                supplier_price=supplier_price,
                similarity_score=r.get("final_score", 0.0),
                text_score=r.get("text_score"),
                feature_score=r.get("feature_score"),
                image_score=r.get("image_score"),
                rank=rank,
                estimated_profit=profit_data["estimated_profit"],
                profit_margin=profit_data["profit_margin"],
            )
            matches.append(match)

        logger.info(
            "[SupplierMatching] 匹配完成: product_id={}, count={}, "
            "best_score={:.3f}, best_margin={:.1f}%",
            product.id, len(matches),
            matches[0].similarity_score if matches else 0,
            matches[0].profit_margin if matches else 0,
        )
        return matches

    # ── Deprecated methods (保留兼容，标记弃用) ───────────────

    def match_product(
        self,
        product: Product,
        supplier_products: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """[DEPRECATED] 旧 Jaccard 匹配方法。请使用 match_products_with_matcher()。

        保留仅用于向后兼容，不再推荐使用。
        """
        warnings.warn(
            "match_product() is deprecated. Use match_products_with_matcher() instead.",
            DeprecationWarning, stacklevel=2,
        )

        if not product or not product.name:
            return None

        # Step 1: 清洗标题
        cleaned_title = self.clean_title(product.name)

        # Step 2: 生成搜索关键词
        search_keyword = self.generate_search_keyword(cleaned_title)

        # Step 3: 获取候选供应商（如果未提供且配置了爬虫，则调用爬虫）
        if supplier_products is None and self._alibaba_crawler:
            supplier_products = []

        if not supplier_products:
            logger.warning("[SupplierMatching] No supplier products for: {}", product.name[:30])
            return None

        # Step 4: 计算相似度并找到最佳匹配
        best_match = self._find_best_match(cleaned_title, supplier_products)

        if not best_match:
            return None

        # Step 5: 计算利润
        profit_data = self.calculate_profit(product.price, best_match["price"])

        return {
            "supplier_title": best_match["title"],
            "supplier_url": best_match.get("url"),
            "supplier_price": best_match["price"],
            "similarity_score": best_match["similarity"],
            "estimated_profit": profit_data["estimated_profit"],
            "profit_margin": profit_data["profit_margin"],
        }

    def create_match_record(
        self,
        product: Product,
        match_data: dict[str, Any],
    ) -> SupplierMatch:
        """[DEPRECATED] 旧创建匹配记录方法。请使用 match_products_with_matcher()。

        保留仅用于向后兼容，不再推荐使用。
        """
        warnings.warn(
            "create_match_record() is deprecated. Use match_products_with_matcher() instead.",
            DeprecationWarning, stacklevel=2,
        )
        return SupplierMatch(
            product_id=product.id,
            supplier_title=match_data["supplier_title"],
            supplier_url=match_data.get("supplier_url"),
            supplier_price=match_data["supplier_price"],
            similarity_score=match_data["similarity_score"],
            estimated_profit=match_data["estimated_profit"],
            profit_margin=match_data["profit_margin"],
        )

    # ── 标题清洗 ────────────────────────────────────────────

    def clean_title(self, title: str) -> str:
        """[DEPRECATED] 旧标题清洗方法。请使用 FeatureExtractor.extract()。

        保留仅用于向后兼容，不再推荐使用。
        """
        if not title:
            return ""

        result = title

        # 1. 去除品牌词
        for brand in BRAND_WORDS:
            result = result.replace(brand, "")

        # 2. 去除促销词
        for promo in PROMO_WORDS:
            result = result.replace(promo, "")

        # 3. 去除特殊符号
        result = SPECIAL_CHARS_PATTERN.sub("", result)

        # 4. 去除数字规格
        result = NUMBER_PATTERN.sub("", result)

        # 5. 清理多余空格
        result = " ".join(result.split())

        return result.strip()

    # ── 关键词生成 ──────────────────────────────────────────

    def generate_search_keyword(self, cleaned_title: str) -> str:
        """[DEPRECATED] 旧关键词生成方法。请使用 TextMatcher + ProductMatcher。"""
        if not cleaned_title:
            return ""

        # 去除常见连接词
        stop_words = ["味", "的", "型", "款", "装", "装", "装"]
        result = cleaned_title

        for word in stop_words:
            # 只去除作为连接词的"味"（不在词首）
            if word == "味" and result.startswith(word):
                continue
            result = result.replace(word, "", 1) if word in result[1:] else result

        return result.strip()

    # ── 相似度计算 ──────────────────────────────────────────

    def calculate_similarity(self, title1: str, title2: str) -> float:
        """[DEPRECATED] 旧 Jaccard 相似度。请使用 TextMatcher.calculate_similarity()。

        保留仅用于向后兼容，不再推荐使用。
        """
        if not title1 or not title2:
            return 0.0

        # 分词（简单按字符分割）
        words1 = set(self._tokenize(title1))
        words2 = set(self._tokenize(title2))

        if not words1 or not words2:
            return 0.0

        # Jaccard 相似度
        intersection = words1 & words2
        union = words1 | words2

        if not union:
            return 0.0

        similarity = len(intersection) / len(union)
        return round(similarity * 100, 1)

    def _tokenize(self, text: str) -> list[str]:
        """简单分词（2-gram）。"""
        if len(text) < 2:
            return [text] if text else []

        # 使用 2-gram 分词
        return [text[i:i+2] for i in range(len(text) - 1)]

    # ── 利润计算 ────────────────────────────────────────────

    def calculate_profit(
        self,
        sell_price: float,
        cost_price: float,
    ) -> dict[str, float]:
        """计算利润。

        公式：
        - 利润率 = (售价 - 成本) / 售价 * 100
        - 预估利润 = 售价 - 成本

        Args:
            sell_price: 淘宝售价。
            cost_price: 1688成本价。

        Returns:
            {"estimated_profit": float, "profit_margin": float}

        Example:
            售价69, 成本18 -> 利润率73.9%
        """
        if sell_price <= 0 or cost_price <= 0:
            return {"estimated_profit": 0.0, "profit_margin": 0.0}

        estimated_profit = sell_price - cost_price
        profit_margin = (estimated_profit / sell_price) * 100

        return {
            "estimated_profit": round(estimated_profit, 2),
            "profit_margin": round(profit_margin, 1),
        }

    # ── 内部方法 ────────────────────────────────────────────

    def _find_best_match(
        self,
        cleaned_title: str,
        supplier_products: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """找到最佳匹配的供应商。

        Args:
            cleaned_title: 清洗后的淘宝标题。
            supplier_products: 1688候选商品列表。

        Returns:
            最佳匹配结果，或 None。
        """
        best_match = None
        best_similarity = 0.0

        for supplier in supplier_products:
            supplier_title = supplier.get("title", "")
            similarity = self.calculate_similarity(cleaned_title, supplier_title)

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = {
                    "title": supplier_title,
                    "url": supplier.get("url"),
                    "price": supplier.get("price", 0.0),
                    "similarity": similarity,
                }

        # 相似度阈值：至少 30 分
        if best_match and best_similarity >= 30.0:
            return best_match

        return None

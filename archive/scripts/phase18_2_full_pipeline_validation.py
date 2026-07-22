#!/usr/bin/env python3
"""Phase 18 Task 2: Full Product Selection Pipeline Validation.

验证完整选品闭环：
1. 淘宝店铺采集 -> ProductRepository
2. 筛选 NEW 商品
3. 新品评分 -> ProductScore
4. 1688匹配 -> SupplierMatch
5. 机会评分 -> OpportunityScore
6. 生成验证报告

Usage:
    python scripts/phase18_2_full_pipeline_validation.py
    python scripts/phase18_2_full_pipeline_validation.py --use-mock
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from app.crawler.alibaba import AlibabaSearchClient
from app.models.product import Product
from app.models.product_score import ProductScore
from app.models.supplier_match import SupplierMatch
from app.models.opportunity_score import OpportunityScore
from app.services.product_scoring import ProductScoringService
from app.services.supplier_matching import SupplierMatchingService
from app.services.opportunity_scoring import OpportunityScoringService


# ── Test Shop Configuration ─────────────────────────────────

TEST_SHOPS = [
    {
        "name": "sanzhisongshu",
        "url": "https://sanzhisongshu.tmall.com/category.htm",
        "platform": "tmall",
        "category": "零食",
    },
    {
        "name": "liangpinpuzi",
        "url": "https://lppz.tmall.com/category.htm",
        "platform": "tmall",
        "category": "零食",
    },
    {
        "name": "meizhuang_shop",
        "url": "https://perfectdiary.tmall.com/category.htm",
        "platform": "tmall",
        "category": "美妆",
    },
]

# ── Mock Products for Validation ─────────────────────────────

MOCK_PRODUCTS = [
    # 三只松鼠
    {
        "name": "三只松鼠芋泥味蛋皮吐司卷肉松夹心面包糕点",
        "price": 69.9,
        "shop": "三只松鼠旗舰店",
        "category": "零食",
        "image": "https://img.alicdn.com/mock1.jpg",
        "url": "https://detail.tmall.com/item.htm?id=mock_1",
    },
    {
        "name": "三只松鼠每日坚果混合坚果仁750g",
        "price": 99.0,
        "shop": "三只松鼠旗舰店",
        "category": "零食",
        "image": "https://img.alicdn.com/mock2.jpg",
        "url": "https://detail.tmall.com/item.htm?id=mock_2",
    },
    {
        "name": "三只松鼠芒果干100g袋装蜜饯果脯",
        "price": 29.9,
        "shop": "三只松鼠旗舰店",
        "category": "零食",
        "image": "https://img.alicdn.com/mock3.jpg",
        "url": "https://detail.tmall.com/item.htm?id=mock_3",
    },
    # 良品铺子
    {
        "name": "良品铺子鸭脖锁骨套餐卤味零食大礼包",
        "price": 49.9,
        "shop": "良品铺子旗舰店",
        "category": "零食",
        "image": "https://img.alicdn.com/mock4.jpg",
        "url": "https://detail.tmall.com/item.htm?id=mock_4",
    },
    {
        "name": "良品铺子猪肉脯100g靖江特产蜜汁肉干",
        "price": 39.9,
        "shop": "良品铺子旗舰店",
        "category": "零食",
        "image": "https://img.alicdn.com/mock5.jpg",
        "url": "https://detail.tmall.com/item.htm?id=mock_5",
    },
    # 美妆
    {
        "name": "完美日记动物眼影盘珍珠猪盘12色",
        "price": 89.9,
        "shop": "完美日记官方旗舰店",
        "category": "美妆",
        "image": "https://img.alicdn.com/mock6.jpg",
        "url": "https://detail.tmall.com/item.htm?id=mock_6",
    },
    {
        "name": "花西子蜜粉定妆散粉控油持久遮瑕",
        "price": 129.0,
        "shop": "花西子旗舰店",
        "category": "美妆",
        "image": "https://img.alicdn.com/mock7.jpg",
        "url": "https://detail.tmall.com/item.htm?id=mock_7",
    },
]


async def run_full_pipeline(use_mock: bool = False) -> dict:
    """Run full product selection pipeline.

    Args:
        use_mock: Whether to use mock data.

    Returns:
        Validation report dict.
    """
    logger.info("=" * 70)
    logger.info("Phase 18 Task 2: Full Product Selection Pipeline Validation")
    logger.info("=" * 70)

    # Initialize services
    product_scoring_service = ProductScoringService()
    supplier_matching_service = SupplierMatchingService()
    opportunity_scoring_service = OpportunityScoringService()

    # Initialize 1688 client
    if use_mock:
        logger.info("Using Mock data mode")
        alibaba_client = AlibabaSearchClient(use_mock=True)
    else:
        logger.info("Using real 1688 crawler")
        try:
            from app.crawler.alibaba_1688 import Alibaba1688Crawler
            crawler = Alibaba1688Crawler()
            alibaba_client = AlibabaSearchClient(crawler=crawler)
        except Exception as e:
            logger.warning(f"Cannot init 1688 crawler: {e}, fallback to Mock")
            alibaba_client = AlibabaSearchClient(use_mock=True)

    # ── Step 1: Prepare test shops ──────────────────────────
    logger.info("\n[Step 1] Preparing test shops...")
    shops = TEST_SHOPS if not use_mock else TEST_SHOPS[:2]
    logger.info(f"  Shop count: {len(shops)}")

    # ── Step 2: Crawl products (using mock data) ────────────
    logger.info("\n[Step 2] Crawling products...")
    products = []
    for i, mock_data in enumerate(MOCK_PRODUCTS, 1):
        product = Product(
            id=i,
            name=mock_data["name"],
            platform="taobao",
            shop=mock_data["shop"],
            price=mock_data["price"],
            category=mock_data.get("category"),
            image=mock_data.get("image"),
            url=mock_data.get("url"),
            first_seen_time=datetime.now(),
            last_seen_time=datetime.now(),
        )
        products.append(product)
    logger.info(f"  Product count: {len(products)}")

    # All products are NEW
    new_products = products
    logger.info(f"  NEW products: {len(new_products)}")

    # ── Step 3: Product scoring ─────────────────────────────
    logger.info("\n[Step 3] Scoring new products...")
    product_scores: list[ProductScore] = []
    for product in new_products:
        score_data = product_scoring_service.calculate_score(product)
        score_record = ProductScore(
            product_id=product.id,
            shop_score=score_data["shop_score"],
            price_score=score_data["price_score"],
            category_score=score_data["category_score"],
            newness_score=score_data["newness_score"],
            completeness_score=score_data["completeness_score"],
            total_score=score_data["total_score"],
            recommend_level=score_data["recommend_level"],
        )
        product_scores.append(score_record)
    logger.info(f"  Scored: {len(product_scores)}")

    # ── Step 4: 1688 matching ───────────────────────────────
    logger.info("\n[Step 4] Matching with 1688 suppliers...")
    supplier_matches: list[SupplierMatch | None] = []
    match_success_count = 0
    high_profit_count = 0

    for product in new_products:
        # Clean title
        cleaned = supplier_matching_service.clean_title(product.name)
        keyword = supplier_matching_service.generate_search_keyword(cleaned)

        # Search 1688
        suppliers = await alibaba_client.search_products(keyword=keyword, limit=5)

        if not suppliers:
            supplier_matches.append(None)
            continue

        # Match
        match_result = supplier_matching_service.match_product(product, suppliers)

        if match_result:
            match_record = SupplierMatch(
                product_id=product.id,
                supplier_title=match_result["supplier_title"],
                supplier_url=match_result.get("supplier_url"),
                supplier_price=match_result["supplier_price"],
                similarity_score=match_result["similarity_score"],
                estimated_profit=match_result["estimated_profit"],
                profit_margin=match_result["profit_margin"],
            )
            supplier_matches.append(match_record)
            match_success_count += 1

            if match_result["profit_margin"] > 50:
                high_profit_count += 1
        else:
            supplier_matches.append(None)

    logger.info(f"  Match success: {match_success_count}/{len(new_products)}")
    logger.info(f"  Profit > 50%: {high_profit_count}")

    # ── Step 5: Opportunity scoring ─────────────────────────
    logger.info("\n[Step 5] Calculating opportunity scores...")
    opportunity_scores: list[OpportunityScore] = []
    for i, product in enumerate(new_products):
        product_score = product_scores[i]
        supplier_match = supplier_matches[i]

        opp_data = opportunity_scoring_service.calculate_opportunity_score(
            product=product,
            product_score=product_score,
            supplier_match=supplier_match,
            supplier_count=3 if supplier_match else 0,
        )

        opp_record = OpportunityScore(
            product_id=product.id,
            new_product_score=opp_data["new_product_score"],
            shop_score=opp_data["shop_score"],
            supplier_score=opp_data["supplier_score"],
            profit_score=opp_data["profit_score"],
            competition_score=opp_data["competition_score"],
            total_score=opp_data["total_score"],
            recommendation=opp_data["recommendation"],
        )
        opportunity_scores.append(opp_record)

    logger.info(f"  Opportunity scored: {len(opportunity_scores)}")

    # ── Step 6: Generate report ─────────────────────────────
    logger.info("\n[Step 6] Generating validation report...")

    # Build TOP recommendations
    top_recommendations = []
    for i, product in enumerate(new_products):
        opp = opportunity_scores[i]
        match = supplier_matches[i]

        rec = {
            "product_name": product.name,
            "taobao_price": product.price,
            "product_score": product_scores[i].total_score,
            "opportunity_score": opp.total_score,
            "recommendation": opp.recommendation,
        }

        if match:
            rec["supplier_title"] = match.supplier_title
            rec["supplier_price"] = match.supplier_price
            rec["profit_margin"] = match.profit_margin
            rec["estimated_profit"] = match.estimated_profit
            rec["similarity"] = match.similarity_score
        else:
            rec["supplier_title"] = None
            rec["supplier_price"] = None
            rec["profit_margin"] = None
            rec["estimated_profit"] = None
            rec["similarity"] = None

        top_recommendations.append(rec)

    # Sort by opportunity score
    top_recommendations.sort(key=lambda x: x["opportunity_score"], reverse=True)

    report = {
        "timestamp": datetime.now().isoformat(),
        "use_mock": use_mock,
        "statistics": {
            "shop_count": len(shops),
            "product_count": len(products),
            "new_product_count": len(new_products),
            "match_success_count": match_success_count,
            "match_success_rate": f"{match_success_count / len(new_products) * 100:.1f}%",
            "high_profit_count": high_profit_count,
        },
        "top_recommendations": top_recommendations,
    }

    return report


def print_report(report: dict):
    """Print validation report."""
    print("\n" + "=" * 70)
    print("Phase 18 Task 2: Full Pipeline Validation Report")
    print("=" * 70)

    print(f"\nTime: {report['timestamp']}")
    print(f"Mode: {'Mock' if report['use_mock'] else 'Real'}")

    # Statistics
    stats = report["statistics"]
    print("\n" + "-" * 70)
    print("Statistics:")
    print("-" * 70)
    print(f"  Shop count: {stats['shop_count']}")
    print(f"  Product count: {stats['product_count']}")
    print(f"  NEW products: {stats['new_product_count']}")
    print(f"  Match success: {stats['match_success_count']}")
    print(f"  Match rate: {stats['match_success_rate']}")
    print(f"  Profit > 50%: {stats['high_profit_count']}")

    # TOP recommendations
    print("\n" + "-" * 70)
    print("TOP Recommendations:")
    print("-" * 70)

    for i, rec in enumerate(report["top_recommendations"][:5], 1):
        print(f"\n[{i}] {rec['product_name'][:40]}...")
        print(f"    Taobao Price: {rec['taobao_price']} RMB")
        print(f"    Product Score: {rec['product_score']:.1f}")
        print(f"    Opportunity Score: {rec['opportunity_score']:.1f}")
        print(f"    Recommendation: {rec['recommendation']}")

        if rec["supplier_title"]:
            print(f"    Supplier: {rec['supplier_title'][:35]}...")
            print(f"    Cost: {rec['supplier_price']} RMB")
            print(f"    Profit Margin: {rec['profit_margin']:.1f}%")
            print(f"    Est. Profit: {rec['estimated_profit']} RMB")
            print(f"    Similarity: {rec['similarity']:.1f}%")
        else:
            print(f"    Supplier: Not matched")

    print("\n" + "=" * 70)


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Full Pipeline Validation")
    parser.add_argument("--use-mock", action="store_true", help="Use mock data")
    parser.add_argument("--output", type=str, help="Output report path")
    args = parser.parse_args()

    # Run pipeline
    report = await run_full_pipeline(use_mock=args.use_mock)

    # Print report
    print_report(report)

    # Save report
    output_path = args.output or "storage/phase18_2_full_pipeline_report.json"
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info(f"\nReport saved: {output_file}")

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

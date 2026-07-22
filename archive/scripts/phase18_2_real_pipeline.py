#!/usr/bin/env python3
"""Phase 18.2 Real: Full Pipeline with Real Crawling.

真实选品闭环验证（关闭Mock模式）：
1. 真实淘宝采集 → 三只松鼠天猫旗舰店
2. 筛选 NEW 商品（全部视为新品）
3. 新品评分 → ProductScoringService
4. 真实1688搜索 → Alibaba1688Crawler
5. 供应商匹配 → SupplierMatchingService
6. 机会评分 → OpportunityScoringService
7. 输出TOP5跟卖机会
8. 保存报告到storage

Usage:
    python scripts/phase18_2_real_pipeline.py
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger

from app.crawler.taobao import TaobaoCrawler
from app.crawler.alibaba_1688 import Alibaba1688Crawler
from app.crawler.alibaba import AlibabaSearchClient
from app.models.product import Product
from app.models.product_score import ProductScore
from app.models.supplier_match import SupplierMatch
from app.models.opportunity_score import OpportunityScore
from app.services.product_scoring import ProductScoringService
from app.services.supplier_matching import SupplierMatchingService
from app.services.opportunity_scoring import OpportunityScoringService
from app.services.login_helper import LoginHelper, TAOBAO_STATE_PATH, ALIBABA_STATE_PATH


# ── Test Shop Configuration ─────────────────────────────────

TEST_SHOP = {
    "name": "三只松鼠天猫旗舰店",
    "url": "https://sanzhisongshu.tmall.com/category.htm",
    "platform": "tmall",
    "category": "零食",
}

PRODUCT_LIMIT = 20  # 采集20个商品


def check_login_states() -> dict[str, Any]:
    """Check login states for taobao and 1688."""
    result = {
        "taobao": {
            "exists": TAOBAO_STATE_PATH.exists(),
            "path": str(TAOBAO_STATE_PATH.absolute()),
        },
        "alibaba": {
            "exists": ALIBABA_STATE_PATH.exists(),
            "path": str(ALIBABA_STATE_PATH.absolute()),
        },
    }
    return result


async def run_real_pipeline() -> dict:
    """Run full pipeline with real crawling.

    Returns:
        Validation report dict.
    """
    start_time = datetime.now()

    logger.info("=" * 70)
    logger.info("Phase 18.2 Real: Full Pipeline with Real Crawling")
    logger.info(f"Start time: {start_time.isoformat()}")
    logger.info("=" * 70)

    # ── Pre-check: Login states ──────────────────────────────
    logger.info("\n[Pre-check] Checking login states...")
    login_states = check_login_states()

    for platform, info in login_states.items():
        status = "OK" if info["exists"] else "MISSING"
        logger.info(f"  {platform}: {status} -> {info['path']}")

    if not login_states["taobao"]["exists"]:
        logger.error("淘宝登录态不存在！请先运行: uv run python login_taobao.py")
        return {"error": "taobao_login_missing"}

    if not login_states["alibaba"]["exists"]:
        logger.error("1688登录态不存在！请先运行: uv run python login_taobao.py")
        return {"error": "alibaba_login_missing"}

    # ── Initialize services ──────────────────────────────────
    logger.info("\n[Init] Initializing services...")
    product_scoring_service = ProductScoringService()
    supplier_matching_service = SupplierMatchingService()
    opportunity_scoring_service = OpportunityScoringService()

    # Initialize crawlers
    logger.info("  Initializing TaobaoCrawler...")
    taobao_crawler = TaobaoCrawler()

    logger.info("  Initializing Alibaba1688Crawler...")
    alibaba_crawler = Alibaba1688Crawler()

    alibaba_client = AlibabaSearchClient(crawler=alibaba_crawler)

    try:
        # ── Step 1: Crawl products from Taobao shop ──────────
        logger.info(f"\n[Step 1] Crawling products from {TEST_SHOP['name']}...")
        logger.info(f"  Shop URL: {TEST_SHOP['url']}")
        logger.info(f"  Product limit: {PRODUCT_LIMIT}")

        raw_products = await taobao_crawler.crawl_shop(
            shop_url=TEST_SHOP["url"],
            shop_name=TEST_SHOP["name"],
            max_pages=3,
            limit=PRODUCT_LIMIT,
        )

        logger.info(f"  Crawled {len(raw_products)} products")

        if not raw_products:
            logger.error("No products crawled! Check login state and shop URL.")
            return {"error": "no_products_crawled"}

        # Convert to Product models
        products = []
        for i, rp in enumerate(raw_products, 1):
            product = Product(
                id=i,
                name=rp.name,
                platform="taobao",
                shop=rp.shop or TEST_SHOP["name"],
                price=rp.price,
                category=TEST_SHOP["category"],
                image=rp.image,
                url=rp.url,
                first_seen_time=datetime.now(),
                last_seen_time=datetime.now(),
            )
            products.append(product)

        logger.info(f"  Products converted: {len(products)}")

        # All crawled products are NEW
        new_products = products
        logger.info(f"  NEW products: {len(new_products)}")

        # ── Step 2: Product scoring ──────────────────────────
        logger.info("\n[Step 2] Scoring new products...")
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

        # ── Step 3: 1688 supplier matching ───────────────────
        logger.info("\n[Step 3] Matching with 1688 suppliers (real search)...")
        supplier_matches: list[SupplierMatch | None] = []
        match_success_count = 0
        high_profit_count = 0

        for idx, product in enumerate(new_products):
            # Clean title and generate keyword
            cleaned = supplier_matching_service.clean_title(product.name)
            keyword = supplier_matching_service.generate_search_keyword(cleaned)

            logger.info(f"  [{idx + 1}/{len(new_products)}] Searching: {keyword[:30]}...")

            # Real 1688 search
            suppliers = await alibaba_client.search_products(keyword=keyword, limit=5)

            if not suppliers:
                logger.info(f"    No suppliers found")
                supplier_matches.append(None)
                continue

            logger.info(f"    Found {len(suppliers)} suppliers")

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

                logger.info(f"    Matched: {match_result['supplier_title'][:30]}... "
                          f"price={match_result['supplier_price']} "
                          f"margin={match_result['profit_margin']:.1f}%")
            else:
                supplier_matches.append(None)
                logger.info(f"    No match")

        logger.info(f"\n  Match success: {match_success_count}/{len(new_products)}")
        logger.info(f"  Profit > 50%: {high_profit_count}")

        # ── Step 4: Opportunity scoring ──────────────────────
        logger.info("\n[Step 4] Calculating opportunity scores...")
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

        # ── Step 5: Generate report ──────────────────────────
        logger.info("\n[Step 5] Generating validation report...")

        # Build TOP recommendations
        top_recommendations = []
        for i, product in enumerate(new_products):
            opp = opportunity_scores[i]
            match = supplier_matches[i]

            rec = {
                "rank": 0,  # Will be set after sorting
                "product_name": product.name,
                "taobao_price": product.price,
                "product_url": product.url,
                "product_score": product_scores[i].total_score,
                "opportunity_score": opp.total_score,
                "recommendation": opp.recommendation,
            }

            if match:
                rec["supplier_title"] = match.supplier_title
                rec["supplier_url"] = match.supplier_url
                rec["supplier_price"] = match.supplier_price
                rec["profit_margin"] = match.profit_margin
                rec["estimated_profit"] = match.estimated_profit
                rec["similarity"] = match.similarity_score
            else:
                rec["supplier_title"] = None
                rec["supplier_url"] = None
                rec["supplier_price"] = None
                rec["profit_margin"] = None
                rec["estimated_profit"] = None
                rec["similarity"] = None

            top_recommendations.append(rec)

        # Sort by opportunity score
        top_recommendations.sort(key=lambda x: x["opportunity_score"], reverse=True)
        for rank, rec in enumerate(top_recommendations, 1):
            rec["rank"] = rank

        end_time = datetime.now()

        report = {
            "timestamp": datetime.now().isoformat(),
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "mode": "real",
            "shop": {
                "name": TEST_SHOP["name"],
                "url": TEST_SHOP["url"],
                "category": TEST_SHOP["category"],
            },
            "login_states": login_states,
            "statistics": {
                "product_count": len(products),
                "new_product_count": len(new_products),
                "match_success_count": match_success_count,
                "match_success_rate": f"{match_success_count / len(new_products) * 100:.1f}%" if new_products else "0%",
                "high_profit_count": high_profit_count,
            },
            "top_recommendations": top_recommendations,
            "all_products": [
                {
                    "name": p.name,
                    "price": p.price,
                    "url": p.url,
                }
                for p in new_products
            ],
        }

        return report

    finally:
        # Cleanup
        logger.info("\n[Cleanup] Closing crawlers...")
        try:
            await taobao_crawler.close()
        except Exception:
            pass
        try:
            await alibaba_crawler.close()
        except Exception:
            pass


def print_report(report: dict):
    """Print validation report."""
    if "error" in report:
        print(f"\nERROR: {report['error']}")
        return

    print("\n" + "=" * 70)
    print("Phase 18.2 Real: Full Pipeline Validation Report")
    print("=" * 70)

    print(f"\nShop: {report['shop']['name']}")
    print(f"URL: {report['shop']['url']}")
    print(f"Duration: {report['duration_seconds']:.1f}s")
    print(f"Mode: {report['mode']}")

    # Login states
    print("\n" + "-" * 70)
    print("Login States:")
    print("-" * 70)
    for platform, info in report["login_states"].items():
        status = "OK" if info["exists"] else "MISSING"
        print(f"  {platform}: {status}")

    # Statistics
    stats = report["statistics"]
    print("\n" + "-" * 70)
    print("Statistics:")
    print("-" * 70)
    print(f"  Products crawled: {stats['product_count']}")
    print(f"  NEW products: {stats['new_product_count']}")
    print(f"  Match success: {stats['match_success_count']}")
    print(f"  Match rate: {stats['match_success_rate']}")
    print(f"  Profit > 50%: {stats['high_profit_count']}")

    # TOP 5 recommendations
    print("\n" + "-" * 70)
    print("TOP 5 跟卖机会:")
    print("-" * 70)

    for rec in report["top_recommendations"][:5]:
        print(f"\n[#{rec['rank']}] {rec['product_name'][:50]}")
        print(f"    淘宝价格: {rec['taobao_price']} RMB")
        print(f"    新品评分: {rec['product_score']:.1f}")
        print(f"    机会评分: {rec['opportunity_score']:.1f}")
        print(f"    推荐等级: {rec['recommendation']}")

        if rec["supplier_title"]:
            print(f"    供应商: {rec['supplier_title'][:40]}...")
            print(f"    成本价: {rec['supplier_price']} RMB")
            print(f"    利润率: {rec['profit_margin']:.1f}%")
            print(f"    预估利润: {rec['estimated_profit']} RMB")
            print(f"    相似度: {rec['similarity']:.1f}%")
        else:
            print(f"    供应商: 未匹配")

    print("\n" + "=" * 70)


async def main():
    """Main function."""
    # Run pipeline
    report = await run_real_pipeline()

    # Print report
    print_report(report)

    # Save report
    output_path = PROJECT_ROOT / "storage" / "phase18_2_real_pipeline_report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info(f"\nReport saved: {output_path}")

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

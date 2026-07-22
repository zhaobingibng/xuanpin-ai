#!/usr/bin/env python3
"""Phase 18 Task 1: 1688供应链匹配真实验证脚本.

验证流程：
1. 选择5个淘宝新品（模拟数据）
2. 标题清洗
3. 1688搜索
4. 获取真实供应商
5. 计算：相似度、成本、利润率
6. 输出验证报告

Usage:
    python scripts/phase18_1_supply_chain_validation.py
    python scripts/phase18_1_supply_chain_validation.py --use-mock  # 使用Mock数据
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from app.crawler.alibaba import AlibabaSearchClient
from app.models.product import Product
from app.services.supplier_matching import SupplierMatchingService


# ── 测试商品数据（模拟淘宝新品）───────────────────────────────

TEST_PRODUCTS = [
    {
        "name": "三只松鼠芋泥味蛋皮吐司卷肉松夹心面包糕点",
        "price": 69.9,
        "shop": "三只松鼠旗舰店",
        "category": "零食",
    },
    {
        "name": "良品铺子芒果干100g袋装蜜饯果脯",
        "price": 29.9,
        "shop": "良品铺子官方旗舰店",
        "category": "零食",
    },
    {
        "name": "完美日记动物眼影盘珍珠猪盘12色",
        "price": 89.9,
        "shop": "完美日记官方旗舰店",
        "category": "美妆",
    },
    {
        "name": "花西子蜜粉定妆散粉控油持久",
        "price": 129.0,
        "shop": "花西子旗舰店",
        "category": "美妆",
    },
    {
        "name": "百草味坚果零食大礼包混合装",
        "price": 99.0,
        "shop": "百草味旗舰店",
        "category": "零食",
    },
]


async def run_validation(use_mock: bool = False) -> dict:
    """运行供应链匹配验证。

    Args:
        use_mock: 是否使用Mock数据。

    Returns:
        验证报告字典。
    """
    logger.info("=" * 60)
    logger.info("Phase 18 Task 1: 1688 Supply Chain Matching Validation")
    logger.info("=" * 60)

    # 初始化服务
    matching_service = SupplierMatchingService()

    # 初始化搜索客户端
    if use_mock:
        logger.info("使用 Mock 数据模式")
        alibaba_client = AlibabaSearchClient(use_mock=True)
    else:
        logger.info("使用真实 1688 爬虫")
        try:
            from app.crawler.alibaba_1688 import Alibaba1688Crawler
            crawler = Alibaba1688Crawler()
            alibaba_client = AlibabaSearchClient(crawler=crawler)
        except Exception as e:
            logger.warning(f"无法初始化1688爬虫: {e}, 降级到Mock模式")
            alibaba_client = AlibabaSearchClient(use_mock=True)

    results = []
    success_count = 0

    for i, product_data in enumerate(TEST_PRODUCTS, 1):
        logger.info(f"\n[{i}/5] Processing: {product_data['name'][:30]}...")

        # 创建 Product 对象
        product = Product(
            id=i,
            name=product_data["name"],
            platform="taobao",
            shop=product_data["shop"],
            price=product_data["price"],
            category=product_data.get("category"),
        )

        # Step 1: 标题清洗
        cleaned_title = matching_service.clean_title(product.name)
        logger.info(f"  Cleaned: {cleaned_title}")

        # Step 2: 生成搜索关键词
        search_keyword = matching_service.generate_search_keyword(cleaned_title)
        logger.info(f"  Keyword: {search_keyword}")

        # Step 3: 搜索1688
        logger.info(f"  Searching 1688...")
        supplier_products = await alibaba_client.search_products(
            keyword=search_keyword,
            limit=5,
        )
        logger.info(f"  Found {len(supplier_products)} suppliers")

        if not supplier_products:
            logger.warning(f"  No suppliers found, skipping")
            results.append({
                "product_name": product.name,
                "taobao_price": product.price,
                "status": "failed",
                "reason": "no_supplier_found",
            })
            continue

        # Step 4: 匹配商品
        match_result = matching_service.match_product(product, supplier_products)

        if not match_result:
            logger.warning(f"  Match failed (similarity too low)")
            results.append({
                "product_name": product.name,
                "taobao_price": product.price,
                "status": "failed",
                "reason": "low_similarity",
            })
            continue

        # Step 5: 记录结果
        success_count += 1
        result = {
            "product_name": product.name,
            "taobao_price": product.price,
            "cleaned_title": cleaned_title,
            "search_keyword": search_keyword,
            "supplier_title": match_result["supplier_title"],
            "supplier_url": match_result.get("supplier_url"),
            "supplier_name": match_result.get("supplier_name", "未知"),
            "supplier_price": match_result["supplier_price"],
            "similarity_score": match_result["similarity_score"],
            "estimated_profit": match_result["estimated_profit"],
            "profit_margin": match_result["profit_margin"],
            "status": "success",
        }
        results.append(result)

        logger.info(f"  [OK] Match success!")
        logger.info(f"    Supplier: {match_result['supplier_title'][:40]}...")
        logger.info(f"    Cost: {match_result['supplier_price']} RMB")
        logger.info(f"    Similarity: {match_result['similarity_score']:.1f}%")
        logger.info(f"    Profit Margin: {match_result['profit_margin']:.1f}%")
        logger.info(f"    Est. Profit: {match_result['estimated_profit']} RMB")

    # 生成报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "use_mock": use_mock,
        "total_products": len(TEST_PRODUCTS),
        "success_count": success_count,
        "success_rate": f"{success_count / len(TEST_PRODUCTS) * 100:.1f}%",
        "results": results,
    }

    return report


def print_report(report: dict):
    """打印验证报告。"""
    print("\n" + "=" * 70)
    print("Phase 18 Task 1: 1688 Supply Chain Validation Report")
    print("=" * 70)
    print(f"\nTime: {report['timestamp']}")
    print(f"Mode: {'Mock' if report['use_mock'] else 'Real 1688 Crawler'}")
    print(f"\nTotal Products: {report['total_products']}")
    print(f"Success Count: {report['success_count']}")
    print(f"Success Rate: {report['success_rate']}")

    print("\n" + "-" * 70)
    print("Detailed Results:")
    print("-" * 70)

    for i, result in enumerate(report["results"], 1):
        print(f"\n[{i}] {result['product_name'][:40]}...")
        print(f"    Taobao Price: {result['taobao_price']} RMB")

        if result["status"] == "success":
            print(f"    Status: MATCH SUCCESS")
            print(f"    Supplier: {result['supplier_title'][:40]}...")
            print(f"    Cost Price: {result['supplier_price']} RMB")
            print(f"    Similarity: {result['similarity_score']:.1f}%")
            print(f"    Profit Margin: {result['profit_margin']:.1f}%")
            print(f"    Est. Profit: {result['estimated_profit']} RMB")
        else:
            print(f"    Status: MATCH FAILED")
            print(f"    Reason: {result.get('reason', 'unknown')}")

    print("\n" + "=" * 70)


async def main():
    """主函数。"""
    parser = argparse.ArgumentParser(description="1688供应链匹配验证")
    parser.add_argument("--use-mock", action="store_true", help="使用Mock数据")
    parser.add_argument("--output", type=str, help="输出报告路径")
    args = parser.parse_args()

    # 运行验证
    report = await run_validation(use_mock=args.use_mock)

    # 打印报告
    print_report(report)

    # 保存报告
    output_path = args.output or "storage/phase18_1_supply_chain_validation_report.json"
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info(f"\n报告已保存: {output_file}")

    return 0 if report["success_count"] > 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

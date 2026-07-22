"""Phase 16.8 Task 2: 淘宝真实店铺采集验证脚本

验证真实淘宝店铺商品采集能力，禁止 Mock fallback。

Usage:
    uv run python scripts/phase16_8_shop_validation.py --shop-url "https://shop123.taobao.com"
    uv run python scripts/phase16_8_shop_validation.py --shop-url "https://store.taobao.com/shop/view_shop.htm?appKey=xxx"
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def print_header(title: str):
    """Print formatted header."""
    width = 70
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


async def validate_shop_crawl(shop_url: str, max_pages: int = 2, limit: int = 30):
    """Validate real Taobao shop crawling.

    Args:
        shop_url: Real Taobao shop URL
        max_pages: Max pages to crawl
        limit: Max products to return

    Returns:
        dict with validation results
    """
    print_header("Phase 16.8: 淘宝真实店铺采集验证")
    print(f"  店铺 URL: {shop_url}")
    print(f"  最大页数: {max_pages}")
    print(f"  商品上限: {limit}")
    print(f"  禁止 Mock: True")
    print()

    result = {
        "shop_url": shop_url,
        "timestamp": datetime.now().isoformat(),
        "real_product_count": 0,
        "pages_crawled": 0,
        "elapsed_seconds": 0.0,
        "failure_reason": "",
        "is_logged_in": False,
        "products": [],
    }

    # ── Step 1: Initialize browser ──────────────────────────
    print("[1/5] 初始化浏览器...")

    try:
        from app.crawler.taobao import TaobaoCrawler
    except ImportError as e:
        result["failure_reason"] = f"import_error: {e}"
        print(f"  [ERROR] {e}")
        return result

    crawler = TaobaoCrawler()  # headless controlled by settings

    try:
        # ── Step 2: Check login ─────────────────────────────
        print("[2/5] 检查登录状态...")
        is_logged_in = await crawler.check_login()
        result["is_logged_in"] = is_logged_in

        if is_logged_in:
            print("  [OK] 已登录")
        else:
            print("  [WARN] 未登录，尝试继续（可能需要扫码）...")
            # Try to wait for manual login
            print("  等待 30 秒进行手动扫码登录...")
            await asyncio.sleep(30)
            is_logged_in = await crawler.check_login()
            result["is_logged_in"] = is_logged_in
            if not is_logged_in:
                result["failure_reason"] = "not_logged_in_after_wait"
                print("  [FAIL] 仍未登录，跳过采集")
                return result
            print("  [OK] 登录成功")

        # ── Step 3: Crawl shop with metrics ─────────────────
        print("[3/5] 开始采集店铺...")
        start_time = datetime.now()

        crawl_result = await crawler.crawl_shop_with_metrics(
            shop_url=shop_url,
            max_pages=max_pages,
            limit=limit,
        )

        elapsed = (datetime.now() - start_time).total_seconds()

        result["real_product_count"] = crawl_result.real_product_count
        result["pages_crawled"] = crawl_result.pages_crawled
        result["elapsed_seconds"] = elapsed
        result["failure_reason"] = crawl_result.failure_reason
        result["is_logged_in"] = crawl_result.is_logged_in

        # Collect product details
        for p in crawl_result.products[:20]:  # Limit to 20 for report
            result["products"].append({
                "name": p.name,
                "price": p.price,
                "shop": p.shop,
                "sales_24h": p.sales_24h,
                "url": p.url,
            })

        print(f"  [OK] 采集完成")
        print(f"       商品数: {crawl_result.real_product_count}")
        print(f"       页面数: {crawl_result.pages_crawled}")
        print(f"       耗时: {elapsed:.1f}s")
        if crawl_result.failure_reason:
            print(f"       原因: {crawl_result.failure_reason}")

        # ── Step 4: Analyze results ─────────────────────────
        print("[4/5] 分析采集结果...")

        if crawl_result.real_product_count > 0:
            print(f"  [OK] 成功采集 {crawl_result.real_product_count} 个商品")

            # Price range
            prices = [p.price for p in crawl_result.products if p.price > 0]
            if prices:
                print(f"       价格范围: {min(prices):.2f} - {max(prices):.2f}")
                print(f"       平均价格: {sum(prices)/len(prices):.2f}")

            # Shop distribution
            shops = {}
            for p in crawl_result.products:
                shops[p.shop] = shops.get(p.shop, 0) + 1
            if shops:
                print(f"       店铺数: {len(shops)}")
                top_shop = max(shops.items(), key=lambda x: x[1])
                print(f"       最多商品店铺: {top_shop[0]} ({top_shop[1]} 个)")

            # Show top 5 products
            print("\n  TOP 5 商品:")
            for i, p in enumerate(crawl_result.products[:5], 1):
                print(f"    {i}. {p.name[:40]}")
                print(f"       价格: {p.price:.2f} | 销量: {p.sales_24h} | 店铺: {p.shop}")
        else:
            reason = crawl_result.failure_reason or "unknown"
            print(f"  [WARN] 未采集到商品")
            print(f"         原因: {reason}")

            # Categorize failure
            if "not_logged_in" in reason:
                print("         建议: 重新登录淘宝")
            elif "timeout" in reason:
                print("         建议: 网络超时或页面加载慢")
            elif "no_products" in reason:
                print("         建议: 店铺可能无商品或URL不正确")
            elif "anti-bot" in reason or "sec.taobao" in reason:
                print("         建议: 触发风控，稍后重试")

        # ── Step 5: Save report ─────────────────────────────
        print("[5/5] 保存验证报告...")

        report_path = Path("storage/phase16_8_shop_validation_report.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)

        # Remove full products list from saved report (keep summary)
        save_result = {k: v for k, v in result.items() if k != "products"}
        save_result["top_products"] = result["products"][:10]

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(save_result, f, indent=2, ensure_ascii=False)

        print(f"  [OK] 报告已保存: {report_path}")

    except Exception as e:
        result["failure_reason"] = f"validation_error: {e}"
        print(f"\n[ERROR] 验证过程出错: {e}")

    finally:
        await crawler.close()

    return result


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Phase 16.8: 淘宝真实店铺采集验证")
    parser.add_argument(
        "--shop-url",
        type=str,
        required=True,
        help="淘宝店铺URL (e.g. https://shop123.taobao.com)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=2,
        help="最大采集页数 (default: 2)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="最大商品数 (default: 30)",
    )

    args = parser.parse_args()

    # Validate URL format
    shop_url = args.shop_url.strip()
    if not shop_url.startswith("http"):
        shop_url = "https://" + shop_url

    if "taobao.com" not in shop_url and "tmall.com" not in shop_url:
        print("[ERROR] 请提供有效的淘宝/天猫店铺URL")
        sys.exit(1)

    # Run validation
    result = asyncio.run(validate_shop_crawl(
        shop_url=shop_url,
        max_pages=args.max_pages,
        limit=args.limit,
    ))

    # Print summary
    print_header("验证结果汇总")
    print(f"  店铺 URL: {result['shop_url']}")
    print(f"  登录状态: {'已登录' if result['is_logged_in'] else '未登录'}")
    print(f"  真实商品: {result['real_product_count']}")
    print(f"  采集页面: {result['pages_crawled']}")
    print(f"  总耗时: {result['elapsed_seconds']:.1f}s")
    print(f"  失败原因: {result['failure_reason'] or '无'}")
    print()

    # Exit code based on success
    if result["real_product_count"] > 0:
        print("[SUCCESS] 店铺采集验证通过!")
        sys.exit(0)
    else:
        print("[WARN] 店铺采集未获取到商品，请检查原因")
        sys.exit(1)


if __name__ == "__main__":
    main()

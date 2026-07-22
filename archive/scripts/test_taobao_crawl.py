"""淘宝真实采集验证脚本。

功能：
1. 检查登录状态（复用 TaobaoCrawler.check_login）
2. 采集关键词 "海苔卷"
3. 限制最多 10 条商品
4. 输出：标题、价格、店铺、URL

用法:
    python scripts/test_taobao_crawl.py              # 采集 + 输出
    python scripts/test_taobao_crawl.py --keyword "蓝牙耳机"  # 自定义关键词
    python scripts/test_taobao_crawl.py --limit 5    # 限制 5 条
    python scripts/test_taobao_crawl.py --save-json  # 保存到 storage/ 目录

依赖:
    - 复用 app/crawler/taobao.py 的 TaobaoCrawler
    - 不修改 DailySelectionPipeline / ProductService / TaobaoCrawler
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# ── Windows GBK 兼容 ──────────────────────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Project root ────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="淘宝真实采集验证 — 使用 TaobaoCrawler 采集商品并输出关键字段",
    )
    parser.add_argument(
        "--keyword",
        default="海苔卷",
        help="搜索关键词 (默认: 海苔卷)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="最多采集商品数 (默认: 10)",
    )
    parser.add_argument(
        "--save-json",
        action="store_true",
        help="将结果保存到 storage/test_taobao_crawl_result.json",
    )
    return parser.parse_args(argv)


# ── Helpers ─────────────────────────────────────────────────────


def _print_header(text: str) -> None:
    """Print a section header."""
    print(f"\n{'─' * 60}")
    print(f"  {text}")
    print(f"{'─' * 60}")


def _print_product(idx: int, p, max_name_len: int = 40) -> None:
    """Print a single product row."""
    name = p.name[:max_name_len] + ("..." if len(p.name) > max_name_len else "")
    print(
        f"  {idx:>2}. {name:<{max_name_len + 3}}  "
        f"¥{p.price:>8.2f}  "
        f"{p.shop[:20]:<20}  "
        f"{p.url or '—'}"
    )


async def _check_and_warn_login(crawler) -> bool:
    """Check login state and print warning if not logged in."""
    logged_in = await crawler.check_login()
    if logged_in:
        print("  [OK] 登录状态: 已登录")
        return True
    else:
        print("  [!!] 登录状态: 未登录 — 可能无法采集到商品")
        print("  请先运行: python scripts/login_taobao.py")
        return False


# ── Main ────────────────────────────────────────────────────────


async def main() -> int:
    args = parse_args()
    keyword = args.keyword
    limit = args.limit

    print(f"\n  淘宝采集验证")
    print(f"  关键词: {keyword}")
    print(f"  限制: {limit} 条")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    from app.crawler.taobao import TaobaoCrawler

    crawler = TaobaoCrawler()
    start_time = datetime.now()

    try:
        # ── Step 1: Login check ─────────────────────────────────
        _print_header("Step 1: 登录检查")
        logged_in = await _check_and_warn_login(crawler)

        # ── Step 2: Crawl ───────────────────────────────────────
        _print_header(f"Step 2: 采集 '{keyword}'")
        products = await crawler.crawl(
            keyword=keyword,
            max_pages=1,
            limit=limit,
        )
        elapsed = (datetime.now() - start_time).total_seconds()

        # ── Step 3: Display results ─────────────────────────────
        _print_header(f"Step 3: 结果 ({len(products)} 条, 耗时 {elapsed:.1f}s)")

        if not products:
            print("\n  未采集到商品。可能原因：")
            print("    1. 未登录 — 请运行 python scripts/login_taobao.py")
            print("    2. 关键词无结果 — 请尝试其他关键词")
            print("    3. 淘宝风控拦截 — 请稍后再试")
            return 1 if not logged_in else 0

        print()
        for i, p in enumerate(products, 1):
            _print_product(i, p)

        # ── Summary ──────────────────────────────────────────────
        prices = [p.price for p in products if p.price > 0]
        shops = {p.shop for p in products if p.shop}
        urls = [p for p in products if p.url]

        print(f"\n  {'─' * 60}")
        print(f"  总计: {len(products)} 条商品")
        if prices:
            print(f"  价格区间: ¥{min(prices):.2f} ~ ¥{max(prices):.2f}")
        print(f"  店铺数: {len(shops)}")
        print(f"  含 URL: {len(urls)}/{len(products)}")
        if logged_in:
            print(f"  登录态: 已登录")
        print(f"  耗时: {elapsed:.1f}s")

        # ── Step 4: Optional JSON save ──────────────────────────
        if args.save_json:
            _print_header("Step 4: 保存 JSON")
            output_dir = PROJECT_ROOT / "storage"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / "test_taobao_crawl_result.json"

            result_data = {
                "keyword": keyword,
                "limit": limit,
                "total": len(products),
                "logged_in": logged_in,
                "elapsed_seconds": round(elapsed, 1),
                "timestamp": datetime.now().isoformat(),
                "products": [
                    {
                        "name": p.name,
                        "price": p.price,
                        "shop": p.shop,
                        "url": p.url,
                        "viewers": p.viewers,
                        "sales_24h": p.sales_24h,
                        "image": p.image,
                    }
                    for p in products
                ],
            }
            output_path.write_text(
                json.dumps(result_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"  已保存: {output_path}")

        return 0

    except Exception as e:
        print(f"\n  [ERROR] 采集失败: {e}")
        import traceback
        traceback.print_exc()
        return 2

    finally:
        await crawler.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

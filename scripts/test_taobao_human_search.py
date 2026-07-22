"""淘宝拟人搜索诊断脚本 — 模拟首页→输入→点击搜索流程。

功能：
1. 复用 TaobaoCrawler 打开浏览器上下文（cookies/storage_state）
2. 打开淘宝首页 → 随机等待 → 输入关键词 → 点击搜索
3. 对比直接 URL 导航，验证拟人操作是否更容易获得商品结果
4. 保存截图 / HTML / JSON 报告 到 storage/taobao_debug/

用法:
    python scripts/test_taobao_human_search.py
    python scripts/test_taobao_human_search.py --keyword "蓝牙耳机"
    python scripts/test_taobao_human_search.py --no-save
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Windows GBK 兼容 ──────────────────────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Project root ────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEBUG_DIR = PROJECT_ROOT / "storage" / "taobao_debug"

# ── Search input / button selectors (tried in order) ────────────
SEARCH_INPUT_SELECTORS = [
    "#q",
    "input[name='q']",
    ".search-combobox-input input",
    ".search-combobox-input",
    "#J_SearchForm input[type='text']",
    "#J_SearchForm input",
    "input[aria-label='搜索']",
    "input[placeholder*='搜索']",
    ".tb-header-search-input",
]

SEARCH_BUTTON_SELECTORS = [
    "button[type='submit']",
    ".btn-search",
    "#J_SearchBtn",
    ".search-button",
    "[aria-label='搜索']",
    "button:has-text('搜索')",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="淘宝拟人搜索诊断 — 首页→输入→点击 vs 直接URL",
    )
    parser.add_argument(
        "--keyword",
        default="海苔卷",
        help="搜索关键词 (默认: 海苔卷)",
    )
    parser.add_argument(
        "--wait-min",
        type=float,
        default=3.0,
        help="首页等待最短秒数 (默认: 3.0)",
    )
    parser.add_argument(
        "--wait-max",
        type=float,
        default=5.0,
        help="首页等待最长秒数 (默认: 5.0)",
    )
    parser.add_argument(
        "--result-wait",
        type=float,
        default=10.0,
        help="搜索后等待秒数 (默认: 10.0)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="不保存文件，仅输出诊断信息",
    )
    return parser.parse_args(argv)


# ── Helpers ────────────────────────────────────────────────────


def _print_section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


async def _try_find(page, selectors: list[str]) -> str | None:
    """Try each selector, return the first that matches."""
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                return sel
        except Exception:
            continue
    return None


async def _type_human(page, selector: str, text: str) -> None:
    """Type text with variable delays between keystrokes."""
    await page.click(selector)
    await page.fill(selector, "")  # clear
    for char in text:
        await page.type(selector, char, delay=random.randint(60, 180))
    await page.wait_for_timeout(random.randint(200, 600))


# ── Main ────────────────────────────────────────────────────────


async def main() -> int:
    args = parse_args()
    keyword = args.keyword
    wait_sec = random.uniform(args.wait_min, args.wait_max)

    print(f"\n  淘宝拟人搜索诊断")
    print(f"  关键词: {keyword}")
    print(f"  首页等待: {wait_sec:.1f}s")
    print(f"  结果等待: {args.result_wait:.1f}s")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    from app.crawler.taobao import TaobaoCrawler

    crawler = TaobaoCrawler()
    context = None
    page = None
    start = datetime.now()

    # ── Report data ─────────────────────────────────────────────
    report: dict = {
        "keyword": keyword,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "steps": [],
        "final_url": "",
        "page_title": "",
        "has_product_links": False,
        "has_item_taobao_com": False,
        "is_login_page": False,
        "is_captcha_page": False,
        "product_link_count": 0,
        "html_size": 0,
        "elapsed_seconds": 0,
    }

    try:
        # ── Step 1: Open browser context ────────────────────────
        _print_section("Step 1: 打开浏览器上下文")
        context = await crawler._new_context()
        await crawler.load_cookies(context)
        await crawler.load_storage_state(context)
        print("  [OK] 上下文已创建，cookies/storage_state 已加载")
        report["steps"].append({"step": 1, "action": "open_context", "success": True})

        # ── Step 2: Open Taobao homepage ────────────────────────
        _print_section("Step 2: 打开淘宝首页")
        page = await context.new_page()
        homepage = "https://www.taobao.com"
        try:
            await page.goto(homepage, wait_until="domcontentloaded", timeout=30000)
            print(f"  [OK] 首页已加载: {page.url[:100]}")
        except Exception as e:
            print(f"  [WARN] 首页加载超时，继续执行: {e}")
        report["steps"].append(
            {"step": 2, "action": "goto_homepage", "url": page.url[:120]}
        )

        # ── Step 3: Wait like a human ───────────────────────────
        _print_section(f"Step 3: 拟人等待 {wait_sec:.1f}s")
        await page.wait_for_timeout(int(wait_sec * 1000))
        print("  [OK] 等待完成")
        report["steps"].append(
            {"step": 3, "action": "human_wait", "seconds": round(wait_sec, 1)}
        )

        # ── Step 4: Find search input ──────────────────────────
        _print_section("Step 4: 查找搜索输入框")
        input_sel = await _try_find(page, SEARCH_INPUT_SELECTORS)
        if not input_sel:
            print("  [FAIL] 未找到搜索输入框，尝试的选择器:")
            for s in SEARCH_INPUT_SELECTORS:
                print(f"    - {s}")
            report["steps"].append(
                {"step": 4, "action": "find_input", "success": False}
            )
            return 1
        print(f"  [OK] 找到输入框: {input_sel}")
        report["steps"].append(
            {"step": 4, "action": "find_input", "selector": input_sel, "success": True}
        )

        # ── Step 5: Type keyword ────────────────────────────────
        _print_section(f'Step 5: 输入关键词 "{keyword}"')
        await _type_human(page, input_sel, keyword)
        await page.wait_for_timeout(random.randint(500, 1200))
        print(f"  [OK] 已输入: {keyword}")
        report["steps"].append({"step": 5, "action": "type_keyword", "keyword": keyword})

        # ── Step 6: Click search button ─────────────────────────
        _print_section("Step 6: 点击搜索")
        btn_sel = await _try_find(page, SEARCH_BUTTON_SELECTORS)
        if not btn_sel:
            # Fallback: press Enter
            print("  [WARN] 未找到搜索按钮，使用 Enter 键提交")
            await page.press(input_sel, "Enter")
            report["steps"].append(
                {"step": 6, "action": "click_search", "fallback": "Enter key"}
            )
        else:
            print(f"  [OK] 找到搜索按钮: {btn_sel}")
            await page.click(btn_sel)
            report["steps"].append(
                {"step": 6, "action": "click_search", "selector": btn_sel}
            )

        # ── Step 7: Wait for results ────────────────────────────
        _print_section(f"Step 7: 等待结果加载 ({args.result_wait:.0f}s)")
        await page.wait_for_timeout(int(args.result_wait * 1000))

        # Additional wait for network to settle
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
            print("  [OK] networkidle")
        except Exception:
            print("  [INFO] networkidle 未达成（可能有持续请求）")

        report["steps"].append(
            {"step": 7, "action": "wait_results", "seconds": args.result_wait}
        )

        # ── Step 8: Extract diagnostics ─────────────────────────
        _print_section("Step 8: 诊断结果")

        final_url = page.url
        title = await page.title()
        html = await page.content()
        html_size = len(html)

        # Product links
        product_patterns = [
            r'href="//item\.taobao\.com',
            r'href="//detail\.tmall\.com',
            r'href="https?://item\.taobao\.com',
            r'href="https?://detail\.tmall\.com',
        ]
        product_links: list[str] = []
        for pat in product_patterns:
            product_links.extend(re.findall(pat, html, re.IGNORECASE))
        # Also try to find actual URLs
        url_matches = re.findall(
            r'(?:href|data-href)="(//(?:item|detail)\.(?:taobao|tmall)\.com[^"]*)"',
            html,
            re.IGNORECASE,
        )
        product_links.extend(url_matches)

        # Page type indicators
        is_login = bool(
            re.search(r'login\.taobao\.com', html, re.I)
            or re.search(r'亲，请登录', html)
            or html.count("site-nav-login") > 10
        )
        is_captcha = bool(
            re.search(r'sec\.taobao\.com|验证码|滑块验证|baxia|punish', html, re.I)
        )
        has_items = bool(re.search(r'J_ItemList|m-itemlist|item-card', html, re.I))

        print(f"  最终URL: {final_url[:150]}")
        print(f"  页面标题: {title}")
        print(f"  HTML 大小: {html_size:,} 字符")
        print(f"  商品链接数: {len(product_links)}")
        print(f"  是否有 item.taobao.com: {'是' if any('item.taobao.com' in l for l in product_links) else '否'}")
        print(f"  是否有商品列表: {'是' if has_items else '否'}")
        print(f"  是否登录页面: {'是' if is_login else '否'}")
        print(f"  是否验证码页: {'是' if is_captcha else '否'}")

        # Show a few product links if found
        if product_links:
            print(f"\n  示例商品链接:")
            for link in product_links[:5]:
                print(f"    {link[:120]}")

        report.update({
            "final_url": final_url,
            "page_title": title,
            "has_product_links": len(product_links) > 0,
            "has_item_taobao_com": any("item.taobao.com" in l for l in product_links),
            "is_login_page": is_login,
            "is_captcha_page": is_captcha,
            "product_link_count": len(product_links),
            "html_size": html_size,
            "elapsed_seconds": round((datetime.now() - start).total_seconds(), 1),
        })

        # ── Step 9: Save files ──────────────────────────────────
        _print_section("Step 9: 保存文件")

        if not args.no_save:
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)

            # Screenshot
            ss_path = DEBUG_DIR / "human_search.png"
            await page.screenshot(path=str(ss_path), full_page=False)
            print(f"  [OK] 截图: {ss_path.name}")

            # HTML
            html_path = DEBUG_DIR / "human_search.html"
            html_path.write_text(html, encoding="utf-8")
            print(f"  [OK] HTML: {html_path.name} ({html_path.stat().st_size:,} bytes)")

            # JSON report
            report_path = DEBUG_DIR / "human_search_report.json"
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"  [OK] 报告: {report_path.name}")
        else:
            print("  [SKIP] --no-save 模式")

        # ── Summary ─────────────────────────────────────────────
        elapsed = (datetime.now() - start).total_seconds()
        _print_section("总结")
        print(f"  关键词: {keyword}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  商品链接: {len(product_links)} 个")
        print(f"  J_ItemList: {'找到' if has_items else '未找到'}")
        print(f"  登录页: {'是 [!!]' if is_login else '否'}")
        print(f"  验证码: {'是 [!!]' if is_captcha else '否'}")

        if not args.no_save:
            print(f"  保存目录: {DEBUG_DIR}")

        return 0

    except Exception as e:
        print(f"\n  [ERROR] 诊断失败: {e}")
        import traceback
        traceback.print_exc()
        report["error"] = str(e)
        return 1

    finally:
        if page:
            await page.close()
        if context:
            await context.close()
        await crawler.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

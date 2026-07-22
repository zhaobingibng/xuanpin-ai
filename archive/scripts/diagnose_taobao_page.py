"""淘宝搜索页 DOM 结构诊断脚本。

功能：
1. 复用 TaobaoCrawler 打开浏览器上下文
2. 导航到搜索页 https://s.taobao.com/search?q=海苔卷
3. 保存 html / 截图 到 storage/taobao_debug/
4. 输出：页面标题、HTML 大小、商品相关关键词计数

用法:
    python scripts/diagnose_taobao_page.py
    python scripts/diagnose_taobao_page.py --keyword "蓝牙耳机"
    python scripts/diagnose_taobao_page.py --timeout 15
"""

from __future__ import annotations

import argparse
import asyncio
import re
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
DEBUG_DIR = PROJECT_ROOT / "storage" / "taobao_debug"

SEARCH_URL = "https://s.taobao.com/search"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="淘宝搜索页 DOM 诊断 — 检查真实页面结构",
    )
    parser.add_argument(
        "--keyword",
        default="海苔卷",
        help="搜索关键词 (默认: 海苔卷)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="页面加载等待秒数 (默认: 10)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="不保存文件，仅输出诊断信息",
    )
    return parser.parse_args(argv)


# ── Keyword counters ────────────────────────────────────────────


KEYWORD_PATTERNS = {
    # DOM structure hints
    "data-item": r'data-item',
    "data-item-id": r'data-item-id',
    "data-nid": r'data-nid',
    "data-spm": r'data-spm',
    # Common Taobao CSS classes
    "J_ItemList": r'J_ItemList',
    "m-itemlist": r'm-itemlist',
    "item J_MouserOnverReq": r'item\s+J_MouserOnverReq',
    "grid-item": r'grid-item',
    "ctx-box": r'ctx-box',
    # Product card classes
    "item-card": r'item-card',
    "card-item": r'card-item',
    # Links
    'href="//item.taobao.com': r'href="//item\.taobao\.com',
    'href="//detail.tmall.com': r'href="//detail\.tmall\.com',
    # Text
    "月销": r'月销',
    "人付款": r'人付款',
    # Login state
    "亲，请登录": r'亲，请登录',
    "site-nav-login": r'site-nav-login',
    # Anti-bot / captcha
    "sec.taobao.com": r'sec\.taobao\.com',
    "punish": r'punish',
    "验证码": r'验证码',
    "滑块验证": r'滑块验证',
    # Price patterns
    '¥\\d': r'¥\d',
    'price': r'price',
}


def _count_keywords(html: str) -> dict[str, int]:
    """统计 HTML 中各关键词的出现次数。"""
    counts: dict[str, int] = {}
    for label, pattern in KEYWORD_PATTERNS.items():
        counts[label] = len(re.findall(pattern, html, re.IGNORECASE))
    return counts


def _print_section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ── Main ────────────────────────────────────────────────────────


async def main() -> int:
    args = parse_args()
    keyword = args.keyword
    timeout = args.timeout * 1000
    url = f"{SEARCH_URL}?q={keyword}"

    print(f"\n  淘宝搜索页 DOM 诊断")
    print(f"  URL: {url}")
    print(f"  超时: {args.timeout}s")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    from app.crawler.taobao import TaobaoCrawler

    crawler = TaobaoCrawler()
    context = None
    page = None
    start = datetime.now()

    try:
        # ── Step 1: Open browser context ────────────────────────
        _print_section("Step 1: 打开浏览器上下文")
        context = await crawler._new_context()
        await crawler.load_cookies(context)
        await crawler.load_storage_state(context)
        print("  [OK] 上下文已创建，cookies/storage_state 已加载")

        # ── Step 2: Navigate ────────────────────────────────────
        _print_section(f"Step 2: 导航到搜索页")
        page = await context.new_page()
        print(f"  导航中... {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        print("  [OK] domcontentloaded")

        # Wait extra for JS rendering
        wait_ms = max(timeout, 5000)
        print(f"  等待 JS 渲染 {wait_ms // 1000}s...")
        await page.wait_for_timeout(wait_ms)

        # ── Step 3: Extract diagnostics ─────────────────────────
        _print_section("Step 3: 诊断信息")

        # 3a. Page title
        title = await page.title()
        print(f"  页面标题: {title}")

        # 3b. Current URL (may get redirected)
        current_url = page.url
        print(f"  当前 URL: {current_url}")
        if current_url != url:
            print(f"  [!!] URL 已跳转 (可能被风控或重定向)")

        # 3c. HTML content
        html = await page.content()
        html_size = len(html)
        print(f"  HTML 大小: {html_size:,} 字符")

        # 3d. Keyword counts
        _print_section("Step 4: 关键词计数")
        counts = _count_keywords(html)

        # Group and print
        print("\n  ── DOM 结构 ──")
        for k in ["data-item", "data-item-id", "data-nid", "data-spm"]:
            print(f"    {k:<25} {counts.get(k, 0)}")

        print("\n  ── CSS 类名 ──")
        for k in ["J_ItemList", "m-itemlist", "item J_MouserOnverReq",
                   "grid-item", "ctx-box", "item-card", "card-item"]:
            print(f"    {k:<25} {counts.get(k, 0)}")

        print("\n  ── 商品链接 ──")
        for k in ['href="//item.taobao.com', 'href="//detail.tmall.com']:
            print(f"    {k:<30} {counts.get(k, 0)}")

        print("\n  ── 交易信息 ──")
        for k in ["月销", "人付款", '¥\\d', "price"]:
            print(f"    {k:<25} {counts.get(k, 0)}")

        print("\n  ── 登录/风控 ──")
        for k in ["亲，请登录", "site-nav-login", "sec.taobao.com",
                   "punish", "验证码", "滑块验证"]:
            print(f"    {k:<25} {counts.get(k, 0)}")

        # 3e. Screenshot
        _print_section("Step 5: 截图")
        if not args.no_save:
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            screenshot_path = DEBUG_DIR / f"taobao_search_{keyword}.png"
            await page.screenshot(path=str(screenshot_path), full_page=False)
            print(f"  [OK] 截图已保存: {screenshot_path}")

        # ── Step 6: Save HTML ───────────────────────────────────
        _print_section("Step 6: 保存 HTML")
        if not args.no_save:
            html_path = DEBUG_DIR / f"taobao_search_{keyword}.html"
            html_path.write_text(html, encoding="utf-8")
            print(f"  [OK] HTML 已保存: {html_path}")
            print(f"       大小: {html_path.stat().st_size:,} bytes")

        # ── Summary ─────────────────────────────────────────────
        elapsed = (datetime.now() - start).total_seconds()
        product_hints = counts.get('href="//item.taobao.com', 0) + counts.get('href="//detail.tmall.com', 0)
        is_blocked = bool(
            counts.get("sec.taobao.com", 0)
            or counts.get("punish", 0)
            or counts.get("验证码", 0)
        )

        _print_section("总结")
        print(f"  关键词: {keyword}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  HTML 大小: {html_size:,} 字符")
        print(f"  疑似商品链接: {product_hints} 个")
        print(f"  J_ItemList 容器: {'找到' if counts.get('J_ItemList', 0) > 0 else '未找到'}")
        print(f"  风控拦截: {'是 [!!]' if is_blocked else '否'}")
        if not args.no_save:
            print(f"  保存目录: {DEBUG_DIR}")

        return 0

    except Exception as e:
        print(f"\n  [ERROR] 诊断失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        if page:
            await page.close()
        if context:
            await context.close()
        await crawler.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

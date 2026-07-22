"""Xiaohongshu crawl smoke test — full diagnostic, no production code changes.

Captures every verification step to a JSON report + log file.
"""

import asyncio
import json
import sys
import time
import traceback
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loguru import logger

REPORT_FILE = Path(__file__).resolve().parent / "storage" / "smoke_test_report.json"
LOG_FILE    = Path(__file__).resolve().parent / "storage" / "smoke_test.log"

KEYWORD = "水杯"
LIMIT   = 5


def setup_logging():
    """Route all loguru output to a UTF-8 log file."""
    logger.remove()
    logger.add(
        str(LOG_FILE),
        rotation=None,
        encoding="utf-8",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {name}:{function}:{line} | {message}",
    )
    # Also mirror to stderr for live viewing
    logger.add(
        sys.stderr,
        level="DEBUG",
        format="{time:HH:mm:ss} | {level:<7} | {message}",
    )


async def step(name: str, fn, report: dict):
    """Run a verification step, capture result."""
    logger.info("=== STEP: {} ===", name)
    entry = {"step": name, "status": "UNKNOWN", "detail": "", "duration_s": 0}
    t0 = time.time()
    try:
        result = await fn()
        entry["status"] = "PASS"
        entry["detail"] = str(result) if result is not None else "ok"
    except Exception as e:
        entry["status"] = "FAIL"
        entry["detail"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        logger.error("STEP FAILED: {}", e)
    entry["duration_s"] = round(time.time() - t0, 2)
    report["steps"].append(entry)
    return entry["status"] == "PASS"


async def main():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    setup_logging()

    report = {
        "test": "xiaohongshu_smoke_test",
        "keyword": KEYWORD,
        "limit": LIMIT,
        "timestamp": datetime.now().isoformat(),
        "steps": [],
        "summary": {},
    }

    from app.crawler.xiaohongshu import XiaohongshuCrawler
    from app.crawler.browser import _ContextProxy

    crawler = XiaohongshuCrawler()
    bm = crawler._browser_manager

    report["config"] = {
        "persistent": bm._persistent,
        "headless": bm._settings.browser_headless,
        "user_data_dir": bm._user_data_dir,
    }

    # ── Step 1: check_login ──
    async def s1_check_login():
        result = await crawler.check_login()
        logger.info("check_login() => {}", result)
        if not result:
            raise RuntimeError("check_login returned False — not logged in")
        return f"logged_in={result}"

    ok = await step("1. check_login()", s1_check_login, report)

    # After check_login the crawler's browser is closed; recreate for fresh state
    crawler2 = XiaohongshuCrawler()
    bm2 = crawler2._browser_manager

    # ── Step 2: start browser + open homepage ──
    async def s2_start_and_homepage():
        await bm2.start()
        ctx = await bm2.new_context("xiaohongshu")
        is_proxy = isinstance(ctx, _ContextProxy)
        page = await ctx.new_page()
        await page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        title = await page.title()
        url = page.url
        await ctx.close()  # closes pages via _ContextProxy
        return f"proxy={is_proxy}, title={title}, url={url}"

    if ok:
        ok = await step("2. start_browser + homepage", s2_start_and_homepage, report)

    # ── Step 3: full crawl ──
    products = []

    async def s3_crawl():
        nonlocal products
        products = await crawler2.crawl(
            keyword=KEYWORD, max_pages=2, limit=LIMIT, crawl_sort="general",
        )
        return f"collected={len(products)}"

    if ok:
        ok = await step("3. crawl(keyword, limit=5)", s3_crawl, report)

    # ── Step 4: inspect cards ──
    async def s4_inspect_cards():
        if not products:
            raise RuntimeError("No products collected — cannot inspect")

        fields_ok = 0
        details = []
        for i, p in enumerate(products):
            d = asdict(p)
            checks = {
                "name":    bool(d.get("name")),
                "image":   bool(d.get("image")),
                "url":     bool(d.get("url")),
                "viewers": d.get("viewers", 0) > 0,
                "shop":    bool(d.get("shop")) and d["shop"] != "未知店铺",
            }
            score = sum(checks.values())
            details.append({"index": i + 1, "name": d["name"][:60], "checks": checks, "score": f"{score}/5"})
            if score >= 3:
                fields_ok += 1

        report["products"] = details
        return f"products_with_3+_fields={fields_ok}/{len(products)}"

    if ok:
        ok = await step("4. parse_product field coverage", s4_inspect_cards, report)

    # ── Step 5: 300012 / anti-bot check ──
    async def s5_antibot():
        log_text = LOG_FILE.read_text(encoding="utf-8")
        has_300012 = "300012" in log_text
        has_ip_risk = "IP" in log_text and "风险" in log_text
        has_blocked = "blocked" in log_text.lower() or "forbidden" in log_text.lower()
        issues = []
        if has_300012:
            issues.append("300012 detected")
        if has_ip_risk:
            issues.append("IP risk detected")
        if has_blocked:
            issues.append("blocked/forbidden detected")
        if issues:
            raise RuntimeError(", ".join(issues))
        return "no anti-bot signals in logs"

    await step("5. anti-bot / 300012 check", s5_antibot, report)

    # ── Cleanup ──
    try:
        await bm2.close()
    except Exception:
        pass
    try:
        await bm.close()
    except Exception:
        pass

    # ── Summary ──
    passed = sum(1 for s in report["steps"] if s["status"] == "PASS")
    failed = sum(1 for s in report["steps"] if s["status"] == "FAIL")
    report["summary"] = {
        "total": len(report["steps"]),
        "passed": passed,
        "failed": failed,
        "verdict": "PASS" if failed == 0 else "FAIL",
    }

    # ── Save report ──
    REPORT_FILE.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("Report saved: {}", REPORT_FILE)


if __name__ == "__main__":
    asyncio.run(main())

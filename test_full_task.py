"""Full Xiaohongshu task verification — 5 keywords, cooldown + breaker active."""

import asyncio
import json
import time
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loguru import logger

REPORT = Path(__file__).resolve().parent / "storage" / "full_task_report.json"
LOG    = Path(__file__).resolve().parent / "storage" / "full_task.log"

KEYWORDS = ["蓝牙耳机", "手机壳", "防晒霜", "水杯", "收纳盒"]


async def main():
    # ── Logging setup ──
    LOG.parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(str(LOG), rotation=None, encoding="utf-8", level="DEBUG",
               format="{time:HH:mm:ss.SSS} | {level:<7} | {message}")
    logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")

    # ── Monkey-patch safe_goto to count page navigations ──
    from app.crawler.browser import BrowserManager
    _nav_count = {"total": 0, "per_keyword": {}}
    _current_keyword = {"kw": ""}
    _original_safe_goto = BrowserManager.safe_goto

    async def _counted_safe_goto(self, page, url, **kwargs):
        _nav_count["total"] += 1
        kw = _current_keyword["kw"]
        if kw:
            _nav_count["per_keyword"].setdefault(kw, 0)
            _nav_count["per_keyword"][kw] += 1
        return await _original_safe_goto(self, page, url, **kwargs)

    BrowserManager.safe_goto = _counted_safe_goto

    # ── Monkey-patch crawl to track per-keyword timing ──
    from app.crawler.base import BaseCrawler
    _original_crawl = BaseCrawler.crawl
    _keyword_results = []

    async def _tracked_crawl(self, keyword, **kwargs):
        _current_keyword["kw"] = keyword
        t0 = time.time()
        products = await _original_crawl(self, keyword=keyword, **kwargs)
        elapsed = time.time() - t0
        navs = _nav_count["per_keyword"].get(keyword, 0)
        _keyword_results.append({
            "keyword": keyword,
            "platform": self.PLATFORM,
            "products": len(products),
            "page_navigations": navs,
            "duration_s": round(elapsed, 1),
        })
        return products

    BaseCrawler.crawl = _tracked_crawl

    # ── Run crawl ──
    from app.tasks.crawler_jobs import crawl_all_platforms

    print("=" * 60)
    print("  Xiaohongshu Full Task Verification")
    print(f"  Keywords: {KEYWORDS}")
    print(f"  Cooldown: active (60-180s)")
    print(f"  Breaker:  active (300012)")
    print("=" * 60)
    print()

    t_start = time.time()
    try:
        all_products = await crawl_all_platforms(
            keywords=KEYWORDS,
            platforms=["xiaohongshu"],
            max_pages=2,
        )
    except Exception as e:
        print(f"FATAL: {e}")
        all_products = []
    t_total = time.time() - t_start

    # ── Check if breaker fired ──
    log_text = LOG.read_text(encoding="utf-8")
    breaker_fired = "[circuit-breaker] xiaohongshu 300012 detected" in log_text
    skipped_count = log_text.count("[circuit-breaker] skipping")

    # ── Restore monkey-patches ──
    BrowserManager.safe_goto = _original_safe_goto
    BaseCrawler.crawl = _original_crawl

    # ── Build report ──
    report = {
        "keywords": KEYWORDS,
        "total_duration_s": round(t_total, 1),
        "total_products": len(all_products),
        "total_page_navigations": _nav_count["total"],
        "breaker_fired": breaker_fired,
        "keywords_skipped_by_breaker": skipped_count,
        "per_keyword": _keyword_results,
    }

    # ── Print results ──
    print()
    print("=" * 60)
    print("  RESULTS")
    print("=" * 60)
    print()
    print(f"  {'#':<3} {'Keyword':<12} {'Products':>8} {'Navs':>5} {'Time':>7}")
    print(f"  {'─'*3} {'─'*12} {'─'*8} {'─'*5} {'─'*7}")

    for i, kr in enumerate(_keyword_results, 1):
        print(f"  {i:<3} {kr['keyword']:<12} {kr['products']:>8} {kr['page_navigations']:>5} {kr['duration_s']:>6.1f}s")

    skipped_keywords = set(KEYWORDS) - {kr["keyword"] for kr in _keyword_results}
    for kw in skipped_keywords:
        print(f"  {'—':<3} {kw:<12} {'SKIP':>8} {'—':>5} {'—':>7}")

    print()
    print(f"  Total products:        {len(all_products)}")
    print(f"  Total page navigations: {_nav_count['total']}")
    print(f"  Breaker fired:         {'YES' if breaker_fired else 'NO'}")
    print(f"  Keywords skipped:      {skipped_count}")
    print(f"  Total duration:        {t_total:.1f}s ({t_total/60:.1f} min)")
    print("=" * 60)

    # ── Save ──
    report["products_sample"] = [asdict(p) for p in all_products[:3]]
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\nReport saved: {REPORT}")


if __name__ == "__main__":
    asyncio.run(main())

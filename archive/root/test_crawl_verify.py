"""Real crawl verification test — XiaohongshuCrawler with persistent profile.

Outputs:
- Request process (URLs, page loads, card counts)
- Crawl count
- Parsed product examples
- Exception / anti-bot logs
"""

import asyncio
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loguru import logger
from app.crawler.xiaohongshu import XiaohongshuCrawler

KEYWORD = "防晒霜"
LIMIT = 5


async def main():
    crawler = XiaohongshuCrawler()
    bm = crawler._browser_manager

    print("=" * 60)
    print(f"  XiaohongshuCrawler Real Crawl Test")
    print(f"  keyword:  {KEYWORD}")
    print(f"  limit:    {LIMIT}")
    print(f"  persistent: {bm._persistent}")
    print(f"  headless:   {bm._settings.browser_headless}")
    print(f"  profile:    {bm._user_data_dir}")
    print("=" * 60)
    print()

    # Run crawl (check_login is called internally by _do_crawl)
    print(f"[1/3] Crawling keyword='{KEYWORD}' (limit={LIMIT})...")
    print("-" * 60)

    start_time = time.time()
    try:
        products = await crawler.crawl(
            keyword=KEYWORD,
            max_pages=2,
            limit=LIMIT,
            crawl_sort="general",
        )
    except Exception as e:
        print(f"  CRAWL EXCEPTION: {type(e).__name__}: {e}")
        products = []
    elapsed = time.time() - start_time

    print("-" * 60)
    print()

    # Results summary
    print(f"[2/3] Crawl Results:")
    print(f"  Products collected: {len(products)}")
    print(f"  Elapsed time:      {elapsed:.1f}s")
    print()

    if products:
        print(f"[3/3] Parsed Product Examples:")
        print()
        for i, p in enumerate(products[:5], 1):
            d = asdict(p)
            print(f"  --- Product #{i} ---")
            print(f"    name:         {d.get('name', 'N/A')}")
            print(f"    price:        {d.get('price', 'N/A')}")
            print(f"    shop:         {d.get('shop', 'N/A')}")
            print(f"    image:        {(d.get('image') or 'None')[:80]}")
            print(f"    viewers:      {d.get('viewers', 0)}")
            print(f"    sales_24h:    {d.get('sales_24h', 0)}")
            print(f"    favorites:    {d.get('favorites', 0)}")
            print(f"    comments:     {d.get('comments', 0)}")
            print(f"    publish_time: {d.get('publish_time', 'N/A')}")
            print(f"    url:          {(d.get('url') or 'None')[:80]}")
            print()
    else:
        print("[3/3] No products parsed. Possible causes:")
        print("  - Search page blocked by anti-bot (300012)")
        print("  - No note-item/goods-card elements found")
        print("  - All cards failed to parse")

    print("=" * 60)

    # Save raw results to JSON for inspection
    out_dir = Path(__file__).resolve().parent / "storage"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "crawl_test_result.json"
    if products:
        data = [asdict(p) for p in products]
        out_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"Raw results saved: {out_file}")

    await crawler.close()


if __name__ == "__main__":
    asyncio.run(main())

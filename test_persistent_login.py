"""Test persistent context login detection.

Opens a VISIBLE Chromium browser with persistent profile.
User logs in manually, script detects login status.
Does NOT read cookies/xiaohongshu.json.
"""

import asyncio
import os
import sys
from pathlib import Path

# Force headless=False via env before importing settings
os.environ["BROWSER_HEADLESS"] = "false"

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loguru import logger
from app.crawler.xiaohongshu import XiaohongshuCrawler


async def main():
    crawler = XiaohongshuCrawler()
    bm = crawler._browser_manager

    print(f"Persistent mode: {bm._persistent}")
    print(f"Headless:        {bm._settings.browser_headless}")
    print(f"User data dir:   {bm._user_data_dir}")
    print()

    try:
        # 1. Start BrowserManager (persistent, visible)
        await bm.start()
        logger.info("BrowserManager started")

        # 2. Open Xiaohongshu homepage
        ctx = await bm.new_context("xiaohongshu")
        page = await ctx.new_page()
        await page.goto(
            "https://www.xiaohongshu.com",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        logger.info("Homepage loaded")

        # 3. Wait for user to log in
        print("=" * 55)
        print("  Browser opened. Please log in to Xiaohongshu.")
        print("  Polling every 3s (max 120s)...")
        print("=" * 55)
        print()

        logged_in = False
        for elapsed in range(1, 121):
            await asyncio.sleep(1)
            if elapsed % 3 == 0:
                user_el = await page.query_selector(
                    "[class*='user'], [class*='avatar'], [class*='sidebar']"
                )
                if user_el:
                    logged_in = True
                    print(f"  >>> Login detected at {elapsed}s!")
                    break
            if elapsed % 15 == 0:
                print(f"  Waiting... {elapsed}s elapsed")

        if not logged_in:
            print("  Timeout: no login detected after 120s.")

        # 4. Refresh & re-check
        await page.reload(wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        user_el = await page.query_selector(
            "[class*='user'], [class*='avatar'], [class*='sidebar']"
        )
        login_el = await page.query_selector(
            "[class*='login'], [class*='signin'], [class*='qrcode']"
        )
        direct_logged_in = user_el is not None

        # check_login() — opens new page internally
        print()
        logger.info("Calling crawler.check_login()...")
        check_result = await crawler.check_login()

        # 5. Output
        print()
        print("=" * 55)
        print(f"  Direct page detection:  {'Logged In' if direct_logged_in else 'Not Logged In'}")
        print(f"  check_login() result:   {'Logged In' if check_result else 'Not Logged In'}")
        print(f"  has_cookies() result:   {crawler.has_cookies()}")
        print(f"  Profile dir:            {bm._user_data_dir}")
        print("=" * 55)

        await asyncio.sleep(3)

    finally:
        await bm.close()
        logger.info("Browser closed. Profile saved.")


if __name__ == "__main__":
    asyncio.run(main())

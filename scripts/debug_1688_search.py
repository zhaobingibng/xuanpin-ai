#!/usr/bin/env python3
"""Debug 1688 search - save HTML/screenshots for analysis.

Usage:
    python scripts/debug_1688_search.py
    python scripts/debug_1688_search.py --keyword "海苔卷"
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger

from app.crawler.alibaba_1688 import Alibaba1688Crawler


DEBUG_DIR = PROJECT_ROOT / "storage" / "alibaba_debug"


async def debug_search(keyword: str = "海苔卷") -> dict:
    """Debug 1688 search with a fixed keyword.
    
    Args:
        keyword: Search keyword.
    
    Returns:
        Debug info dict.
    """
    # Create debug directory
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_prefix = f"{timestamp}_{keyword[:20]}"
    
    logger.info("=" * 70)
    logger.info("1688 Search Debug")
    logger.info(f"Keyword: {keyword}")
    logger.info(f"Debug dir: {DEBUG_DIR}")
    logger.info("=" * 70)
    
    # Initialize crawler
    crawler = Alibaba1688Crawler()
    
    debug_info = {
        "keyword": keyword,
        "timestamp": timestamp,
        "pages": [],
    }
    
    try:
        # Check login
        logger.info("\n[1] Checking login...")
        is_logged_in = await crawler.check_login()
        logger.info(f"  Logged in: {is_logged_in}")
        debug_info["logged_in"] = is_logged_in
        
        if not is_logged_in:
            logger.error("Not logged in! Please run login_taobao.py first.")
            return debug_info
        
        # Create context and page
        logger.info("\n[2] Creating browser context...")
        context = await crawler._new_context()
        page = await context.new_page()
        
        # Load cookies and storage state
        await crawler.load_cookies(context)
        await crawler.load_storage_state(context)
        
        # 注入事件捕获脚本（在页面加载前执行）
        event_capture_script = """
            // 初始化事件捕获数组
            if (!window.__1688_debug) {
                window.__1688_debug = [];
            }
            
            // 监听 postMessage 事件
            window.addEventListener('message', e => {
                if (e.data && e.data.action) {
                    window.__1688_debug.push({
                        type: 'message',
                        action: e.data.action,
                        data: e.data.data || e.data,
                        timestamp: Date.now()
                    });
                }
            });
            
            // 监听 search:firstDataReady:offerV2 自定义事件
            window.addEventListener('search:firstDataReady:offerV2', e => {
                window.__1688_debug.push({
                    type: 'offerV2',
                    detail: e.detail,
                    timestamp: Date.now()
                });
            });
            
            // Hook window.dispatchEvent 捕获所有 CustomEvent
            const originalDispatch = window.dispatchEvent.bind(window);
            window.dispatchEvent = function(event) {
                if (event && event.type) {
                    window.__1688_debug.push({
                        type: 'dispatch',
                        eventType: event.type,
                        detail: event.detail || null,
                        timestamp: Date.now()
                    });
                }
                return originalDispatch(event);
            };
        """
        await page.add_init_script(event_capture_script)
        logger.info("  Event capture script injected")
        
        # Navigate to search page
        search_url = f"{crawler.SEARCH_URL}?keywords={keyword}"
        logger.info(f"\n[3] Navigating to: {search_url}")
        
        page = await crawler._browser_manager.safe_goto(
            page, search_url, platform=crawler.PLATFORM
        )
        
        # Wait for page to load - try multiple strategies
        logger.info("\n[4] Waiting for page content...")
        
        # Strategy 1: Wait for specific selectors
        wait_selectors = [
            "[class*='offer'] [class*='card']",
            "[class*='offer-card']",
            ".sm-offer-item",
            "[class*='item'][class*='product']",
            "a[href*='detail.1688']",
        ]
        
        content_found = False
        for selector in wait_selectors:
            try:
                await page.wait_for_selector(selector, timeout=10000)
                logger.info(f"  Found content with selector: {selector}")
                content_found = True
                break
            except Exception:
                continue
        
        if not content_found:
            logger.warning("  No product content found via selectors, waiting extra...")
            await page.wait_for_timeout(10000)  # Extra wait
        
        # Get page info
        page_title = await page.title()
        current_url = page.url
        html_content = await page.content()
        html_length = len(html_content)
        
        logger.info(f"\n[4] Page info:")
        logger.info(f"  Title: {page_title}")
        logger.info(f"  URL: {current_url}")
        logger.info(f"  HTML length: {html_length}")
        
        # Check for anti-bot
        is_anti_bot = "sec.1688" in current_url or "punish" in current_url
        logger.info(f"  Anti-bot redirect: {is_anti_bot}")
        
        # Check for login prompts or error messages
        login_prompts = []
        if "login" in html_content.lower() and "sign" in html_content.lower():
            login_prompts.append("login/sign prompt found")
        if "empty" in html_content.lower() or "no result" in html_content.lower():
            login_prompts.append("empty/no result found")
        if login_prompts:
            logger.warning(f"  Page issues: {login_prompts}")
        
        # Check for product-related keywords in HTML
        product_keywords = ["offer", "card", "product", "price", "¥", "元"]
        found_keywords = []
        for kw in product_keywords:
            if kw.lower() in html_content.lower():
                found_keywords.append(kw)
        logger.info(f"  Found product keywords: {found_keywords}")
        
        # Save HTML
        html_path = DEBUG_DIR / f"{debug_prefix}_page.html"
        html_path.write_text(html_content, encoding="utf-8")
        logger.info(f"\n[5] HTML saved: {html_path}")
        
        # Take screenshot
        screenshot_path = DEBUG_DIR / f"{debug_prefix}_screenshot.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        logger.info(f"  Screenshot saved: {screenshot_path}")
        
        # Find cards
        cards = await page.query_selector_all(crawler._card_selector)
        logger.info(f"\n[6] Card selector: {crawler._card_selector}")
        logger.info(f"  Cards found: {len(cards)}")
        
        # Try alternative selectors
        alt_selectors = [
            "[class*='offer']",
            "[class*='card']",
            "[class*='item']",
            "[class*='product']",
            "a[href*='detail']",
        ]
        
        alt_results = {}
        for sel in alt_selectors:
            try:
                elements = await page.query_selector_all(sel)
                alt_results[sel] = len(elements)
            except Exception as e:
                alt_results[sel] = f"error: {e}"
        
        logger.info(f"\n[7] Alternative selector results:")
        for sel, count in alt_results.items():
            logger.info(f"  {sel}: {count}")
        
        # ── Event 调试输出 ──────────────────────────────────────
        logger.info(f"\n[8] Event Debug:")
        
        # 读取捕获的事件
        events = await page.evaluate("""
            () => {
                return window.__1688_debug || [];
            }
        """)
        
        logger.info(f"  [1688 EVENT] Found {len(events)} events")
        
        # 输出前10个事件详情
        for i, event in enumerate(events[:10]):
            if isinstance(event, dict):
                event_type = event.get("type", "unknown")
                action = event.get("action", "")
                event_type_name = event.get("eventType", "")
                detail = event.get("detail", {})
                
                logger.info(f"  Event {i+1}:")
                logger.info(f"    type: {event_type}")
                if action:
                    logger.info(f"    action: {action}")
                if event_type_name:
                    logger.info(f"    eventType: {event_type_name}")
                if detail:
                    detail_keys = list(detail.keys()) if isinstance(detail, dict) else str(type(detail))
                    logger.info(f"    detail keys: {detail_keys}")
        
        # 保存事件原始数据到 JSON
        events_path = DEBUG_DIR / f"{debug_prefix}_events.json"
        events_path.write_text(
            json.dumps(events, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8"
        )
        logger.info(f"  Events saved: {events_path}")
        
        # 如果事件数量为0，输出警告
        if len(events) == 0:
            logger.warning("  No events captured! The page may not be using postMessage/CustomEvent for data.")
            logger.warning("  Check if the login state is valid or if 1688 changed their data loading mechanism.")
        
        # 将事件信息添加到 debug_info
        debug_info["events"] = {
            "count": len(events),
            "events": events[:20],  # 只保存前20个
        }
        
        # Save debug info
        debug_info["pages"].append({
            "page_num": 1,
            "title": page_title,
            "url": current_url,
            "html_length": html_length,
            "is_anti_bot": is_anti_bot,
            "found_keywords": found_keywords,
            "cards_found": len(cards),
            "alternative_selectors": alt_results,
            "events_count": len(events),
        })
        
        # Save search info
        info_path = DEBUG_DIR / f"{debug_prefix}_info.json"
        info_path.write_text(json.dumps(debug_info, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"\n[8] Debug info saved: {info_path}")
        
        await context.close()
        
    except Exception as e:
        logger.error(f"Debug failed: {e}")
        debug_info["error"] = str(e)
    
    finally:
        await crawler.close()
    
    return debug_info


def print_summary(debug_info: dict):
    """Print debug summary."""
    print("\n" + "=" * 70)
    print("1688 Search Debug Summary")
    print("=" * 70)
    
    print(f"\nKeyword: {debug_info['keyword']}")
    print(f"Logged in: {debug_info.get('logged_in', 'N/A')}")
    
    if debug_info.get("error"):
        print(f"\nERROR: {debug_info['error']}")
        return
    
    for page_info in debug_info.get("pages", []):
        print(f"\n--- Page {page_info['page_num']} ---")
        print(f"  Title: {page_info['title']}")
        print(f"  URL: {page_info['url']}")
        print(f"  HTML length: {page_info['html_length']}")
        print(f"  Anti-bot: {page_info['is_anti_bot']}")
        print(f"  Product keywords found: {page_info['found_keywords']}")
        print(f"  Cards found: {page_info['cards_found']}")
        print(f"  Events captured: {page_info.get('events_count', 0)}")
        
        print(f"\n  Alternative selectors:")
        for sel, count in page_info.get("alternative_selectors", {}).items():
            print(f"    {sel}: {count}")
    
    # Event summary
    events_info = debug_info.get("events", {})
    if events_info:
        print(f"\n--- Events Summary ---")
        print(f"  Total events: {events_info.get('count', 0)}")
        events = events_info.get("events", [])
        if events:
            event_types = {}
            for e in events:
                if isinstance(e, dict):
                    t = e.get("type", "unknown")
                    event_types[t] = event_types.get(t, 0) + 1
            print(f"  Event types: {event_types}")
    
    print("\n" + "=" * 70)
    print(f"Debug files saved to: {DEBUG_DIR}")
    print("=" * 70)


async def main():
    parser = argparse.ArgumentParser(description="Debug 1688 search")
    parser.add_argument("--keyword", type=str, default="海苔卷", help="Search keyword")
    args = parser.parse_args()
    
    debug_info = await debug_search(keyword=args.keyword)
    print_summary(debug_info)
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

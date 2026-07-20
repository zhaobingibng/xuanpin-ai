"""Taobao login via headful (visible) Playwright browser.
Temporarily overrides headless=False so user can log in directly in the Playwright window.
"""
import asyncio
import json
from pathlib import Path
from app.config.settings import get_settings
from app.crawler.browser import BrowserManager
from app.crawler.base import CookieManager


async def main():
    settings = get_settings()

    # Override to headful mode for login
    settings.browser_headless = False

    cookie_manager = CookieManager(settings.cookie_dir)
    bm = BrowserManager(settings, cookie_manager)

    print("=" * 60)
    print("  Taobao Login — Headful Playwright Browser")
    print("=" * 60)
    print("\nA browser window will open. Please log in to Taobao there.")
    print("After login, the script will automatically detect and continue.\n")

    ctx = await bm.new_context("taobao")
    page = await ctx.new_page()

    # Go to Taobao login
    await page.goto("https://login.taobao.com/member/login.jhtml", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)

    ss_dir = Path(settings.browser_user_data_dir).parent
    ss_dir.mkdir(parents=True, exist_ok=True)

    print("Waiting for login (up to 5 minutes)...")
    logged_in = False
    for i in range(60):
        await page.wait_for_timeout(5000)
        url = page.url

        # If redirected away from login page
        if "login" not in url.lower():
            print(f"  Redirected to: {url[:100]}")
            logged_in = True
            break

        # Check page content
        status = await page.evaluate("""
            () => {
                const body = document.body.innerText || '';
                if (body.includes('我的淘宝') || body.includes('个人中心')) return 'success';
                return 'waiting';
            }
        """)
        if status == 'success':
            print("  Login detected!")
            logged_in = True
            break

        if i % 6 == 0 and i > 0:
            print(f"  Still waiting... ({i*5}s elapsed)")

    if logged_in:
        print("\n[OK] Login successful! Verifying...")
        await page.wait_for_timeout(2000)

        # Go to homepage
        await page.goto("https://www.taobao.com", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)

        # Get nick
        nick = await page.evaluate("""
            () => {
                const els = document.querySelectorAll('.J_UserMemberNickUrl, [class*="nick"]');
                for (const el of els) {
                    const t = (el.innerText || '').trim();
                    if (t && !t.includes('请登录')) return t;
                }
                return '';
            }
        """)
        print(f"  User: {nick or '(unknown)'}")

        # Test search
        print("\n[TEST] Searching for '蓝牙耳机'...")
        await page.goto("https://s.taobao.com/search?q=蓝牙耳机", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(10000)  # wait 10s for full render

        await page.screenshot(path=str(ss_dir / "taobao_search_loggedin.png"))
        print(f"  URL: {page.url[:120]}")

        is_login = await page.evaluate("""
            () => {
                const body = document.body.innerText || '';
                return body.includes('请重新登录') || body.includes('密码登录');
            }
        """)
        print(f"  Login page: {is_login}")

        content = await page.evaluate("""
            () => {
                const root = document.getElementById('root');
                const imgs = document.querySelectorAll('img[src*="alicdn"]');
                const links = document.querySelectorAll('a[href*="item.taobao"], a[href*="detail.tmall"]');
                return {
                    rootChildren: root ? root.children.length : -1,
                    alicdnImages: imgs.length,
                    productLinks: links.length,
                    totalDivs: document.querySelectorAll('div').length,
                    bodyText: document.body.innerText.substring(0, 300),
                };
            }
        """)
        print(f"  Root children: {content['rootChildren']}")
        print(f"  Alicdn images: {content['alicdnImages']}")
        print(f"  Product links: {content['productLinks']}")
        print(f"  Total divs: {content['totalDivs']}")

        result = {
            "logged_in": True,
            "nick": nick,
            "search_is_login_page": is_login,
            "root_children": content["rootChildren"],
            "product_links": content["productLinks"],
            "alicdn_images": content["alicdnImages"],
            "total_divs": content["totalDivs"],
        }
    else:
        print("\n[FAIL] Login not detected after 5 minutes.")
        result = {"logged_in": False}

    # Save result
    result_path = ss_dir / "taobao_login_result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResult saved: {result_path}")

    await bm.close()


if __name__ == "__main__":
    asyncio.run(main())

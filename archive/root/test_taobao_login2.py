"""Taobao login via Playwright persistent context — ensures session saves to profile."""
import asyncio
from pathlib import Path
from app.config.settings import get_settings
from app.crawler.browser import BrowserManager
from app.crawler.base import CookieManager


async def main():
    settings = get_settings()
    cookie_manager = CookieManager(settings.cookie_dir)
    bm = BrowserManager(settings, cookie_manager)

    print("Opening Taobao login page in Playwright browser...")
    print("Please complete login in the browser window that appears.")
    print("The browser may be headless — checking login state in loop.\n")

    ctx = await bm.new_context("taobao")
    page = await ctx.new_page()

    # Navigate to login page
    await page.goto("https://login.taobao.com/member/login.jhtml", wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(2000)

    # Screenshot the login page
    ss_dir = Path(settings.browser_user_data_dir).parent
    ss_dir.mkdir(parents=True, exist_ok=True)

    await page.screenshot(path=str(ss_dir / "taobao_login_prompt.png"))
    print("Login page opened. Please complete login.")
    print("Waiting for login to complete (checking every 5s)...\n")

    # Poll for login completion
    logged_in = False
    for attempt in range(60):  # wait up to 5 minutes
        await page.wait_for_timeout(5000)
        current_url = page.url

        # Check if redirected away from login page (login success)
        if "login" not in current_url.lower():
            print(f"Redirected to: {current_url[:100]}")
            print("Login appears successful!")
            logged_in = True
            break

        # Check for logged-in indicators on current page
        is_logged = await page.evaluate("""
            () => {
                const body = document.body.innerText || '';
                // If we see the user's nick or account page elements
                if (body.includes('我的淘宝') || body.includes('个人中心')) return true;
                // Check for member nick
                const nick = document.querySelector('.login-view .nick, [class*="nick-info"]');
                if (nick && nick.innerText.trim() && !nick.innerText.includes('请登录')) return true;
                return false;
            }
        """)
        if is_logged:
            print("Login detected!")
            logged_in = True
            break

        if attempt % 6 == 0:
            await page.screenshot(path=str(ss_dir / "taobao_login_progress.png"))
            print(f"  Still waiting... (attempt {attempt+1}/60)")

    if logged_in:
        # Navigate to homepage to verify
        print("\nVerifying login on homepage...")
        await page.goto("https://www.taobao.com", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)

        nick_text = await page.evaluate("""
            () => {
                const el = document.querySelector('.J_UserMemberNickUrl');
                if (el) return el.innerText.trim();
                const els = document.querySelectorAll('[class*="nick"]');
                for (const e of els) {
                    const t = e.innerText.trim();
                    if (t && !t.includes('请登录') && !t.includes('登录')) return t;
                }
                return '';
            }
        """)
        print(f"User nick: '{nick_text}'")

        # Now try search
        print("\nTesting search page...")
        await page.goto("https://s.taobao.com/search?q=蓝牙耳机", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(8000)

        await page.screenshot(path=str(ss_dir / "taobao_search_after_login.png"))
        print(f"Search URL: {page.url[:120]}")
        print(f"Title: {await page.title()}")

        is_login_page = await page.evaluate("""
            () => {
                const body = document.body.innerText || '';
                return body.includes('请重新登录') || body.includes('密码登录');
            }
        """)

        content = await page.evaluate("""
            () => {
                const imgs = document.querySelectorAll('img[src*="alicdn"]');
                const links = document.querySelectorAll('a[href*="item.taobao"], a[href*="detail.tmall"]');
                const prices = document.querySelectorAll('[class*="price"], [class*="Price"]');
                const root = document.getElementById('root');
                return {
                    rootChildren: root ? root.children.length : -1,
                    alicdnImages: imgs.length,
                    productLinks: links.length,
                    priceElements: prices.length,
                    bodyPreview: document.body.innerText.substring(0, 200),
                };
            }
        """)
        print(f"Is login page: {is_login_page}")
        print(f"Root children: {content['rootChildren']}")
        print(f"Alicdn images: {content['alicdnImages']}")
        print(f"Product links: {content['productLinks']}")
        print(f"Price elements: {content['priceElements']}")

        # Write results to file (avoid GBK encoding issues)
        result = {
            "logged_in": logged_in,
            "nick": nick_text,
            "search_is_login_page": is_login_page,
            "root_children": content["rootChildren"],
            "product_links": content["productLinks"],
            "alicdn_images": content["alicdnImages"],
        }
        import json
        (ss_dir / "taobao_login_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nResult saved to: {ss_dir / 'taobao_login_result.json'}")
    else:
        print("\nTimeout: login not detected after 5 minutes.")

    await bm.close()


if __name__ == "__main__":
    asyncio.run(main())

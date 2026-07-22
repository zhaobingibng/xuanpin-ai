"""Quick Taobao login diagnostic — check if persistent profile has Taobao session."""
import asyncio
from pathlib import Path
from app.config.settings import get_settings
from app.crawler.browser import BrowserManager
from app.crawler.base import CookieManager


async def main():
    settings = get_settings()
    cookie_manager = CookieManager(settings.cookie_dir)
    bm = BrowserManager(settings, cookie_manager)

    try:
        ctx = await bm.new_context("taobao")
        page = await ctx.new_page()

        # Step 1: Go to taobao homepage
        print("[1] Opening taobao.com homepage...")
        await page.goto("https://www.taobao.com", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)
        print(f"    URL: {page.url}")
        print(f"    Title: {await page.title()}")

        # Screenshot homepage
        ss1 = Path(settings.browser_user_data_dir).parent / "taobao_home_check.png"
        await page.screenshot(path=str(ss1), full_page=False)
        print(f"    Screenshot: {ss1}")

        # Check for user nick
        nick = await page.evaluate("""
            () => {
                const els = document.querySelectorAll(
                    '.J_UserMemberNickUrl, .member-nick-info, [class*=\"nick\"], .site-nav-user .site-nav-user-hd'
                );
                const results = [];
                els.forEach(el => {
                    const t = (el.innerText || '').trim();
                    if (t) results.push({ cls: el.className.substring(0,60), text: t.substring(0,40) });
                });
                // Also check for "亲，请登录" which means NOT logged in
                const loginTexts = document.querySelectorAll('[class*=\"login\"], [class*=\"Login\"]');
                loginTexts.forEach(el => {
                    const t = (el.innerText || '').trim();
                    if (t.includes('登录') || t.includes('login')) results.push({ type: 'login_prompt', text: t.substring(0,40) });
                });
                return results;
            }
        """)
        print(f"    Login indicators: {len(nick)}")
        for n in nick[:8]:
            print(f"      {n}")

        # Step 2: Check cookies
        print("\n[2] Checking cookies...")
        cookies = await ctx.cookies()
        taobao_cookies = [c for c in cookies if "taobao" in c.get("domain", "")]
        login_cookies = [c for c in taobao_cookies if c.get("name", "") in (
            "_m_h5_tk", "_m_h5_tk_enc", "cookie2", "sgcookie", "_tb_token_",
            "csg", "dnk", "uc1", "uc3"
        )]
        print(f"    Total cookies: {len(cookies)}")
        print(f"    Taobao cookies: {len(taobao_cookies)}")
        print(f"    Key login cookies: {len(login_cookies)}")
        for c in login_cookies:
            print(f"      {c['name']} = {c['value'][:20]}... (domain: {c['domain']})")

        # Step 3: Try search page directly
        print("\n[3] Navigating to search page...")
        await page.goto("https://s.taobao.com/search?q=蓝牙耳机", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(8000)  # wait 8s for full render
        print(f"    URL: {page.url[:120]}")
        print(f"    Title: {await page.title()}")

        # Check if login page or search results
        is_login = await page.evaluate("""
            () => {
                const body = document.body.innerText || '';
                if (body.includes('请重新登录') || body.includes('密码登录')) return true;
                const forms = document.querySelectorAll('form, [class*=\"login-form\"], [class*=\"loginForm\"]');
                if (forms.length > 0) return true;
                return false;
            }
        """)
        print(f"    Is login page: {is_login}")

        # Check for actual product content
        content_check = await page.evaluate("""
            () => {
                const all = document.body.innerText.substring(0, 500);
                const imgs = document.querySelectorAll('img[src*=\"alicdn\"]');
                const prices = document.querySelectorAll('[class*=\"price\"], [class*=\"Price\"]');
                const links = document.querySelectorAll('a[href*=\"item.taobao\"], a[href*=\"detail.tmall\"]');
                return {
                    bodyPreview: all.substring(0, 200),
                    alicdnImages: imgs.length,
                    priceElements: prices.length,
                    productLinks: links.length,
                };
            }
        """)
        print(f"    Content check:")
        print(f"      alicdn images: {content_check['alicdnImages']}")
        print(f"      price elements: {content_check['priceElements']}")
        print(f"      product links: {content_check['productLinks']}")
        print(f"      body preview: {content_check['bodyPreview'][:100]}")

        # Screenshot search page
        ss2 = Path(settings.browser_user_data_dir).parent / "taobao_search_check.png"
        await page.screenshot(path=str(ss2), full_page=False)
        print(f"    Screenshot: {ss2}")

    finally:
        await bm.close()


if __name__ == "__main__":
    asyncio.run(main())

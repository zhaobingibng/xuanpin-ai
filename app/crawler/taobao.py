"""Taobao (淘宝) crawler — Phase 1 feasibility verification only.

NOT integrated into pipeline. Used solely to validate:
- Page accessibility with persistent browser profile
- Login state detection
- Product card DOM structure
- Anti-bot risk assessment
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from loguru import logger

from app.crawler.base import BaseCrawler
from app.crawler.browser import BrowserManager, random_delay, random_scroll
from app.crawler.models.schemas import RawProduct
from app.config.settings import get_settings


class TaobaoCrawler(BaseCrawler):
    """Taobao search page crawler — verification only.

    Phase 1: validates page access, login, DOM structure.
    Not integrated into CrawlerManager or crawler_jobs.
    """

    PLATFORM = "taobao"
    BASE_URL = "https://www.taobao.com"
    SEARCH_URL = "https://s.taobao.com/search"

    async def check_login(self) -> bool:
        """Check if Taobao session is logged in via persistent profile."""
        context = None
        try:
            context = await self._new_context()
            page = await context.new_page()
            await page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)

            # Check for login indicators
            login_selectors = [
                ".site-nav-user .site-nav-user-hd",       # username in nav
                "[class*='nick']",                         # nickname
                ".member-nick",                            # member nick
                "a[href*='member.taobao.com']",            # member link
                ".J_SiteNavLogin .site-nav-menu-hd",      # login area with name
            ]
            for sel in login_selectors:
                el = await page.query_selector(sel)
                if el:
                    text = (await el.inner_text()).strip()
                    if text and text not in ("登录", "亲，请登录"):
                        logger.info("[taobao] login detected: selector='{}', text='{}'", sel, text[:30])
                        return True

            # Check if login button is visible (means NOT logged in)
            not_logged_in = [
                "a[href*='login.taobao.com']",
                ".site-nav-login",
            ]
            for sel in not_logged_in:
                el = await page.query_selector(sel)
                if el:
                    text = (await el.inner_text()).strip()
                    if "登录" in text or "login" in text.lower():
                        logger.info("[taobao] NOT logged in — found login prompt")
                        return False

            logger.info("[taobao] login state ambiguous, defaulting to False")
            return False

        except Exception as e:
            logger.warning("[taobao] login check failed: {}", e)
            return False
        finally:
            if context:
                await context.close()

    async def _do_crawl(self, keyword: str, max_pages: int = 1) -> list[RawProduct]:
        """Verification crawl — single page only."""
        products: list[RawProduct] = []
        context = await self._new_context()
        try:
            page = await context.new_page()

            url = f"{self.SEARCH_URL}?q={keyword}"
            logger.info("[taobao] Navigating to: {}", url)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # Scroll to trigger lazy loading
            await random_scroll(page, times=2)
            await random_delay(1000, 2000)

            # Check for anti-bot redirect
            final_url = page.url
            logger.info("[taobao] Final URL: {}", final_url[:150])

            if "login" in final_url.lower() or "sec.taobao" in final_url:
                logger.warning("[taobao] Redirected to login/security page")
                return []

            # Try multiple selector patterns for product cards
            card_selectors = [
                ".Content--contentInner--QVTcU0M .Card--doubleCardWrapper--IFCaXbl",
                "[class*='Card--doubleCard']",
                "[class*='contentInner']",
                ".search-content-col",
                ".item.J_MouserOnverReq",
                ".items .item",
                "[data-category]",
                "a[href*='detail.tmall.com'], a[href*='item.taobao.com']",
            ]

            cards = []
            matched_selector = ""
            for sel in card_selectors:
                cards = await page.query_selector_all(sel)
                if cards:
                    matched_selector = sel
                    break

            logger.info("[taobao] Cards found: {} (selector: {})", len(cards), matched_selector)

            for card in cards[:5]:
                product = await self._parse_product(card)
                if product:
                    products.append(product)

        finally:
            await context.close()

        return products

    async def _parse_product(self, element) -> RawProduct | None:
        """Parse a single Taobao product card."""
        try:
            # Title — try multiple selectors
            name = ""
            for sel in [
                "[class*='Title--title']",
                "[class*='title']",
                "[class*='row-2']",
                ".title",
                "a[title]",
            ]:
                el = await element.query_selector(sel)
                if el:
                    name = (await el.inner_text()).strip()
                    if name:
                        break
            if not name:
                # fallback: try a[title] attribute
                el = await element.query_selector("a[title]")
                if el:
                    name = (await el.get_attribute("title")) or ""

            if not name:
                return None

            # Price
            price = 0.0
            for sel in [
                "[class*='Price--priceInt']",
                "[class*='price']",
                ".price",
            ]:
                el = await element.query_selector(sel)
                if el:
                    text = await el.inner_text()
                    nums = "".join(c for c in text if c.isdigit() or c == ".")
                    if nums:
                        try:
                            price = float(nums)
                        except ValueError:
                            pass
                    if price:
                        break

            # Image
            image = None
            img_el = await element.query_selector("img[src*='img.alicdn'], img")
            if img_el:
                image = await img_el.get_attribute("src")

            # Shop
            shop = ""
            for sel in [
                "[class*='Shop--shopName']",
                "[class*='shop']",
                "[class*='store']",
            ]:
                el = await element.query_selector(sel)
                if el:
                    shop = (await el.inner_text()).strip()
                    if shop:
                        break

            # Sales
            sales = 0
            for sel in [
                "[class*='Deal--deal']",
                "[class*='sales']",
                "[class*='sold']",
            ]:
                el = await element.query_selector(sel)
                if el:
                    text = await el.inner_text()
                    sales = self.parse_count(text)
                    if sales:
                        break

            # URL
            url = None
            link_el = await element.query_selector("a[href*='item.taobao'], a[href*='detail.tmall']")
            if link_el:
                url = await link_el.get_attribute("href")

            return RawProduct(
                name=name,
                platform=self.PLATFORM,
                shop=shop or "未知店铺",
                price=price,
                image=image,
                sales_24h=sales,
                url=url,
            )

        except Exception as e:
            logger.warning("[taobao] parse error: {}", e)
            return None


async def _dump_page_structure(page) -> dict:
    """Dump key DOM elements for Taobao page analysis."""
    info: dict = {}

    # Page title
    info["title"] = await page.title()
    info["url"] = page.url

    # Check for slider / captcha
    captcha_selectors = [
        "#nc_1_wrapper",
        "#nc_1__scale_text",
        "[class*='slider']",
        "[class*='captcha']",
        "#baxia-dialog",
        ".J_MIDDLEWARE",
    ]
    for sel in captcha_selectors:
        el = await page.query_selector(sel)
        if el:
            info.setdefault("captcha_elements", []).append(sel)

    # Dump top-level structure
    structure = await page.evaluate("""
        () => {
            const result = [];
            // Main content containers
            const containers = document.querySelectorAll(
                '#root, #app, #content, .search-content, [class*=\"Content\"], [class*=\"content\"]'
            );
            containers.forEach(el => {
                result.push({
                    tag: el.tagName,
                    id: el.id,
                    className: (el.className || '').toString().substring(0, 120),
                    childCount: el.children.length,
                });
            });
            // Links to item pages
            const itemLinks = document.querySelectorAll(
                'a[href*=\"item.taobao\"], a[href*=\"detail.tmall\"], a[href*=\"detail.taobao\"]'
            );
            result.push({
                tag: 'STATS',
                itemLinks: itemLinks.length,
            });
            return result;
        }
    """)
    info["structure"] = structure

    # Get all card-like containers
    card_analysis = await page.evaluate("""
        () => {
            const results = [];
            // Look for repetitive structures that could be product cards
            const all = document.querySelectorAll('[class*=\"Card\"], [class*=\"card\"], .item, [class*=\"item\"]');
            const classMap = {};
            all.forEach(el => {
                const cls = (el.className || '').toString().substring(0, 80);
                if (!classMap[cls]) classMap[cls] = { count: 0, sample: '' };
                classMap[cls].count++;
                if (!classMap[cls].sample) {
                    classMap[cls].sample = el.innerText.substring(0, 100);
                }
            });
            for (const [cls, data] of Object.entries(classMap)) {
                if (data.count >= 3) {
                    results.push({ class: cls, count: data.count, sample: data.sample });
                }
            }
            return results;
        }
    """)
    info["card_analysis"] = card_analysis

    # Check login state from page content
    body_text = await page.evaluate("() => document.body.innerText.substring(0, 500)")
    info["body_preview"] = body_text[:300]

    return info


async def main():
    """Run Taobao feasibility verification."""
    settings = get_settings()
    report: dict = {
        "timestamp": datetime.now().isoformat(),
        "keyword": "蓝牙耳机",
        "steps": [],
    }

    print("=" * 60)
    print("  Taobao Phase 1 — Feasibility Verification")
    print("=" * 60)

    crawler = TaobaoCrawler()

    try:
        # ── Step 1: Open Taobao homepage ──
        print("\n[Step 1] Opening Taobao homepage...")
        context = await crawler._new_context()
        page = await context.new_page()

        try:
            await page.goto(crawler.BASE_URL, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)
            step1 = {"action": "open_homepage", "success": True, "url": page.url}
            print(f"  URL: {page.url[:100]}")
            print(f"  Title: {await page.title()}")
        except Exception as e:
            step1 = {"action": "open_homepage", "success": False, "error": str(e)}
            print(f"  FAILED: {e}")
        report["steps"].append(step1)

        # ── Step 2: Check login state ──
        print("\n[Step 2] Checking login state...")
        # Analyze page for login indicators
        login_info = await page.evaluate("""
            () => {
                const result = { logged_in: false, indicators: [] };
                // Look for user nick / name
                const navEls = document.querySelectorAll(
                    '[class*=\"nick\"], [class*=\"user\"], [class*=\"member\"], [class*=\"login\"]'
                );
                navEls.forEach(el => {
                    const text = (el.innerText || '').trim();
                    if (text) {
                        result.indicators.push({
                            class: (el.className || '').toString().substring(0, 60),
                            text: text.substring(0, 40),
                        });
                    }
                });
                // Check for explicit login link
                const loginLinks = document.querySelectorAll('a[href*=\"login\"]');
                loginLinks.forEach(el => {
                    result.indicators.push({
                        type: 'login_link',
                        href: (el.href || '').substring(0, 80),
                        text: (el.innerText || '').substring(0, 40),
                    });
                });
                return result;
            }
        """)
        print(f"  Indicators found: {len(login_info.get('indicators', []))}")
        for ind in login_info.get("indicators", [])[:10]:
            print(f"    - class='{ind.get('class', '')[:40]}' text='{ind.get('text', '')[:30]}'")
        report["steps"].append({"action": "check_login", "indicators": login_info})

        # ── Step 3: Navigate to search ──
        print("\n[Step 3] Navigating to search page...")
        search_url = f"{crawler.SEARCH_URL}?q=蓝牙耳机"
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            # Wait longer for React hydration
            await page.wait_for_timeout(5000)

            final_url = page.url
            print(f"  Final URL: {final_url[:120]}")
            print(f"  Title: {await page.title()}")

            is_login_redirect = "login" in final_url.lower() and "taobao" in final_url.lower()
            is_security = "sec.taobao" in final_url or "punish" in final_url

            step3 = {
                "action": "search",
                "success": not (is_login_redirect or is_security),
                "final_url": final_url[:150],
                "login_redirect": is_login_redirect,
                "security_check": is_security,
            }
        except Exception as e:
            step3 = {"action": "search", "success": False, "error": str(e)}
            print(f"  FAILED: {e}")
            final_url = ""
        report["steps"].append(step3)

        if step3.get("success"):
            # ── Step 3b: Take screenshot for analysis ──
            print("\n[Step 3b] Taking screenshot...")
            ss_path = Path(settings.browser_user_data_dir).parent / "taobao_search.png"
            await page.screenshot(path=str(ss_path), full_page=False)
            print(f"  Screenshot saved: {ss_path}")

            # ── Step 4: Scroll and analyze DOM ──
            print("\n[Step 4] Scrolling and analyzing page structure...")
            await random_scroll(page, times=3)
            await random_delay(2000, 3000)

            # Check if content has rendered (not just skeleton)
            hydration_check = await page.evaluate("""
                () => {
                    const root = document.getElementById('root');
                    const result = {
                        rootChildren: root ? root.children.length : -1,
                        rootInnerHTML: root ? root.innerHTML.substring(0, 300) : '',
                        bodyChildren: document.body.children.length,
                        scriptCount: document.querySelectorAll('script').length,
                        hasReactRoot: !!document.querySelector('[data-reactroot]'),
                        allDivCount: document.querySelectorAll('div').length,
                        allLinks: document.querySelectorAll('a').length,
                    };
                    // Check for specific Taobao content indicators
                    result.hasPriceElements = document.querySelectorAll('[class*=\"price\"], [class*=\"Price\"]').length;
                    result.hasImgElements = document.querySelectorAll('img[src*=\"alicdn\"], img[src*=\"taobao\"]').length;
                    result.skeletonCount = document.querySelectorAll('[class*=\"bone\"], [class*=\"skeleton\"]').length;
                    return result;
                }
            """)
            print(f"  Hydration check:")
            print(f"    root children: {hydration_check.get('rootChildren', -1)}")
            print(f"    body children: {hydration_check.get('bodyChildren', 0)}")
            print(f"    total divs: {hydration_check.get('allDivCount', 0)}")
            print(f"    total links: {hydration_check.get('allLinks', 0)}")
            print(f"    price elements: {hydration_check.get('hasPriceElements', 0)}")
            print(f"    alicdn images: {hydration_check.get('hasImgElements', 0)}")
            print(f"    skeleton/bone elements: {hydration_check.get('skeletonCount', 0)}")

            # If skeleton is still showing, content hasn't loaded
            if hydration_check.get('skeletonCount', 0) > 5 and hydration_check.get('allLinks', 0) < 10:
                print("  → Page stuck in skeleton/loading state (content not rendered)")
                print("  → This usually means: login required OR anti-bot blocking")

                # Try waiting even longer
                print("  → Waiting 10 more seconds...")
                await page.wait_for_timeout(10000)
                recheck = await page.evaluate("""
                    () => ({
                        allLinks: document.querySelectorAll('a').length,
                        priceElements: document.querySelectorAll('[class*=\"price\"], [class*=\"Price\"]').length,
                        skeletonCount: document.querySelectorAll('[class*=\"bone\"], [class*=\"skeleton\"]').length,
                        bodyText: document.body.innerText.substring(0, 200),
                    })
                """)
                print(f"  → After 10s: links={recheck.get('allLinks', 0)}, prices={recheck.get('priceElements', 0)}, skeleton={recheck.get('skeletonCount', 0)}")

            page_info = await _dump_page_structure(page)
            print(f"  Page title: {page_info.get('title', 'N/A')}")
            print(f"  Structure containers: {len(page_info.get('structure', []))}")
            for s in page_info.get("structure", []):
                print(f"    - <{s.get('tag', '?')}> id='{s.get('id', '')}' class='{s.get('className', '')[:60]}' children={s.get('childCount', 0)}")

            if page_info.get("captcha_elements"):
                print(f"  CAPTCHA detected: {page_info['captcha_elements']}")

            print(f"\n  Card-like containers (count>=3):")
            for card in page_info.get("card_analysis", []):
                print(f"    - class='{card['class'][:60]}' count={card['count']}")
                print(f"      sample: '{card.get('sample', '')[:80]}'")

            report["steps"].append({
                "action": "analyze_structure",
                "info": page_info,
                "hydration": hydration_check,
            })

            # ── Step 5: Try parsing product cards ──
            print("\n[Step 5] Attempting to parse product cards...")
            await random_scroll(page, times=2)
            await random_delay(500, 1500)

            # Try all known selectors (including new Taobao PC layout)
            selectors_to_try = [
                "[class*='Card--doubleCard']",
                "[class*='CardWrapper']",
                "[class*='contentInner'] > div > div",
                "[class*='Content--content']",
                "[class*='leftContent'] > div > div > div",
                "#content_wrapper > div > div",
                ".search-content-col",
                "a[href*='item.taobao.com']",
                "a[href*='detail.tmall.com']",
                "a[href*='item.taobao']",
            ]

            best_count = 0
            best_selector = ""
            for sel in selectors_to_try:
                cards = await page.query_selector_all(sel)
                if len(cards) > best_count:
                    best_count = len(cards)
                    best_selector = sel
                print(f"  Selector: '{sel}' -> {len(cards)} elements")

            print(f"\n  Best selector: '{best_selector}' -> {best_count} cards")

            # Extract titles from best selector
            if best_count > 0:
                cards = await page.query_selector_all(best_selector)
                print(f"\n  First 5 product titles:")
                for i, card in enumerate(cards[:5]):
                    text = await card.inner_text()
                    first_line = text.split("\n")[0].strip()[:80]
                    print(f"    {i+1}. {first_line}")

            # Deep JS extraction
            js_results = await page.evaluate("""
                () => {
                    const results = [];
                    const links = document.querySelectorAll(
                        'a[href*=\"item.taobao.com\"], a[href*=\"detail.tmall.com\"], '
                        + 'a[href*=\"item.taobao\"], a[href*=\"detail.taobao\"]'
                    );
                    links.forEach((a, i) => {
                        if (i >= 10) return;
                        const card = a.closest('div[class]');
                        results.push({
                            href: (a.href || '').substring(0, 100),
                            title: (a.title || a.innerText || '').substring(0, 80),
                            cardClass: card ? (card.className || '').toString().substring(0, 80) : '',
                        });
                    });
                    return results;
                }
            """)
            print(f"\n  Product links found via JS: {len(js_results)}")
            for i, r in enumerate(js_results[:5]):
                print(f"    {i+1}. title='{r['title'][:60]}' cardClass='{r['cardClass'][:50]}'")

            report["steps"].append({
                "action": "parse_cards",
                "best_selector": best_selector,
                "best_count": best_count,
                "js_results": js_results[:5],
            })

        # ── Summary ──
        print("\n" + "=" * 60)
        print("  Verification Summary")
        print("=" * 60)
        print(f"  Homepage accessible: {step1.get('success', False)}")
        print(f"  Login state: {len(login_info.get('indicators', []))} indicators found")
        print(f"  Search accessible: {step3.get('success', False)}")
        if step3.get("login_redirect"):
            print("  → Login redirect detected")
        if step3.get("security_check"):
            print("  → Security/CAPTCHA check detected")
        if "best_count" in report["steps"][-1]:
            print(f"  Product cards: {report['steps'][-1]['best_count']}")
        print(f"  Anti-bot risk: {'LOW' if step3.get('success') else 'HIGH'}")

    finally:
        await crawler.close()

    # Save report
    report_path = Path(settings.browser_user_data_dir).parent / "taobao_verify_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\n  Report saved: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())

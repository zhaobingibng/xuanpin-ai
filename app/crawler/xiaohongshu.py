"""Xiaohongshu (小红书) product crawler."""

from loguru import logger

from app.crawler.base import BaseCrawler
from app.crawler.models.schemas import RawProduct


class XiaohongshuCrawler(BaseCrawler):
    """Crawl product data from Xiaohongshu (小红书)."""

    PLATFORM = "xiaohongshu"
    BASE_URL = "https://www.xiaohongshu.com"
    SEARCH_URL = "https://www.xiaohongshu.com/search_result"

    def __init__(self) -> None:
        super().__init__()
        self._cookie_file_path = self._cookies_dir / "xiaohongshu.json"

    # ── Login ─────────────────────────────────────────────────

    async def login(self) -> bool:
        """Manual login flow with cookie persistence."""
        if self.has_cookies():
            logger.info("[xiaohongshu] Existing cookies found, skipping login")
            return True
        return await super().login()

    # ── Crawl ─────────────────────────────────────────────────

    async def crawl(self, keyword: str, max_pages: int = 3) -> list[RawProduct]:
        """Search Xiaohongshu for *keyword* and scrape product cards."""
        logger.info("[xiaohongshu] Searching '{}' (max {} pages)", keyword, max_pages)
        products: list[RawProduct] = []

        context = await self._new_context()
        try:
            page = await context.new_page()
            await self.load_cookies(context)

            for page_num in range(1, max_pages + 1):
                url = f"{self.SEARCH_URL}?keyword={keyword}&source=web_search_result_notes&page={page_num}"
                logger.debug("[xiaohongshu] Page {}/{}: {}", page_num, max_pages, url)

                await page.goto(url, wait_until="networkidle")
                await page.wait_for_timeout(2000)
                await self._scroll_page(page, times=2)

                cards = await page.query_selector_all("[class*='note-item'], [class*='goods-card']")
                logger.info("[xiaohongshu] Page {}: found {} cards", page_num, len(cards))

                for card in cards:
                    product = await self._parse_product(card)
                    if product:
                        products.append(product)

            await self.save_cookies(context)

        finally:
            await context.close()

        logger.info("[xiaohongshu] Total products crawled: {}", len(products))
        return products

    # ── Parse ─────────────────────────────────────────────────

    async def _parse_product(self, element) -> RawProduct | None:
        """Parse a single Xiaohongshu product card element."""
        try:
            # Name / title
            name_el = await element.query_selector(
                "[class*='title'], [class*='name'], [class*='desc']"
            )
            name = (await name_el.inner_text()).strip() if name_el else ""
            if not name:
                return None

            # Price
            price = 0.0
            price_el = await element.query_selector("[class*='price']")
            if price_el:
                price_text = await price_el.inner_text()
                price_nums = price_text.replace("¥", "").replace("￥", "").strip()
                try:
                    price = float("".join(c for c in price_nums if c.isdigit() or c == "."))
                except ValueError:
                    pass

            # Image
            image = None
            img_el = await element.query_selector("img")
            if img_el:
                image = await img_el.get_attribute("src")

            # Shop
            shop = ""
            shop_el = await element.query_selector(
                "[class*='author'], [class*='shop'], [class*='store']"
            )
            if shop_el:
                shop = (await shop_el.inner_text()).strip()

            # Viewers / engagement
            viewers = 0
            view_el = await element.query_selector(
                "[class*='count'], [class*='browse'], [class*='like']"
            )
            if view_el:
                view_text = await view_el.inner_text()
                viewers = self.parse_count(view_text)

            # Link
            url = None
            link_el = await element.query_selector("a[href*='goods'], a[href*='explore']")
            if link_el:
                url = await link_el.get_attribute("href")

            return RawProduct(
                name=name,
                platform=self.PLATFORM,
                shop=shop or "未知店铺",
                price=price,
                image=image,
                viewers=viewers,
                sales_24h=0,
                url=url,
            )

        except Exception as e:
            logger.warning("[xiaohongshu] Failed to parse product card: {}", e)
            return None

    # ── Helpers ────────────────────────────────────────────────

    async def _check_login(self, page) -> bool:
        """Verify login status by checking for user-specific elements."""
        try:
            user_el = await page.query_selector("[class*='user'], [class*='avatar'], [class*='sidebar']")
            return user_el is not None
        except Exception:
            return False

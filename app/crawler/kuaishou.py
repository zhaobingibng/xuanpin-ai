"""Kuaishou (快手) product crawler."""

from loguru import logger

from app.crawler.base import BaseCrawler
from app.crawler.models.schemas import RawProduct


class KuaishouCrawler(BaseCrawler):
    """Crawl product data from Kuaishou e-commerce (快手电商)."""

    PLATFORM = "kuaishou"
    BASE_URL = "https://www.kuaishou.com"
    ECOM_URL = "https://university.kuaishou.com"
    SEARCH_URL = "https://www.kuaishou.com/search"

    def __init__(self) -> None:
        super().__init__()
        self._cookie_file_path = self._cookies_dir / "kuaishou.json"

    # ── Login ─────────────────────────────────────────────────

    async def login(self) -> bool:
        """Manual login flow for Kuaishou."""
        if self.has_cookies():
            logger.info("[kuaishou] Existing cookies found, skipping login")
            return True
        return await super().login()

    # ── Crawl ─────────────────────────────────────────────────

    async def crawl(self, keyword: str, max_pages: int = 3) -> list[RawProduct]:
        """Search Kuaishou for *keyword* and scrape product cards."""
        logger.info("[kuaishou] Searching '{}' (max {} pages)", keyword, max_pages)
        products: list[RawProduct] = []

        context = await self._new_context()
        try:
            page = await context.new_page()
            await self.load_cookies(context)

            for page_num in range(1, max_pages + 1):
                url = f"{self.SEARCH_URL}/video?searchKey={keyword}&page={page_num}"
                logger.debug("[kuaishou] Page {}/{}: {}", page_num, max_pages, url)

                await page.goto(url, wait_until="networkidle")
                await page.wait_for_timeout(3000)
                await self._scroll_page(page, times=3, delay_ms=2500)

                cards = await page.query_selector_all(
                    "[class*='product-card'], [class*='goods-card'], [class*='item-card']"
                )
                logger.info("[kuaishou] Page {}: found {} cards", page_num, len(cards))

                for card in cards:
                    product = await self._parse_product(card)
                    if product:
                        products.append(product)

            await self.save_cookies(context)

        finally:
            await context.close()

        logger.info("[kuaishou] Total products crawled: {}", len(products))
        return products

    # ── Parse ─────────────────────────────────────────────────

    async def _parse_product(self, element) -> RawProduct | None:
        """Parse a single Kuaishou product card element."""
        try:
            # Name
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
                "[class*='shop'], [class*='author'], [class*='anchor']"
            )
            if shop_el:
                shop = (await shop_el.inner_text()).strip()

            # Sales
            sales = 0
            sales_el = await element.query_selector(
                "[class*='sales'], [class*='sold'], [class*='buy-count']"
            )
            if sales_el:
                sales_text = await sales_el.inner_text()
                sales = self.parse_count(sales_text)

            # Viewers
            viewers = 0
            view_el = await element.query_selector(
                "[class*='view'], [class*='play'], [class*='watch']"
            )
            if view_el:
                view_text = await view_el.inner_text()
                viewers = self.parse_count(view_text)

            # Link
            url = None
            link_el = await element.query_selector("a[href*='goods'], a[href*='product']")
            if link_el:
                url = await link_el.get_attribute("href")

            return RawProduct(
                name=name,
                platform=self.PLATFORM,
                shop=shop or "未知店铺",
                price=price,
                image=image,
                viewers=viewers,
                sales_24h=sales,
                url=url,
            )

        except Exception as e:
            logger.warning("[kuaishou] Failed to parse product card: {}", e)
            return None

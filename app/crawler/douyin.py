"""Douyin (抖音) product crawler."""

from loguru import logger

from app.crawler.base import BaseCrawler
from app.crawler.models.schemas import RawProduct


class DouyinCrawler(BaseCrawler):
    """Crawl product data from Douyin e-commerce (抖音电商)."""

    PLATFORM = "douyin"
    BASE_URL = "https://www.douyin.com"
    ECOM_URL = "https://buyin.jinritemai.com"
    SEARCH_URL = "https://www.douyin.com/search"

    # ── Login ─────────────────────────────────────────────────

    async def login(self) -> bool:
        """Manual login flow for Douyin."""
        if self.has_cookies():
            logger.info("[douyin] Existing cookies found, skipping login")
            return True
        return await super().login()

    # ── Login detection ────────────────────────────────────────

    async def check_login(self) -> bool:
        """检测抖音登录状态。

        启动浏览器 → 加载 Cookie → 访问首页 → 判断登录元素。
        返回 True 已登录, False 未登录。
        """
        if not self.has_cookies():
            logger.info("[douyin] login required")
            return False

        context = None
        try:
            context = await self._new_context()
            await self.load_cookies(context)
            page = await context.new_page()
            timeout = self._settings.login_check_timeout * 1000
            await page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=timeout)

            # login-guide 元素存在 → 未登录
            guide_el = await page.query_selector("[class*='login-guide']")
            if guide_el:
                logger.info("[douyin] login required")
                return False

            # 登录按钮存在 → 未登录
            login_btn = await page.query_selector(
                "[class*='login-btn'], [class*='login-button']"
            )
            if login_btn:
                logger.info("[douyin] login required")
                return False

            # 用户信息 / 头像存在 → 已登录
            user_el = await page.query_selector(
                "[class*='avatar'], [class*='user-info']"
            )
            if user_el:
                logger.info("[douyin] login success")
                return True

            logger.info("[douyin] login required")
            return False

        except Exception as e:
            logger.warning("[douyin] login check failed: {}", e)
            return False
        finally:
            if context:
                await context.close()

    # ── Crawl ─────────────────────────────────────────────────

    async def _do_crawl(self, keyword: str, max_pages: int = 3) -> list[RawProduct]:
        """Search Douyin for *keyword* and scrape product cards."""
        products: list[RawProduct] = []

        context = await self._new_context()
        try:
            page = await context.new_page()
            await self.load_cookies(context)

            for page_num in range(1, max_pages + 1):
                url = f"{self.SEARCH_URL}/{keyword}?type=general&page={page_num}"
                logger.debug("[douyin] Page {}/{}: {}", page_num, max_pages, url)

                await page.goto(url, wait_until="networkidle")
                await page.wait_for_timeout(3000)
                await self._scroll_page(page, times=3, delay_ms=2500)

                cards = await page.query_selector_all(
                    "[class*='product-card'], [class*='goods-item'], [class*='card-item']"
                )
                logger.info("[douyin] Page {}: found {} cards", page_num, len(cards))

                for card in cards:
                    product = await self._parse_product(card)
                    if product:
                        products.append(product)

            await self.save_cookies(context)

        finally:
            await context.close()

        return products

    # ── Parse ─────────────────────────────────────────────────

    async def _parse_product(self, element) -> RawProduct | None:
        """Parse a single Douyin product card element."""
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
                "[class*='shop'], [class*='store'], [class*='seller']"
            )
            if shop_el:
                shop = (await shop_el.inner_text()).strip()

            # Sales
            sales = 0
            sales_el = await element.query_selector(
                "[class*='sales'], [class*='sold'], [class*='buy']"
            )
            if sales_el:
                sales_text = await sales_el.inner_text()
                sales = self.parse_count(sales_text)

            # Viewers
            viewers = 0
            view_el = await element.query_selector(
                "[class*='view'], [class*='watch'], [class*='look']"
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
            logger.warning("[douyin] Failed to parse product card: {}", e)
            return None

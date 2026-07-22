"""Xiaohongshu (小红书) product crawler — production-grade.

Enhanced with multi-page collection, sort modes, and extended field parsing.
"""

from loguru import logger

from app.config.crawler import crawler_settings
from app.crawler.base import BaseCrawler
from app.crawler.browser import random_delay, random_scroll, mouse_move
from app.crawler.models.schemas import RawProduct

# 排序参数映射
SORT_PARAMS = {
    "general": "general",
    "sales": "sales",
    "latest": "time",
}


class XiaohongshuCrawler(BaseCrawler):
    """Crawl product data from Xiaohongshu (小红书).

    Supports:
    - Multi-page collection via page_limit
    - Sort modes: general (综合), sales (销量), latest (最新)
    - Extended fields: favorites, comments, publish_time
    """

    PLATFORM = "xiaohongshu"
    BASE_URL = "https://www.xiaohongshu.com"
    SEARCH_URL = "https://www.xiaohongshu.com/search_result"

    # ── Login ─────────────────────────────────────────────────

    async def login(self) -> bool:
        """Manual login flow with cookie persistence."""
        if self.has_cookies():
            logger.info("[xiaohongshu] Existing cookies found, skipping login")
            return True
        return await super().login()

    # ── Login detection ────────────────────────────────────────

    async def check_login(self) -> bool:
        """检测小红书登录状态。

        启动浏览器 → 加载 Cookie → 访问首页 → 判断登录元素。
        返回 True 已登录, False 未登录。
        """
        if not self.has_cookies():
            logger.info("[xiaohongshu] login required")
            return False

        context = None
        try:
            context = await self._new_context()
            await self.load_cookies(context)
            page = await context.new_page()
            timeout = self._settings.login_check_timeout * 1000
            await page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=timeout)

            # 先检查是否已登录（用户头像/个人中心存在）
            user_el = await page.query_selector(
                "[class*='user'], [class*='avatar'], [class*='sidebar']"
            )
            if user_el:
                # 已登录，尝试关闭可能弹出的登录推荐框
                close_btn = await page.query_selector(
                    ".login-modal [class*='close'], "
                    ".reds-modal [class*='close'], "
                    "[class*='modal'] [class*='close']"
                )
                if close_btn:
                    try:
                        await close_btn.click()
                        logger.info("[xiaohongshu] Closed login popup overlay")
                    except Exception:
                        pass
                logger.info("[xiaohongshu] login success")
                return True

            # 未找到用户元素，再检查登录弹窗
            login_el = await page.query_selector(
                "[class*='login'], [class*='signin'], [class*='qrcode']"
            )
            if login_el:
                logger.info("[xiaohongshu] login required")
                return False

            logger.info("[xiaohongshu] login required")
            return False

        except Exception as e:
            logger.warning("[xiaohongshu] login check failed: {}", e)
            return False
        finally:
            if context:
                await context.close()

    # ── Crawl ─────────────────────────────────────────────────

    async def crawl(
        self,
        keyword: str,
        max_pages: int = 3,
        limit: int = 100,
        *,
        crawl_sort: str = "general",
    ) -> list[RawProduct]:
        """采集入口 — 支持 limit、排序、自动重试。

        Args:
            keyword: 搜索关键词.
            max_pages: 最多翻页数.
            limit: 最多采集商品数量, 默认 100.
            crawl_sort: 排序方式 "general"/"sales"/"latest".
        """
        from datetime import datetime

        start = datetime.now()
        logger.info(
            "{}:\nkeyword={}\npages={}\nlimit={}\nsort={}",
            self.PLATFORM,
            keyword,
            max_pages,
            limit,
            crawl_sort,
        )

        try:
            products = await self._with_retry(
                self._do_crawl,
                keyword=keyword,
                max_pages=max_pages,
                limit=limit,
                crawl_sort=crawl_sort,
            )
        except Exception as e:
            logger.error("[{}] Crawl failed after all retries: {}", self.PLATFORM, e)
            products = []

        elapsed = (datetime.now() - start).total_seconds()
        logger.info(
            "{}:\nkeyword={}\nsuccess={}\n耗时={:.1f}s",
            self.PLATFORM,
            keyword,
            len(products),
            elapsed,
        )
        return products

    async def _do_crawl(
        self,
        keyword: str,
        max_pages: int = 3,
        limit: int = 100,
        crawl_sort: str = "general",
    ) -> list[RawProduct]:
        """Search Xiaohongshu for *keyword* and scrape product cards.

        Args:
            keyword: 搜索关键词.
            max_pages: 最多翻页数.
            limit: 最多采集商品数量, 默认 100.
            crawl_sort: 排序方式.
        """
        if not await self.check_login():
            logger.warning("[xiaohongshu] 未登录, 停止采集")
            return []

        products: list[RawProduct] = []
        sort_param = SORT_PARAMS.get(crawl_sort, "general")

        context = await self._new_context()
        try:
            page = await context.new_page()
            await self.load_cookies(context)

            for page_num in range(1, max_pages + 1):
                url = (
                    f"{self.SEARCH_URL}?keyword={keyword}"
                    f"&source=web_search_result_notes"
                    f"&page={page_num}"
                    f"&sort={sort_param}"
                )
                logger.debug("[xiaohongshu] Page {}/{}: {}", page_num, max_pages, url)

                # 使用 safe_goto 支持页面异常恢复
                page = await self._browser_manager.safe_goto(
                    page, url, platform=self.PLATFORM
                )
                await page.wait_for_timeout(crawler_settings.post_goto_wait_ms)

                # 行为模拟：随机滚动 + 鼠标移动
                await random_scroll(page, times=2)
                await mouse_move(page)
                await random_delay(500, 1500)

                cards = await page.query_selector_all(
                    "[class*='note-item'], [class*='goods-card']"
                )
                logger.info("[xiaohongshu] Page {}: found {} cards", page_num, len(cards))

                for card in cards:
                    if len(products) >= limit:
                        logger.info("[xiaohongshu] reached limit {}, stop", limit)
                        break
                    product = await self._parse_product(card)
                    if product:
                        products.append(product)

                if len(products) >= limit:
                    break

            await self.save_cookies(context)

        finally:
            await context.close()

        return products

    # ── Parse ─────────────────────────────────────────────────

    async def _parse_product(self, element) -> RawProduct | None:
        """Parse a single Xiaohongshu product card element.

        Extracts: name, price, image, shop, viewers, sales, url,
        favorites, comments, publish_time.
        """
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

            # Sales
            sales = 0
            sales_el = await element.query_selector(
                "[class*='sales'], [class*='sold'], [class*='buy']"
            )
            if sales_el:
                sales_text = await sales_el.inner_text()
                sales = self.parse_count(sales_text)

            # Favorites / 收藏
            favorites = 0
            fav_el = await element.query_selector(
                "[class*='collect'], [class*='favorite'], [class*='fav']"
            )
            if fav_el:
                fav_text = await fav_el.inner_text()
                favorites = self.parse_count(fav_text)

            # Comments / 评论
            comments = 0
            comment_el = await element.query_selector(
                "[class*='comment'], [class*='reply']"
            )
            if comment_el:
                comment_text = await comment_el.inner_text()
                comments = self.parse_count(comment_text)

            # Publish time / 发布时间
            publish_time = None
            time_el = await element.query_selector(
                "[class*='time'], [class*='date'], [class*='publish']"
            )
            if time_el:
                publish_time = (await time_el.inner_text()).strip() or None

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
                sales_24h=sales,
                url=url,
                favorites=favorites,
                comments=comments,
                publish_time=publish_time,
            )

        except Exception as e:
            logger.warning("[xiaohongshu] Failed to parse product card: {}", e)
            return None

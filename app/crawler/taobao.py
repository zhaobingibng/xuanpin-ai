"""Taobao (淘宝) product crawler — production-grade.

Supports:
- Multi-page keyword search
- Shop-specific product crawling (for registered shops)
- Cookie persistence via BrowserManager
- Storage state persistence (cookies + localStorage + sessionStorage)
- Login detection & manual login flow
- Anti-bot risk mitigation (random delays, scroll, mouse movement)
- Per-page timeout retry
- Failure reason recording
- Crawl metrics (real_product_count, fallback_count, failure_reason)
"""

from __future__ import annotations

import asyncio
import json
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from app.crawler.auth_manager import AuthManager, AuthState, LoginStatus
from app.crawler.base import BaseCrawler
from app.crawler.browser import BrowserManager, random_delay, random_scroll, mouse_move
from app.crawler.models.schemas import RawProduct
from app.config.settings import get_settings


@dataclass
class CrawlResult:
    """采集结果，包含产品和指标数据。

    Attributes:
        products: 采集到的商品列表。
        real_product_count: 真实采集的商品数。
        fallback_count: 降级到 Mock 的商品数。
        failure_reason: 失败原因（空字符串表示成功）。
        pages_crawled: 实际采集页数。
        elapsed_seconds: 采集耗时（秒）。
        is_logged_in: 采集时登录状态。
    """
    products: list[RawProduct] = field(default_factory=list)
    real_product_count: int = 0
    fallback_count: int = 0
    failure_reason: str = ""
    pages_crawled: int = 0
    elapsed_seconds: float = 0.0
    is_logged_in: bool = False

    def to_dict(self) -> dict[str, Any]:
        """转为字典格式。"""
        return {
            "real_product_count": self.real_product_count,
            "fallback_count": self.fallback_count,
            "failure_reason": self.failure_reason,
            "pages_crawled": self.pages_crawled,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "is_logged_in": self.is_logged_in,
            "total": len(self.products),
        }


class TaobaoCrawler(BaseCrawler):
    """Taobao search & shop product crawler — production-grade.

    Supports:
    - Multi-page keyword search via ``crawl()``
    - Shop-specific crawling via ``crawl_shop()``
    - Cookie + storage_state persistence
    - Login detection
    - Per-page timeout retry
    - Failure reason recording
    - Crawl metrics via ``crawl_with_metrics()``
    """

    PLATFORM = "taobao"
    BASE_URL = "https://www.taobao.com"
    SEARCH_URL = "https://s.taobao.com/search"

    # ── Storage state persistence ─────────────────────────────

    def _storage_state_path(self) -> Path:
        """Path to the storage state JSON file."""
        return Path(self._settings.cookie_dir) / "taobao_storage_state.json"

    async def save_storage_state(self, context: Any) -> None:
        """Save full browser storage state (cookies + localStorage + sessionStorage)."""
        try:
            state = await context.storage_state()
            path = self._storage_state_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("[taobao] Storage state saved -> {}", path)
        except Exception as e:
            logger.warning("[taobao] Failed to save storage state: {}", e)

    async def load_storage_state(self, context: Any) -> bool:
        """Load storage state into context. Returns True if loaded."""
        path = self._storage_state_path()
        if not path.exists():
            return False
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            # Load cookies from storage state
            cookies = state.get("cookies", [])
            if cookies:
                await context.add_cookies(cookies)
                logger.info("[taobao] Storage state loaded ({} cookies)", len(cookies))
                return True
        except Exception as e:
            logger.warning("[taobao] Failed to load storage state: {}", e)
        return False

    # ── Auth Manager ──────────────────────────────────────────

    @property
    def auth_manager(self) -> AuthManager:
        """Lazy-initialized AuthManager instance."""
        if not hasattr(self, "_auth_manager"):
            self._auth_manager = AuthManager(self._settings.cookie_dir)
        return self._auth_manager

    async def pre_crawl_auth_check(self) -> AuthState:
        """Pre-crawl authentication check.

        Returns:
            AuthState with status:
            - ACTIVE: Login confirmed, proceed with crawl
            - EXPIRED: Login expired, stop and prompt re-login
            - UNKNOWN: Cannot determine, proceed with caution

        Usage:
            state = await crawler.pre_crawl_auth_check()
            if state.is_expired:
                raise RuntimeError("Login expired, please re-login")
            # proceed with crawl
        """
        state = await self.auth_manager.check_login_state(
            platform=self.PLATFORM,
            browser_manager=self._browser_manager,
        )
        logger.info(
            "[taobao] Pre-crawl auth check: status={}, user={}, detail={}",
            state.status.value,
            state.username,
            state.detail,
        )
        return state

    # ── Login ─────────────────────────────────────────────────

    async def login(self) -> bool:
        """Manual login flow with cookie persistence."""
        if self.has_cookies():
            logger.info("[taobao] Existing cookies found, skipping login")
            return True
        return await super().login()

    # ── Login detection ────────────────────────────────────────

    async def check_login(self) -> bool:
        """Check if Taobao session is logged in via persistent profile."""
        if not self.has_cookies():
            logger.info("[taobao] no cookies, login required")
            return False

        context = None
        try:
            context = await self._new_context()
            await self.load_cookies(context)
            page = await context.new_page()
            timeout = self._settings.login_check_timeout * 1000
            await page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=timeout)
            await page.wait_for_timeout(2000)

            # Check for login indicators (logged-in state)
            login_selectors = [
                ".site-nav-user .site-nav-user-hd",
                "[class*='nick']",
                ".member-nick",
                "a[href*='member.taobao.com']",
                ".J_SiteNavLogin .site-nav-menu-hd",
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

    # ── Crawl (keyword search) ────────────────────────────────

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

    async def crawl_with_metrics(
        self,
        keyword: str,
        max_pages: int = 3,
        limit: int = 100,
        *,
        crawl_sort: str = "general",
    ) -> CrawlResult:
        """采集并返回详细指标。

        与 crawl() 相同逻辑，但返回 CrawlResult 包含:
        - real_product_count: 真实采集数
        - failure_reason: 失败原因
        - pages_crawled: 实际页数
        - is_logged_in: 登录状态
        """
        start = datetime.now()
        result = CrawlResult()

        try:
            # Check login state
            result.is_logged_in = await self.check_login()
            if not result.is_logged_in:
                result.failure_reason = "not_logged_in"
                logger.warning("[taobao] 未登录, 无法采集")
                return result

            products = await self._with_retry(
                self._do_crawl,
                keyword=keyword,
                max_pages=max_pages,
                limit=limit,
                crawl_sort=crawl_sort,
            )

            result.products = products
            result.real_product_count = len(products)
            result.pages_crawled = getattr(self, "_last_pages_crawled", 0)

            if not products:
                result.failure_reason = "no_products_found"

        except Exception as e:
            result.failure_reason = f"crawl_error: {e}"
            logger.error("[taobao] Crawl with metrics failed: {}", e)

        result.elapsed_seconds = (datetime.now() - start).total_seconds()
        logger.info(
            "[taobao] crawl_with_metrics: real={}, pages={}, reason='{}', time={:.1f}s",
            result.real_product_count,
            result.pages_crawled,
            result.failure_reason,
            result.elapsed_seconds,
        )
        return result

    async def _do_crawl(
        self,
        keyword: str,
        max_pages: int = 3,
        limit: int = 100,
        crawl_sort: str = "general",
    ) -> list[RawProduct]:
        """Search Taobao for *keyword* and scrape product cards."""
        if not await self.check_login():
            logger.warning("[taobao] 未登录, 停止采集")
            return []

        products: list[RawProduct] = []
        sort_param = self._sort_params.get(crawl_sort, "")
        pages_crawled = 0

        context = await self._new_context()
        try:
            page = await context.new_page()
            await self.load_cookies(context)
            await self.load_storage_state(context)

            for page_num in range(1, max_pages + 1):
                # Taobao pagination: &s=offset (offset = (page-1) * 44)
                offset = (page_num - 1) * 44
                url = f"{self.SEARCH_URL}?q={keyword}"
                if sort_param:
                    url += f"&sort={sort_param}"
                if page_num > 1:
                    url += f"&s={offset}"

                logger.debug("[taobao] Page {}/{}: {}", page_num, max_pages, url)

                # Per-page retry with longer timeout
                page_loaded = False
                for attempt in range(1, 4):  # max 3 attempts per page
                    try:
                        page = await self._browser_manager.safe_goto(
                            page, url, platform=self.PLATFORM,
                            timeout=self._settings.browser_timeout + 10000,
                        )
                        page_loaded = True
                        break
                    except Exception as e:
                        logger.warning(
                            "[taobao] Page {} attempt {} failed: {}",
                            page_num, attempt, e,
                        )
                        if attempt < 3:
                            await random_delay(2000, 5000)

                if not page_loaded:
                    logger.warning("[taobao] Page {} skipped after 3 attempts", page_num)
                    continue

                # Anti-bot: random wait + scroll + mouse movement
                await random_delay(2000, 5000)  # longer random wait
                await random_scroll(page, times=random.randint(2, 4))
                await mouse_move(page)
                await random_delay(1000, 3000)

                # Check for security redirect
                final_url = page.url
                if "sec.taobao" in final_url or "punish" in final_url:
                    logger.warning("[taobao] Anti-bot redirect detected on page {}", page_num)
                    break

                cards = await page.query_selector_all(self._card_selector)
                logger.info("[taobao] Page {}: found {} cards", page_num, len(cards))
                pages_crawled += 1

                for card in cards:
                    if len(products) >= limit:
                        logger.info("[taobao] reached limit {}, stop", limit)
                        break
                    product = await self._parse_product(card)
                    if product:
                        products.append(product)

                if len(products) >= limit:
                    break

                # Random delay between pages
                if page_num < max_pages:
                    delay_ms = random.randint(3000, 8000)
                    logger.debug("[taobao] Waiting {}ms before next page...", delay_ms)
                    await asyncio.sleep(delay_ms / 1000)

            # Save both cookies and storage state
            await self.save_cookies(context)
            await self.save_storage_state(context)

        finally:
            await context.close()

        self._last_pages_crawled = pages_crawled
        return products

    # ── Shop crawl ─────────────────────────────────────────────

    async def crawl_shop(
        self,
        shop_url: str,
        shop_name: str = "",
        max_pages: int = 3,
        limit: int = 50,
    ) -> list[RawProduct]:
        """Crawl products from a specific shop page.

        Args:
            shop_url: Shop URL (e.g. https://shop123.taobao.com or search URL).
            shop_name: Known shop name for tagging products.
            max_pages: Max pages to crawl.
            limit: Max products to return.
        """
        if not await self.check_login():
            logger.warning("[taobao] 未登录, 无法采集店铺: {}", shop_url)
            return []

        products: list[RawProduct] = []
        pages_crawled = 0

        context = await self._new_context()
        try:
            page = await context.new_page()
            await self.load_cookies(context)
            await self.load_storage_state(context)

            for page_num in range(1, max_pages + 1):
                # Build shop search URL with pagination
                if page_num == 1:
                    url = self._normalize_shop_url(shop_url)
                else:
                    base_url = self._normalize_shop_url(shop_url)
                    if "?" in base_url:
                        base_url = base_url.split("?")[0]
                    url = f"{base_url}?page={page_num}"

                logger.debug("[taobao] Shop page {}/{}: {}", page_num, max_pages, url)

                # Per-page retry
                page_loaded = False
                for attempt in range(1, 4):
                    try:
                        page = await self._browser_manager.safe_goto(
                            page, url, platform=self.PLATFORM,
                            timeout=self._settings.browser_timeout + 10000,
                        )
                        page_loaded = True
                        break
                    except Exception as e:
                        logger.warning(
                            "[taobao] Shop page {} attempt {} failed: {}",
                            page_num, attempt, e,
                        )
                        if attempt < 3:
                            await random_delay(2000, 5000)

                if not page_loaded:
                    logger.warning("[taobao] Shop page {} skipped after 3 attempts", page_num)
                    continue

                # Anti-bot
                await random_delay(2000, 4000)
                await random_scroll(page, times=random.randint(2, 4))
                await mouse_move(page)
                await random_delay(1000, 2500)

                # Check for security redirect
                final_url = page.url
                if "sec.taobao" in final_url or "punish" in final_url:
                    logger.warning("[taobao] Anti-bot redirect on shop page {}", page_num)
                    break

                # Shop page card selectors (Taobao + Tmall)
                shop_card_selectors = [
                    # Tmall category page selectors
                    "[class*='CategoryItem']",
                    ".category-item",
                    "a[href*='detail.tmall.com']",
                    # Taobao shop page selectors
                    "[class*='Card--doubleCard']",
                    "[class*='item']",
                    ".J_TItems .item",
                    ".shop-hesper-bd .item",
                    "a[href*='item.taobao.com']",
                    # Generic product link selectors
                    "a[href*='detail']",
                ]

                cards = []
                for sel in shop_card_selectors:
                    cards = await page.query_selector_all(sel)
                    if cards:
                        break

                logger.info("[taobao] Shop page {}: found {} cards", page_num, len(cards))
                pages_crawled += 1

                for card in cards:
                    if len(products) >= limit:
                        break
                    product = await self._parse_product(card, shop_name_override=shop_name)
                    if product:
                        products.append(product)

                if len(products) >= limit:
                    break

                # Random delay between pages
                if page_num < max_pages:
                    await asyncio.sleep(random.randint(3000, 6000) / 1000)

            await self.save_cookies(context)
            await self.save_storage_state(context)

        finally:
            await context.close()

        self._last_pages_crawled = pages_crawled
        logger.info("[taobao] Shop crawl complete: {} products from {}", len(products), shop_url)
        return products

    async def crawl_shop_with_metrics(
        self,
        shop_url: str,
        shop_name: str = "",
        max_pages: int = 3,
        limit: int = 50,
    ) -> CrawlResult:
        """采集店铺并返回详细指标。

        Returns:
            CrawlResult with real_product_count, pages_crawled,
            failure_reason, is_logged_in, elapsed_seconds.
        """
        start = datetime.now()
        result = CrawlResult()

        try:
            result.is_logged_in = await self.check_login()
            if not result.is_logged_in:
                result.failure_reason = "not_logged_in"
                logger.warning("[taobao] 未登录, 无法采集店铺: {}", shop_url)
                return result

            products = await self.crawl_shop(
                shop_url=shop_url,
                shop_name=shop_name,
                max_pages=max_pages,
                limit=limit,
            )

            result.products = products
            result.real_product_count = len(products)
            result.pages_crawled = getattr(self, "_last_pages_crawled", 0)

            if not products:
                result.failure_reason = "no_products_found"

        except Exception as e:
            result.failure_reason = f"crawl_error: {e}"
            logger.error("[taobao] Shop crawl with metrics failed: {}", e)

        result.elapsed_seconds = (datetime.now() - start).total_seconds()
        logger.info(
            "[taobao] shop metrics: url={}, real={}, pages={}, reason='{}', time={:.1f}s",
            shop_url, result.real_product_count, result.pages_crawled,
            result.failure_reason, result.elapsed_seconds,
        )
        return result

    async def crawl_registered_shops(
        self,
        shop_repository: Any,
        max_pages: int = 2,
        limit: int = 30,
    ) -> dict[str, Any]:
        """Crawl all ACTIVE shops from the repository.

        Args:
            shop_repository: ShopRepository instance for fetching shops.
            max_pages: Max pages per shop.
            limit: Max products per shop.

        Returns:
            Dict with crawl results per shop.
        """
        # Get active shops from repository
        active_shops = await shop_repository.get_shops_for_crawl(platform=self.PLATFORM)

        if not active_shops:
            logger.info("[taobao] No active shops to crawl")
            return {"total_shops": 0, "results": []}

        logger.info("[taobao] Starting crawl for {} active shops", len(active_shops))

        results = []
        for shop in active_shops:
            shop_url = shop.shop_url or f"https://shop{shop.shop_id}.taobao.com"
            logger.info("[taobao] Crawling shop: {} ({})", shop.shop_name, shop_url)

            # Crawl the shop
            crawl_result = await self.crawl_shop_with_metrics(
                shop_url=shop_url,
                shop_name=shop.shop_name,
                max_pages=max_pages,
                limit=limit,
            )

            # Update shop crawl status in repository
            success = crawl_result.real_product_count > 0
            await shop_repository.update_crawl_status(
                shop_id=shop.id,
                success=success,
            )

            results.append({
                "shop_id": shop.id,
                "shop_name": shop.shop_name,
                "shop_url": shop_url,
                "products_count": crawl_result.real_product_count,
                "pages_crawled": crawl_result.pages_crawled,
                "success": success,
                "failure_reason": crawl_result.failure_reason,
            })

        total_products = sum(r["products_count"] for r in results)
        logger.info(
            "[taobao] Registered shops crawl complete: {} shops, {} products",
            len(results), total_products,
        )

        return {
            "total_shops": len(active_shops),
            "total_products": total_products,
            "results": results,
        }

    async def save_crawled_products(
        self,
        products: list[RawProduct],
        product_repository: Any,
    ) -> dict[str, Any]:
        """Save crawled products to database with new product detection.

        Flow: RawProduct -> ProductRepository.save_product -> DB

        Args:
            products: List of crawled RawProduct.
            product_repository: ProductRepository instance.

        Returns:
            Dict with save stats.
        """
        if not products:
            return {"total": 0, "new_count": 0, "updated_count": 0}

        new_count = 0
        updated_count = 0

        for raw in products:
            try:
                _, is_new = await product_repository.save_product(
                    name=raw.name,
                    platform=raw.platform,
                    shop=raw.shop,
                    url=raw.url,
                    image=raw.image,
                    price=raw.price,
                )
                if is_new:
                    new_count += 1
                else:
                    updated_count += 1
            except Exception as e:
                logger.warning("[taobao] Failed to save product {}: {}", raw.name[:30], e)

        await product_repository._session.commit()

        logger.info(
            "[taobao] Products saved: total={}, new={}, updated={}",
            len(products), new_count, updated_count,
        )

        return {
            "total": len(products),
            "new_count": new_count,
            "updated_count": updated_count,
        }

    async def score_new_products(
        self,
        product_repository: Any,
        scoring_service: Any,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Score new products (lifecycle_stage='NEW').

        Flow: find_new_products -> calculate_score -> save ProductScore

        Args:
            product_repository: ProductRepository instance.
            scoring_service: ProductScoringService instance.
            limit: Max products to score.

        Returns:
            Dict with scoring stats.
        """
        from app.models.product_score import ProductScore

        new_products = await product_repository.find_new_products(limit=limit)

        if not new_products:
            return {"total": 0, "scored_count": 0}

        scored_count = 0
        score_records = []

        for product in new_products:
            try:
                score_record = scoring_service.create_score_record(product)
                score_records.append(score_record)
                scored_count += 1
            except Exception as e:
                logger.warning("[taobao] Failed to score product {}: {}", product.name[:30], e)

        # Save score records
        if score_records:
            product_repository._session.add_all(score_records)
            await product_repository._session.commit()

        logger.info(
            "[taobao] New products scored: total={}, scored={}",
            len(new_products), scored_count,
        )

        return {
            "total": len(new_products),
            "scored_count": scored_count,
        }

    async def match_new_products_with_suppliers(
        self,
        product_repository: Any,
        matching_service: Any,
        alibaba_client: Any,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Match new products with 1688 suppliers.

        Flow: find_new_products -> search 1688 -> match -> save SupplierMatch

        Args:
            product_repository: ProductRepository instance.
            matching_service: SupplierMatchingService instance.
            alibaba_client: AlibabaSearchClient instance.
            limit: Max products to match.

        Returns:
            Dict with matching stats.
        """
        from app.models.supplier_match import SupplierMatch

        new_products = await product_repository.find_new_products(limit=limit)

        if not new_products:
            return {"total": 0, "matched_count": 0}

        matched_count = 0
        match_records = []

        for product in new_products:
            try:
                # Step 1: Clean title and generate search keyword
                cleaned_title = matching_service.clean_title(product.name)
                search_keyword = matching_service.generate_search_keyword(cleaned_title)

                if not search_keyword:
                    continue

                # Step 2: Search 1688 for suppliers
                supplier_products = await alibaba_client.search_products(
                    keyword=search_keyword,
                    limit=10,
                )

                if not supplier_products:
                    continue

                # Step 3: Match product with suppliers
                match_data = matching_service.match_product(product, supplier_products)

                if match_data:
                    match_record = matching_service.create_match_record(product, match_data)
                    match_records.append(match_record)
                    matched_count += 1

            except Exception as e:
                logger.warning("[taobao] Failed to match product {}: {}", product.name[:30], e)

        # Save match records
        if match_records:
            product_repository._session.add_all(match_records)
            await product_repository._session.commit()

        logger.info(
            "[taobao] New products matched: total={}, matched={}",
            len(new_products), matched_count,
        )

        return {
            "total": len(new_products),
            "matched_count": matched_count,
        }

    async def calculate_opportunity_scores(
        self,
        product_repository: Any,
        opportunity_service: Any,
        product_score_repository: Any = None,
        supplier_match_repository: Any = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Calculate opportunity scores for new products.

        Flow: find_new_products -> get ProductScore -> get SupplierMatch -> calculate -> save

        Args:
            product_repository: ProductRepository instance.
            opportunity_service: OpportunityScoringService instance.
            product_score_repository: Repository for ProductScore (optional).
            supplier_match_repository: Repository for SupplierMatch (optional).
            limit: Max products to score.

        Returns:
            Dict with scoring stats.
        """
        from app.models.opportunity_score import OpportunityScore

        new_products = await product_repository.find_new_products(limit=limit)

        if not new_products:
            return {"total": 0, "scored_count": 0}

        scored_count = 0
        score_records = []

        for product in new_products:
            try:
                # Get ProductScore if available
                product_score = None
                if product_score_repository:
                    product_score = await product_score_repository.get_by_product_id(product.id)

                # Get SupplierMatch if available
                supplier_match = None
                supplier_count = 0
                if supplier_match_repository:
                    supplier_match = await supplier_match_repository.get_by_product_id(product.id)
                    supplier_count = await supplier_match_repository.count_by_product_id(product.id)

                # Calculate opportunity score
                score_record = opportunity_service.create_score_record(
                    product=product,
                    product_score=product_score,
                    supplier_match=supplier_match,
                    supplier_count=supplier_count,
                )
                score_records.append(score_record)
                scored_count += 1

            except Exception as e:
                logger.warning("[taobao] Failed to score opportunity for {}: {}", product.name[:30], e)

        # Save score records
        if score_records:
            product_repository._session.add_all(score_records)
            await product_repository._session.commit()

        logger.info(
            "[taobao] Opportunity scores calculated: total={}, scored={}",
            len(new_products), scored_count,
        )

        return {
            "total": len(new_products),
            "scored_count": scored_count,
        }

    @staticmethod
    def _normalize_shop_url(shop_url: str) -> str:
        """Normalize shop URL to 'all items' page.

        Supports:
        - https://shop123.taobao.com -> /search.htm
        - https://shop123.taobao.com/search.htm -> as-is
        - https://sanzhisongshu.tmall.com -> /category.htm
        - https://sanzhisongshu.tmall.com/shop/view_shop.htm -> /category.htm
        - Full search URLs with query params -> as-is
        """
        from urllib.parse import urlparse

        url = shop_url.strip()
        if not url.startswith("http"):
            url = "https://" + url

        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"

        # If already a search/items/category page, keep as-is
        if "/search.htm" in url or "/category.htm" in url or "?" in url:
            return url

        # Tmall shop: extract domain and use /category.htm
        if "tmall.com" in parsed.netloc:
            return domain + "/category.htm"

        # Taobao shop: extract domain and use /search.htm
        if "taobao.com" in parsed.netloc:
            return domain + "/search.htm"

        return url

    # ── Parse ─────────────────────────────────────────────────

    async def _parse_product(
        self, element, shop_name_override: str = ""
    ) -> RawProduct | None:
        """Parse a single Taobao/Tmall product card."""
        try:
            # Detect if element is a bare <a> link (common on Tmall category pages)
            tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
            is_bare_link = tag_name == "a"

            # Title
            name = ""
            if is_bare_link:
                # For bare links, use title attribute or text content
                name = (await element.get_attribute("title")) or ""
                if not name:
                    name = (await element.inner_text()).strip()
            else:
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
            shop = shop_name_override or ""
            shop_url = None
            if not shop:
                for sel in [
                    "[class*='Shop--shopName']",
                    "[class*='shop']",
                    "[class*='store']",
                ]:
                    el = await element.query_selector(sel)
                    if el:
                        shop = (await el.inner_text()).strip()
                        # Try to extract shop URL from link
                        shop_link = await el.query_selector("a[href*='shop']")
                        if shop_link:
                            shop_url = await shop_link.get_attribute("href")
                        if shop:
                            break

            # If no shop_url found yet, try from shop link directly
            if not shop_url:
                shop_link_el = await element.query_selector(
                    "a[href*='shop.taobao.com'], a[href*='shop*.taobao.com']"
                )
                if shop_link_el:
                    shop_url = await shop_link_el.get_attribute("href")

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
            if is_bare_link:
                # For bare links, the href is the product URL
                url = await element.get_attribute("href")
            else:
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
                shop_url=shop_url,
            )

        except Exception as e:
            logger.warning("[taobao] parse error: {}", e)
            return None

    # ── Class-level config ─────────────────────────────────────

    _card_selector = "[class*='Card--doubleCard'], [class*='contentInner'] > div > div, .search-content-col"

    _sort_params = {
        "general": "",
        "sales": "sale",
        "latest": "renqi-desc",
        "price_asc": "price-asc",
        "price_desc": "price-desc",
    }

    # ── Shop extraction from crawl results ────────────────────

    @staticmethod
    def extract_shops_from_results(
        products: list[RawProduct],
    ) -> list[dict[str, str]]:
        """Extract unique shops from crawl results.

        Returns:
            List of dicts with keys: shop_name, shop_url, platform.
        """
        seen: dict[str, dict[str, str]] = {}
        for prod in products:
            if not prod.shop or prod.shop == "未知店铺":
                continue
            key = prod.shop
            if key not in seen:
                seen[key] = {
                    "shop_name": prod.shop,
                    "shop_url": prod.shop_url or "",
                    "platform": prod.platform,
                }
            elif prod.shop_url and not seen[key]["shop_url"]:
                seen[key]["shop_url"] = prod.shop_url
        return list(seen.values())


# ── Verification script (kept for manual testing) ────────────


async def _dump_page_structure(page) -> dict:
    """Dump key DOM elements for Taobao page analysis."""
    info: dict = {}
    info["title"] = await page.title()
    info["url"] = page.url

    structure = await page.evaluate("""
        () => {
            const result = [];
            const containers = document.querySelectorAll(
                '#root, #app, #content, .search-content, [class*="Content"], [class*="content"]'
            );
            containers.forEach(el => {
                result.push({
                    tag: el.tagName,
                    id: el.id,
                    className: (el.className || '').toString().substring(0, 120),
                    childCount: el.children.length,
                });
            });
            const itemLinks = document.querySelectorAll(
                'a[href*="item.taobao"], a[href*="detail.tmall"], a[href*="detail.taobao"]'
            );
            result.push({ tag: 'STATS', itemLinks: itemLinks.length });
            return result;
        }
    """)
    info["structure"] = structure
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
        # Step 1: Open homepage
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

        # Step 2: Check login
        print("\n[Step 2] Checking login state...")
        login_ok = await crawler.check_login()
        print(f"  Logged in: {login_ok}")
        report["steps"].append({"action": "check_login", "logged_in": login_ok})

        # Step 3: Search
        print("\n[Step 3] Navigating to search...")
        search_url = f"{crawler.SEARCH_URL}?q=蓝牙耳机"
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)
            final_url = page.url
            print(f"  Final URL: {final_url[:120]}")
            step3 = {"action": "search", "success": "login" not in final_url.lower(), "url": final_url[:150]}
        except Exception as e:
            step3 = {"action": "search", "success": False, "error": str(e)}
            print(f"  FAILED: {e}")
        report["steps"].append(step3)

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

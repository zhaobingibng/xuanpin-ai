"""Alibaba 1688 supplier search crawler — production-grade.

Searches 1688.com for supplier products to enable supply chain matching.
Uses the same Playwright-based browser infrastructure as other crawlers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from loguru import logger

from app.config.crawler import crawler_settings
from app.crawler.base import BaseCrawler
from app.crawler.browser import random_delay, random_scroll, mouse_move
from app.crawler.models.schemas import RawProduct


@dataclass
class SupplierProduct:
    """1688 supplier product — used by SupplyChainProvider."""

    product_id: str
    title: str
    price: float
    min_order: int = 1
    supplier_name: str = ""
    supplier_location: str = ""
    monthly_sales: int = 0
    image_url: str | None = None
    url: str | None = None

    def to_raw_product(self) -> RawProduct:
        """Convert to RawProduct for unified processing."""
        return RawProduct(
            name=self.title,
            platform="1688",
            shop=self.supplier_name or "未知供应商",
            price=self.price,
            image=self.image_url,
            url=self.url,
        )


class Alibaba1688Crawler(BaseCrawler):
    """1688.com supplier search crawler.

    Searches 1688 for wholesale/supplier products.
    Returns SupplierProduct instances for supply chain matching.
    """

    PLATFORM = "1688"
    BASE_URL = "https://www.1688.com"
    SEARCH_URL = "https://s.1688.com/selloffer/offer_search.htm"

    # ── Storage state persistence ─────────────────────────────

    def _storage_state_path(self) -> Path:
        """Path to the storage state JSON file."""
        # Check new state file path first
        new_path = Path("storage/alibaba_state.json")
        if new_path.exists() and new_path.stat().st_size > 0:
            return new_path
        # Fall back to cookie_dir
        return Path(self._settings.cookie_dir) / "alibaba_storage_state.json"

    async def load_storage_state(self, context) -> bool:
        """Load storage state into context. Returns True if loaded."""
        path = self._storage_state_path()
        if not path.exists():
            return False
        try:
            # Try multiple encodings for compatibility
            state = None
            for encoding in ["utf-8", "gbk", "gb2312", "latin-1"]:
                try:
                    with open(path, "r", encoding=encoding) as f:
                        state = json.load(f)
                    if encoding != "utf-8":
                        logger.warning("[1688] State file was {} encoded, not utf-8", encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if state is None:
                logger.warning("[1688] Could not decode state file with any encoding")
                return False
            
            # Load cookies from storage state
            cookies = state.get("cookies", [])
            if cookies:
                await context.add_cookies(cookies)
                logger.info("[1688] Storage state loaded ({} cookies) from {}", len(cookies), path)
                return True
        except Exception as e:
            logger.warning("[1688] Failed to load storage state: {}", e)
        return False

    # ── Login ─────────────────────────────────────────────────

    async def login(self) -> bool:
        """Manual login flow with cookie persistence."""
        if self.has_cookies():
            logger.info("[1688] Existing cookies found, skipping login")
            return True
        return await super().login()

    # ── Login detection ────────────────────────────────────────

    async def check_login(self) -> bool:
        """Check if 1688 session is logged in."""
        # Check if storage state file exists (new login flow)
        if self._storage_state_path().exists():
            logger.info("[1688] Storage state file found, assuming logged in")
            return True
        
        if not self.has_cookies():
            logger.info("[1688] no cookies, login required")
            return False

        context = None
        try:
            context = await self._new_context()
            await self.load_cookies(context)
            page = await context.new_page()
            timeout = self._settings.login_check_timeout * 1000
            await page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=timeout)
            await page.wait_for_timeout(crawler_settings.post_goto_wait_ms)

            # Check for login indicators
            login_selectors = [
                "[class*='user-name']",
                "[class*='member']",
                "[class*='nickname']",
                "a[href*='login.1688.com']",
            ]
            for sel in login_selectors:
                el = await page.query_selector(sel)
                if el:
                    text = (await el.inner_text()).strip()
                    if text and "登录" not in text:
                        return True

            # Check for explicit login prompt
            login_prompt = await page.query_selector("a[href*='login']")
            if login_prompt:
                text = (await login_prompt.inner_text()).strip()
                if "登录" in text:
                    return False

            return False

        except Exception as e:
            logger.warning("[1688] login check failed: {}", e)
            return False
        finally:
            if context:
                await context.close()

    # ── Search ────────────────────────────────────────────────

    async def search_suppliers(
        self,
        keyword: str,
        max_pages: int = 2,
        limit: int = 20,
    ) -> list[SupplierProduct]:
        """Search 1688 for supplier products matching keyword.

        Args:
            keyword: Search keyword (e.g. product name).
            max_pages: Max pages to search.
            limit: Max results to return.

        Returns:
            List of SupplierProduct.
        """
        if not await self.check_login():
            logger.warning("[1688] 未登录, 降级到 Mock 数据")
            return []

        results: list[SupplierProduct] = []
        api_results: list[SupplierProduct] = []  # Network API捕获的结果
        js_results: list[SupplierProduct] = []  # JS变量读取的结果
        event_results: list[SupplierProduct] = []  # Event捕获的结果

        context = await self._new_context()
        try:
            page = await context.new_page()
            await self.load_cookies(context)
            await self.load_storage_state(context)

            # 设置 API 响应监听器 (network)
            async def handle_response(response):
                """捕获 getOfferList API 响应"""
                url = response.url
                if "getOfferList" in url or "offerV2" in url:
                    try:
                        body = await response.text()
                        if body:
                            data = json.loads(body)
                            logger.info("[1688 API] FOUND: {}", url[:100])
                            parsed = self._parse_api_response(data)
                            if parsed:
                                api_results.extend(parsed)
                                logger.info("[1688 API] PRODUCTS COUNT: {}", len(parsed))
                    except Exception as e:
                        logger.debug("[1688 API] Parse error: {}", e)

            page.on("response", handle_response)

            # 注入事件监听器脚本（在页面加载前执行）
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
            """
            await page.add_init_script(event_capture_script)

            for page_num in range(1, max_pages + 1):
                url = f"{self.SEARCH_URL}?keywords={keyword}"
                if page_num > 1:
                    url += f"&beginPage={page_num}"

                logger.debug("[1688] Search page {}/{}: {}", page_num, max_pages, url)

                page = await self._browser_manager.safe_goto(
                    page, url, platform=self.PLATFORM
                )
                await page.wait_for_timeout(crawler_settings.post_search_wait_ms)
                await random_scroll(page, times=2)
                await mouse_move(page)
                await random_delay(800, 1500)

                # Check for anti-bot
                if "sec.1688" in page.url or "punish" in page.url:
                    logger.warning("[1688] Anti-bot redirect on page {}", page_num)
                    break

                # 优先级1: 从捕获的事件中提取数据
                event_products = await self._extract_event_data(page)
                if event_products:
                    logger.info("[1688 EVENT] FOUND: {} products", len(event_products))
                    event_results.extend(event_products)

                # 优先级2: 从页面 JS 变量读取数据
                if not event_results:
                    js_products = await self._extract_page_data(page)
                    if js_products:
                        logger.info("[1688 JS] FOUND: {} products", len(js_products))
                        js_results.extend(js_products)

                # 优先级3: 使用 Network API 响应结果
                if api_results:
                    logger.info("[1688] Using API data: {} products", len(api_results))
                    results = api_results[:limit]
                    break

                # 优先级4: 使用 Event 捕获数据
                if event_results:
                    logger.info("[1688] Using EVENT data: {} products", len(event_results))
                    results = event_results[:limit]
                    break

                # 优先级5: 使用 JS 变量数据
                if js_results:
                    logger.info("[1688] Using JS data: {} products", len(js_results))
                    results = js_results[:limit]
                    break

                # 优先级6: DOM selector 解析（兼容旧页面）
                cards = await page.query_selector_all(self._card_selector)
                logger.info("[1688] Page {}: found {} cards (DOM)", page_num, len(cards))

                for card in cards:
                    if len(results) >= limit:
                        break
                    product = await self._parse_supplier_product(card)
                    if product:
                        results.append(product)

                if len(results) >= limit:
                    break

            await self.save_cookies(context)

        finally:
            await context.close()

        logger.info("[1688] Search '{}' complete: {} results", keyword, len(results))
        return results

    # ── Event Data Extraction ─────────────────────────────────

    async def _extract_event_data(self, page) -> list[SupplierProduct]:
        """从捕获的事件中提取商品数据。
        
        1688 新版通过 postMessage 和 CustomEvent 传递商品数据。
        
        Args:
            page: Playwright page object
        
        Returns:
            SupplierProduct 列表
        """
        products: list[SupplierProduct] = []
        
        try:
            # 读取捕获的事件数据
            events = await page.evaluate("""
                () => {
                    return window.__1688_debug || [];
                }
            """)
            
            if not events:
                logger.debug("[1688 EVENT] No events captured")
                return products
            
            logger.debug("[1688 EVENT] Found {} events", len(events))
            
            for event in events:
                if not isinstance(event, dict):
                    continue
                
                event_type = event.get("type", "")
                logger.debug("[1688 EVENT] Processing: type={}, data_len={}", 
                           event_type, len(str(event)))
                
                # 处理 offerV2 自定义事件
                if event_type == "offerV2":
                    detail = event.get("detail", {})
                    if detail:
                        parsed = self._parse_api_response(detail)
                        if parsed:
                            products.extend(parsed)
                            logger.info("[1688 EVENT] Parsed {} products from offerV2 event", len(parsed))
                
                # 处理 postMessage 事件
                elif event_type == "message":
                    action = event.get("action", "")
                    data = event.get("data", {})
                    
                    if action == "getOfferList" and data:
                        # 构造与 _parse_api_response 兼容的格式
                        parsed = self._parse_api_response({"data": data})
                        if parsed:
                            products.extend(parsed)
                            logger.info("[1688 EVENT] Parsed {} products from message event", len(parsed))
            
        except Exception as e:
            logger.debug("[1688 EVENT] Extract error: {}", e)
        
        return products

    # ── Page Data Extraction (JS Variables) ───────────────────

    async def _extract_page_data(self, page) -> list[SupplierProduct]:
        """从页面 JS 变量提取商品数据。
        
        1688 新版使用 postMessage + window.data.offerV2 传递数据。
        
        Args:
            page: Playwright page object
        
        Returns:
            SupplierProduct 列表
        """
        products: list[SupplierProduct] = []
        
        try:
            # 等待数据加载（最多5秒）
            for _ in range(crawler_settings.scroll_loop_count):
                # 尝试读取 window.data.offerV2
                offer_data = await page.evaluate("""
                    () => {
                        // 方式1: window.data.offerV2.response
                        if (window.data && window.data.offerV2) {
                            return window.data.offerV2;
                        }
                        // 方式2: window.__INITIAL_STATE__
                        if (window.__INITIAL_STATE__) {
                            return window.__INITIAL_STATE__;
                        }
                        return null;
                    }
                """)
                
                if offer_data:
                    logger.debug("[1688 JS] Data found: {}", type(offer_data))
                    break
                
                await page.wait_for_timeout(crawler_settings.scroll_wait_ms)
            
            if not offer_data:
                logger.debug("[1688 JS] No data in window.data or __INITIAL_STATE__")
                return products
            
            # 解析 offerV2 结构
            if isinstance(offer_data, dict):
                # offerV2 结构: {reqParams, response, timeCost}
                response_data = offer_data.get("response", offer_data)
                
                # 尝试从 response 中提取 offerList
                offer_list = None
                if isinstance(response_data, dict):
                    # 结构1: response.data.offerList
                    inner = response_data.get("data", {})
                    if isinstance(inner, dict):
                        offer_list = inner.get("offerList", [])
                    
                    # 结构2: response.offerList
                    if not offer_list:
                        offer_list = response_data.get("offerList", [])
                    
                    # 结构3: response.data.offerV2
                    if not offer_list and isinstance(inner, dict):
                        offer_list = inner.get("offerV2", [])
                
                if offer_list:
                    products = self._parse_api_response({"data": {"offerList": offer_list}})
                    if products:
                        logger.info("[1688 JS] Parsed {} products from window.data", len(products))
            
        except Exception as e:
            logger.debug("[1688 JS] Extract error: {}", e)
        
        return products

    # ── API Response Parsing ──────────────────────────────────

    def _parse_api_response(self, data: dict) -> list[SupplierProduct]:
        """解析 getOfferList API 响应数据。
        
        Args:
            data: API 响应的 JSON 数据
        
        Returns:
            SupplierProduct 列表
        """
        import hashlib
        
        products: list[SupplierProduct] = []
        
        # 尝试多种可能的数据结构
        offer_list = None
        
        # 结构1: data.data.offerList
        if isinstance(data, dict):
            inner_data = data.get("data", {})
            if isinstance(inner_data, dict):
                offer_list = inner_data.get("offerList", [])
        
        # 结构2: data.offerList
        if not offer_list and isinstance(data, dict):
            offer_list = data.get("offerList", [])
        
        # 结构3: data.data.offerV2
        if not offer_list and isinstance(data, dict):
            inner_data = data.get("data", {})
            if isinstance(inner_data, dict):
                offer_list = inner_data.get("offerV2", [])
        
        if not offer_list:
            return products
        
        for item in offer_list:
            try:
                if not isinstance(item, dict):
                    continue
                
                # 提取字段（兼容多种字段名）
                offer = item.get("offer", item)
                
                title = (
                    offer.get("title") or 
                    offer.get("subject") or 
                    item.get("title") or 
                    ""
                )
                if not title:
                    continue
                
                # 价格
                price = 0.0
                price_info = offer.get("priceInfo") or offer.get("price") or {}
                if isinstance(price_info, dict):
                    price_str = (
                        price_info.get("price") or 
                        price_info.get("value") or 
                        "0"
                    )
                else:
                    price_str = str(price_info)
                
                # 清理价格字符串
                price_str = "".join(c for c in str(price_str) if c.isdigit() or c == ".")
                if price_str:
                    try:
                        price = float(price_str)
                    except ValueError:
                        price = 0.0
                
                # 供应商名称
                supplier = (
                    offer.get("companyName") or 
                    offer.get("supplierName") or 
                    item.get("companyName") or 
                    ""
                )
                
                # 最小起订量
                min_order = 1
                moq = offer.get("minOrderQuantity") or offer.get("moq") or 1
                try:
                    min_order = int(moq)
                except (ValueError, TypeError):
                    min_order = 1
                
                # 图片
                image = (
                    offer.get("image") or 
                    offer.get("imageUrl") or 
                    offer.get("picUrl") or 
                    None
                )
                
                # URL
                detail_url = offer.get("detailUrl") or offer.get("url")
                if detail_url and not detail_url.startswith("http"):
                    detail_url = "https://detail.1688.com" + detail_url
                
                # 产品ID
                offer_id = offer.get("offerId") or offer.get("id")
                if offer_id:
                    product_id = str(offer_id)
                else:
                    id_source = detail_url or title
                    product_id = hashlib.md5(id_source.encode()).hexdigest()[:12]
                
                products.append(SupplierProduct(
                    product_id=product_id,
                    title=title,
                    price=price,
                    min_order=min_order,
                    supplier_name=supplier,
                    image_url=image,
                    url=detail_url,
                ))
                
            except Exception as e:
                logger.debug("[1688 API] Item parse error: {}", e)
                continue
        
        return products

    # ── Parse ─────────────────────────────────────────────────

    async def _parse_supplier_product(self, element) -> SupplierProduct | None:
        """Parse a single 1688 supplier product card."""
        try:
            # Title
            title = ""
            for sel in [
                "[class*='title']",
                "[class*='name']",
                "a[title]",
                ".title",
            ]:
                el = await element.query_selector(sel)
                if el:
                    title = (await el.inner_text()).strip()
                    if not title:
                        title = (await el.get_attribute("title")) or ""
                    if title:
                        break
            if not title:
                return None

            # Price
            price = 0.0
            for sel in ["[class*='price']", ".price", "[class*='Price']"]:
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

            # Supplier name
            supplier = ""
            for sel in ["[class*='company']", "[class*='supplier']", "[class*='shop']"]:
                el = await element.query_selector(sel)
                if el:
                    supplier = (await el.inner_text()).strip()
                    if supplier:
                        break

            # Min order
            min_order = 1
            for sel in ["[class*='min-order']", "[class*='moq']", "[class*='quantity']"]:
                el = await element.query_selector(sel)
                if el:
                    text = await el.inner_text()
                    nums = "".join(c for c in text if c.isdigit())
                    if nums:
                        min_order = int(nums)
                    break

            # Image
            image = None
            img_el = await element.query_selector("img[src*='cbu01.alicdn'], img")
            if img_el:
                image = await img_el.get_attribute("src")

            # URL
            url = None
            link_el = await element.query_selector("a[href*='detail.1688'], a[href*='offer']")
            if link_el:
                url = await link_el.get_attribute("href")

            # Generate product_id from URL or title hash
            import hashlib
            id_source = url or title
            product_id = hashlib.md5(id_source.encode()).hexdigest()[:12]

            return SupplierProduct(
                product_id=product_id,
                title=title,
                price=price,
                min_order=min_order,
                supplier_name=supplier,
                image_url=image,
                url=url,
            )

        except Exception as e:
            logger.warning("[1688] parse error: {}", e)
            return None

    # ── BaseCrawler interface ─────────────────────────────────

    async def _do_crawl(self, keyword: str, max_pages: int = 3) -> list[RawProduct]:
        """BaseCrawler interface — delegates to search_suppliers."""
        suppliers = await self.search_suppliers(keyword, max_pages=max_pages)
        return [s.to_raw_product() for s in suppliers]

    async def _parse_product(self, element) -> RawProduct | None:
        """BaseCrawler interface — delegates to _parse_supplier_product."""
        sp = await self._parse_supplier_product(element)
        return sp.to_raw_product() if sp else None

    # ── Class config ──────────────────────────────────────────

    _card_selector = (
        "[class*='offer-list'] [class*='card'], "
        "[class*='offercard'], "
        "[class*='offer-card'], "
        ".sm-offer-item"
    )

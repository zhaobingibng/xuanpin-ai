"""Tests for Phase 23: 1688 API response parsing.

验证 Alibaba1688Crawler 的 getOfferList API 响应解析功能。
不调用真实1688，使用mock数据。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.crawler.alibaba_1688 import Alibaba1688Crawler, SupplierProduct


# ── Mock API Response Data ────────────────────────────────────

MOCK_GET_OFFER_LIST_RESPONSE = {
    "data": {
        "offerList": [
            {
                "offer": {
                    "offerId": "123456789",
                    "title": "三只松鼠坚果礼盒装2024新款",
                    "priceInfo": {"price": "29.90"},
                    "companyName": "杭州零食批发有限公司",
                    "minOrderQuantity": 2,
                    "image": "https://cbu01.alicdn.com/test1.jpg",
                    "detailUrl": "/offer/123456789.html",
                }
            },
            {
                "offer": {
                    "offerId": "987654321",
                    "title": "海苔卷即食脆紫菜零食批发",
                    "priceInfo": {"price": "15.50"},
                    "companyName": "福建海味食品有限公司",
                    "minOrderQuantity": 5,
                    "image": "https://cbu01.alicdn.com/test2.jpg",
                    "detailUrl": "https://detail.1688.com/offer/987654321.html",
                }
            },
            {
                "offer": {
                    "offerId": "555666777",
                    "title": "网红零食大礼包混合装",
                    "price": "39.9",  # 直接价格字段
                    "supplierName": "广州食品供应商",  # 不同字段名
                    "moq": 10,  # 不同起订量字段
                    "imageUrl": "https://cbu01.alicdn.com/test3.jpg",
                    "url": "/offer/555666777.html",
                }
            },
        ]
    }
}

MOCK_OFFER_V2_RESPONSE = {
    "data": {
        "offerV2": [
            {
                "offer": {
                    "offerId": "111222333",
                    "title": "offerV2结构测试商品",
                    "priceInfo": {"value": "19.9"},  # value字段
                    "companyName": "测试供应商",
                    "minOrderQuantity": 1,
                    "picUrl": "https://cbu01.alicdn.com/test_v2.jpg",  # picUrl字段
                    "detailUrl": "/offer/111222333.html",
                }
            }
        ]
    }
}

MOCK_FLAT_RESPONSE = {
    "offerList": [
        {
            "title": "扁平结构测试商品",
            "priceInfo": {"price": "25.00"},
            "companyName": "扁平供应商",
            "minOrderQuantity": 3,
            "image": "https://cbu01.alicdn.com/flat.jpg",
            "detailUrl": "/offer/flat.html",
        }
    ]
}


# ── Tests ─────────────────────────────────────────────────────

class TestAlibaba1688ApiParsing:
    """测试 _parse_api_response 方法"""

    @pytest.fixture
    def crawler(self):
        """创建 crawler 实例（不启动浏览器）"""
        with patch.object(Alibaba1688Crawler, "__init__", lambda self: None):
            c = Alibaba1688Crawler()
            return c

    def test_parse_get_offer_list_structure(self, crawler):
        """测试标准 data.data.offerList 结构"""
        products = crawler._parse_api_response(MOCK_GET_OFFER_LIST_RESPONSE)
        
        assert len(products) == 3
        assert all(isinstance(p, SupplierProduct) for p in products)
        
        # 验证第一个商品
        p1 = products[0]
        assert p1.product_id == "123456789"
        assert p1.title == "三只松鼠坚果礼盒装2024新款"
        assert p1.price == 29.90
        assert p1.min_order == 2
        assert p1.supplier_name == "杭州零食批发有限公司"
        assert p1.image_url == "https://cbu01.alicdn.com/test1.jpg"
        assert "123456789" in p1.url

    def test_parse_offer_v2_structure(self, crawler):
        """测试 data.data.offerV2 结构"""
        products = crawler._parse_api_response(MOCK_OFFER_V2_RESPONSE)
        
        assert len(products) == 1
        p = products[0]
        assert p.product_id == "111222333"
        assert p.title == "offerV2结构测试商品"
        assert p.price == 19.9
        assert p.image_url == "https://cbu01.alicdn.com/test_v2.jpg"

    def test_parse_flat_structure(self, crawler):
        """测试扁平 data.offerList 结构"""
        products = crawler._parse_api_response(MOCK_FLAT_RESPONSE)
        
        assert len(products) == 1
        p = products[0]
        assert p.title == "扁平结构测试商品"
        assert p.price == 25.00
        assert p.min_order == 3

    def test_parse_alternative_field_names(self, crawler):
        """测试不同字段名兼容性"""
        products = crawler._parse_api_response(MOCK_GET_OFFER_LIST_RESPONSE)
        
        # 第三个商品使用替代字段名
        p3 = products[2]
        assert p3.title == "网红零食大礼包混合装"
        assert p3.price == 39.9
        assert p3.supplier_name == "广州食品供应商"
        assert p3.min_order == 10

    def test_parse_empty_response(self, crawler):
        """测试空响应"""
        products = crawler._parse_api_response({})
        assert products == []

    def test_parse_none_data(self, crawler):
        """测试 None 数据"""
        products = crawler._parse_api_response({"data": None})
        assert products == []

    def test_parse_invalid_item_skipped(self, crawler):
        """测试无效条目被跳过"""
        data = {
            "data": {
                "offerList": [
                    {"invalid": "item"},  # 无 title
                    {
                        "offer": {
                            "offerId": "valid",
                            "title": "有效商品",
                            "priceInfo": {"price": "10.0"},
                        }
                    },
                ]
            }
        }
        products = crawler._parse_api_response(data)
        assert len(products) == 1
        assert products[0].title == "有效商品"

    def test_parse_price_cleaning(self, crawler):
        """测试价格字符串清理"""
        data = {
            "data": {
                "offerList": [
                    {
                        "offer": {
                            "title": "价格清理测试",
                            "priceInfo": {"price": "¥ 29.90 元"},
                        }
                    }
                ]
            }
        }
        products = crawler._parse_api_response(data)
        assert len(products) == 1
        assert products[0].price == 29.90

    def test_parse_url_normalization(self, crawler):
        """测试 URL 规范化"""
        data = {
            "data": {
                "offerList": [
                    {
                        "offer": {
                            "title": "URL测试",
                            "detailUrl": "/offer/123.html",  # 相对路径
                        }
                    }
                ]
            }
        }
        products = crawler._parse_api_response(data)
        assert len(products) == 1
        assert products[0].url.startswith("https://")

    def test_to_raw_product_conversion(self, crawler):
        """测试 SupplierProduct 转 RawProduct"""
        products = crawler._parse_api_response(MOCK_GET_OFFER_LIST_RESPONSE)
        
        raw = products[0].to_raw_product()
        assert raw.name == "三只松鼠坚果礼盒装2024新款"
        assert raw.platform == "1688"
        assert raw.shop == "杭州零食批发有限公司"
        assert raw.price == 29.90


class TestAlibaba1688SearchIntegration:
    """测试 search_suppliers 的 API 监听集成"""

    @pytest.mark.asyncio
    async def test_search_uses_api_results(self):
        """测试 search_suppliers 优先使用 API 结果"""
        with patch.object(Alibaba1688Crawler, "__init__", lambda self: None):
            crawler = Alibaba1688Crawler()
            
            # Mock 依赖
            crawler.check_login = AsyncMock(return_value=True)
            crawler.load_cookies = AsyncMock()
            crawler.load_storage_state = AsyncMock()
            crawler.save_cookies = AsyncMock()
            
            # 存储注册的 handler
            registered_handlers = {}
            
            # Mock page
            mock_page = AsyncMock()
            mock_page.url = "https://s.1688.com/selloffer/offer_search.htm"
            mock_page.query_selector_all = AsyncMock(return_value=[])  # DOM 无结果
            
            def mock_on(event, handler):
                registered_handlers[event] = handler
            mock_page.on = mock_on
            
            # Mock context
            mock_context = AsyncMock()
            mock_context.new_page = AsyncMock(return_value=mock_page)
            crawler._new_context = AsyncMock(return_value=mock_context)
            
            crawler._browser_manager = MagicMock()
            
            # 模拟 safe_goto 后触发 API 响应
            async def mock_safe_goto(*args, **kwargs):
                # 触发 API handler
                if "response" in registered_handlers:
                    handler = registered_handlers["response"]
                    mock_response = AsyncMock()
                    mock_response.url = "https://s.1688.com/getOfferList?test=1"
                    mock_response.text = AsyncMock(return_value='{"data": {"offerList": [{"offer": {"offerId": "api_123", "title": "API商品", "priceInfo": {"price": "19.9"}, "companyName": "API供应商"}}]}}')
                    await handler(mock_response)
                return mock_page
            
            crawler._browser_manager.safe_goto = mock_safe_goto
            
            # 执行搜索
            results = await crawler.search_suppliers("测试关键词")
            
            # 验证 API 结果被使用
            assert len(results) == 1
            assert results[0].product_id == "api_123"
            assert results[0].title == "API商品"

    @pytest.mark.asyncio
    async def test_search_fallback_to_dom(self):
        """测试 API 无结果时回退到 DOM 解析"""
        with patch.object(Alibaba1688Crawler, "__init__", lambda self: None):
            crawler = Alibaba1688Crawler()
            
            # Mock 依赖
            crawler.check_login = AsyncMock(return_value=True)
            crawler.load_cookies = AsyncMock()
            crawler.load_storage_state = AsyncMock()
            crawler.save_cookies = AsyncMock()
            
            # Mock page
            mock_page = AsyncMock()
            mock_page.url = "https://s.1688.com/selloffer/offer_search.htm"
            
            # Mock DOM 元素
            mock_card = AsyncMock()
            mock_page.query_selector_all = AsyncMock(return_value=[mock_card])
            
            # Mock context
            mock_context = AsyncMock()
            mock_context.new_page = AsyncMock(return_value=mock_page)
            crawler._new_context = AsyncMock(return_value=mock_context)
            
            crawler._browser_manager = MagicMock()
            crawler._browser_manager.safe_goto = AsyncMock(return_value=mock_page)
            
            # Mock DOM 解析返回商品
            crawler._parse_supplier_product = AsyncMock(return_value=SupplierProduct(
                product_id="dom_456",
                title="DOM商品",
                price=29.9,
            ))
            
            # API 解析返回空
            crawler._parse_api_response = MagicMock(return_value=[])
            
            results = await crawler.search_suppliers("测试", max_pages=1)
            
            # 验证 DOM 结果被使用
            assert len(results) == 1
            assert results[0].product_id == "dom_456"
            assert results[0].title == "DOM商品"


class TestAlibaba1688JsExtraction:
    """测试 _extract_page_data 方法（JS 变量读取）"""

    @pytest.fixture
    def crawler(self):
        """创建 crawler 实例"""
        with patch.object(Alibaba1688Crawler, "__init__", lambda self: None):
            c = Alibaba1688Crawler()
            return c

    @pytest.mark.asyncio
    async def test_extract_window_data_offer_v2(self, crawler):
        """测试从 window.data.offerV2 提取数据"""
        mock_page = AsyncMock()
        
        # Mock window.data.offerV2 返回
        mock_offer_data = {
            "reqParams": {"keywords": "海苔卷"},
            "response": {
                "data": {
                    "offerList": [
                        {
                            "offer": {
                                "offerId": "js_123",
                                "title": "JS变量测试商品",
                                "priceInfo": {"price": "25.90"},
                                "companyName": "JS供应商",
                                "minOrderQuantity": 3,
                                "image": "https://cbu01.alicdn.com/js_test.jpg",
                                "detailUrl": "/offer/js_123.html",
                            }
                        }
                    ]
                }
            },
            "timeCost": 100,
        }
        mock_page.evaluate = AsyncMock(return_value=mock_offer_data)
        mock_page.wait_for_timeout = AsyncMock()
        
        products = await crawler._extract_page_data(mock_page)
        
        assert len(products) == 1
        assert products[0].product_id == "js_123"
        assert products[0].title == "JS变量测试商品"
        assert products[0].price == 25.90
        assert products[0].supplier_name == "JS供应商"

    @pytest.mark.asyncio
    async def test_extract_window_data_flat_structure(self, crawler):
        """测试扁平结构的 window.data"""
        mock_page = AsyncMock()
        
        # 扁平结构: window.data.offerV2 直接包含 offerList
        mock_offer_data = {
            "offerList": [
                {
                    "title": "扁平结构JS商品",
                    "priceInfo": {"price": "19.9"},
                    "companyName": "扁平JS供应商",
                }
            ]
        }
        mock_page.evaluate = AsyncMock(return_value=mock_offer_data)
        mock_page.wait_for_timeout = AsyncMock()
        
        products = await crawler._extract_page_data(mock_page)
        
        assert len(products) == 1
        assert products[0].title == "扁平结构JS商品"

    @pytest.mark.asyncio
    async def test_extract_no_data(self, crawler):
        """测试无数据情况"""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=None)
        mock_page.wait_for_timeout = AsyncMock()
        
        products = await crawler._extract_page_data(mock_page)
        
        assert products == []

    @pytest.mark.asyncio
    async def test_extract_empty_offer_list(self, crawler):
        """测试空 offerList"""
        mock_page = AsyncMock()
        mock_offer_data = {
            "response": {
                "data": {
                    "offerList": []
                }
            }
        }
        mock_page.evaluate = AsyncMock(return_value=mock_offer_data)
        mock_page.wait_for_timeout = AsyncMock()
        
        products = await crawler._extract_page_data(mock_page)
        
        assert products == []

    @pytest.mark.asyncio
    async def test_extract_multiple_products(self, crawler):
        """测试提取多个商品"""
        mock_page = AsyncMock()
        mock_offer_data = {
            "response": {
                "data": {
                    "offerList": [
                        {"offer": {"offerId": "1", "title": "商品1", "priceInfo": {"price": "10"}}},
                        {"offer": {"offerId": "2", "title": "商品2", "priceInfo": {"price": "20"}}},
                        {"offer": {"offerId": "3", "title": "商品3", "priceInfo": {"price": "30"}}},
                    ]
                }
            }
        }
        mock_page.evaluate = AsyncMock(return_value=mock_offer_data)
        mock_page.wait_for_timeout = AsyncMock()
        
        products = await crawler._extract_page_data(mock_page)
        
        assert len(products) == 3
        assert products[0].product_id == "1"
        assert products[1].product_id == "2"
        assert products[2].product_id == "3"

    @pytest.mark.asyncio
    async def test_extract_handles_evaluate_error(self, crawler):
        """测试 evaluate 异常处理"""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=Exception("JS error"))
        mock_page.wait_for_timeout = AsyncMock()
        
        products = await crawler._extract_page_data(mock_page)
        
        assert products == []


class TestAlibaba1688PriorityOrder:
    """测试数据获取优先级"""

    @pytest.mark.asyncio
    async def test_js_data_priority_over_dom(self):
        """测试 JS 数据优先于 DOM"""
        with patch.object(Alibaba1688Crawler, "__init__", lambda self: None):
            crawler = Alibaba1688Crawler()
            
            # Mock 依赖
            crawler.check_login = AsyncMock(return_value=True)
            crawler.load_cookies = AsyncMock()
            crawler.load_storage_state = AsyncMock()
            crawler.save_cookies = AsyncMock()
            
            # Mock page
            mock_page = AsyncMock()
            mock_page.url = "https://s.1688.com/selloffer/offer_search.htm"
            mock_page.query_selector_all = AsyncMock(return_value=[AsyncMock()])  # DOM 有结果
            mock_page.on = lambda *args: None
            
            # Mock context
            mock_context = AsyncMock()
            mock_context.new_page = AsyncMock(return_value=mock_page)
            crawler._new_context = AsyncMock(return_value=mock_context)
            
            crawler._browser_manager = MagicMock()
            crawler._browser_manager.safe_goto = AsyncMock(return_value=mock_page)
            
            # Mock JS 提取返回商品
            crawler._extract_page_data = AsyncMock(return_value=[
                SupplierProduct(product_id="js_1", title="JS商品", price=10.0)
            ])
            
            # Mock DOM 解析返回商品
            crawler._parse_supplier_product = AsyncMock(return_value=SupplierProduct(
                product_id="dom_1", title="DOM商品", price=20.0
            ))
            
            results = await crawler.search_suppliers("测试", max_pages=1)
            
            # 验证 JS 数据被优先使用
            assert len(results) == 1
            assert results[0].product_id == "js_1"
            assert results[0].title == "JS商品"


class TestAlibaba1688EventExtraction:
    """测试 _extract_event_data 方法（事件捕获）"""

    @pytest.fixture
    def crawler(self):
        """创建 crawler 实例"""
        with patch.object(Alibaba1688Crawler, "__init__", lambda self: None):
            c = Alibaba1688Crawler()
            return c

    @pytest.mark.asyncio
    async def test_extract_offer_v2_event(self, crawler):
        """测试从 offerV2 自定义事件提取数据"""
        mock_page = AsyncMock()
        
        # Mock window.__1688_debug 返回
        mock_events = [
            {
                "type": "offerV2",
                "detail": {
                    "data": {
                        "offerList": [
                            {
                                "offer": {
                                    "offerId": "event_123",
                                    "title": "事件捕获测试商品",
                                    "priceInfo": {"price": "35.90"},
                                    "companyName": "事件供应商",
                                    "minOrderQuantity": 2,
                                }
                            }
                        ]
                    }
                },
                "timestamp": 1234567890,
            }
        ]
        mock_page.evaluate = AsyncMock(return_value=mock_events)
        
        products = await crawler._extract_event_data(mock_page)
        
        assert len(products) == 1
        assert products[0].product_id == "event_123"
        assert products[0].title == "事件捕获测试商品"
        assert products[0].price == 35.90

    @pytest.mark.asyncio
    async def test_extract_post_message_event(self, crawler):
        """测试从 postMessage 事件提取数据"""
        mock_page = AsyncMock()
        
        # Mock postMessage 事件
        mock_events = [
            {
                "type": "message",
                "action": "getOfferList",
                "data": {
                    "offerList": [
                        {
                            "offer": {
                                "offerId": "msg_456",
                                "title": "postMessage测试商品",
                                "priceInfo": {"price": "22.50"},
                                "companyName": "消息供应商",
                            }
                        }
                    ]
                },
                "timestamp": 1234567890,
            }
        ]
        mock_page.evaluate = AsyncMock(return_value=mock_events)
        
        products = await crawler._extract_event_data(mock_page)
        
        assert len(products) == 1
        assert products[0].product_id == "msg_456"
        assert products[0].title == "postMessage测试商品"

    @pytest.mark.asyncio
    async def test_extract_multiple_events(self, crawler):
        """测试多个事件捕获"""
        mock_page = AsyncMock()
        
        mock_events = [
            {
                "type": "message",
                "action": "getOfferList",
                "data": {
                    "offerList": [
                        {"offer": {"offerId": "1", "title": "商品1", "priceInfo": {"price": "10"}}},
                    ]
                },
            },
            {
                "type": "offerV2",
                "detail": {
                    "data": {
                        "offerList": [
                            {"offer": {"offerId": "2", "title": "商品2", "priceInfo": {"price": "20"}}},
                        ]
                    }
                },
            }
        ]
        mock_page.evaluate = AsyncMock(return_value=mock_events)
        
        products = await crawler._extract_event_data(mock_page)
        
        assert len(products) == 2
        product_ids = [p.product_id for p in products]
        assert "1" in product_ids
        assert "2" in product_ids

    @pytest.mark.asyncio
    async def test_extract_no_events(self, crawler):
        """测试无事件捕获"""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[])
        
        products = await crawler._extract_event_data(mock_page)
        
        assert products == []

    @pytest.mark.asyncio
    async def test_extract_ignores_non_product_events(self, crawler):
        """测试忽略非商品事件"""
        mock_page = AsyncMock()
        
        mock_events = [
            {"type": "message", "action": "otherAction", "data": {}},
            {"type": "unknown", "data": {}},
        ]
        mock_page.evaluate = AsyncMock(return_value=mock_events)
        
        products = await crawler._extract_event_data(mock_page)
        
        assert products == []

    @pytest.mark.asyncio
    async def test_extract_handles_evaluate_error(self, crawler):
        """测试 evaluate 异常处理"""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=Exception("JS error"))
        
        products = await crawler._extract_event_data(mock_page)
        
        assert products == []


class TestAlibaba1688FullPriorityOrder:
    """测试完整的数据获取优先级"""

    @pytest.mark.asyncio
    async def test_event_priority_over_all(self):
        """测试 Event 数据优先级最高"""
        with patch.object(Alibaba1688Crawler, "__init__", lambda self: None):
            crawler = Alibaba1688Crawler()
            
            # Mock 依赖
            crawler.check_login = AsyncMock(return_value=True)
            crawler.load_cookies = AsyncMock()
            crawler.load_storage_state = AsyncMock()
            crawler.save_cookies = AsyncMock()
            
            # Mock page
            mock_page = AsyncMock()
            mock_page.url = "https://s.1688.com/selloffer/offer_search.htm"
            mock_page.query_selector_all = AsyncMock(return_value=[AsyncMock()])
            mock_page.on = lambda *args: None
            mock_page.add_init_script = AsyncMock()
            
            # Mock context
            mock_context = AsyncMock()
            mock_context.new_page = AsyncMock(return_value=mock_page)
            crawler._new_context = AsyncMock(return_value=mock_context)
            
            crawler._browser_manager = MagicMock()
            crawler._browser_manager.safe_goto = AsyncMock(return_value=mock_page)
            
            # Mock 各种数据源
            crawler._extract_event_data = AsyncMock(return_value=[
                SupplierProduct(product_id="event_1", title="Event商品", price=10.0)
            ])
            crawler._extract_page_data = AsyncMock(return_value=[
                SupplierProduct(product_id="js_1", title="JS商品", price=20.0)
            ])
            crawler._parse_supplier_product = AsyncMock(return_value=SupplierProduct(
                product_id="dom_1", title="DOM商品", price=30.0
            ))
            
            results = await crawler.search_suppliers("测试", max_pages=1)
            
            # 验证 Event 数据被优先使用
            assert len(results) == 1
            assert results[0].product_id == "event_1"
            assert results[0].title == "Event商品"

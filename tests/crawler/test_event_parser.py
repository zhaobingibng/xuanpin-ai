"""Tests for Phase 25: 1688 Event Data Parser.

Tests EventParser class for parsing captured events into product data.
"""

import pytest

from app.crawler.event_parser import EventParser, ParsedProduct


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def parser():
    """Create EventParser instance."""
    return EventParser()


@pytest.fixture
def sample_offer_v2_event():
    """Sample offerV2 event from window.__1688_debug."""
    return {
        "type": "offerV2",
        "detail": {
            "reqParams": {"keywords": "海苔卷"},
            "response": {
                "data": {
                    "offerList": [
                        {
                            "offer": {
                                "offerId": "123456789",
                                "title": "三只松鼠坚果礼盒装2024新款",
                                "priceInfo": {"price": "29.90"},
                                "companyName": "杭州零食批发有限公司",
                                "minOrderQuantity": 2,
                                "quantitySumMonth": 1500,
                                "image": "https://cbu01.alicdn.com/test1.jpg",
                                "detailUrl": "/offer/123456789.html",
                            }
                        }
                    ]
                }
            },
            "timeCost": 100,
        },
        "timestamp": 1234567890,
    }


@pytest.fixture
def sample_message_event():
    """Sample postMessage event."""
    return {
        "type": "message",
        "action": "getOfferList",
        "data": {
            "offerList": [
                {
                    "offer": {
                        "offerId": "msg_001",
                        "title": "海苔卷即食脆紫菜零食批发",
                        "priceInfo": {"price": "15.50"},
                        "companyName": "福建海味食品有限公司",
                        "quantitySumMonth": 800,
                        "imageUrl": "https://cbu01.alicdn.com/test2.jpg",
                        "detailUrl": "https://detail.1688.com/offer/msg_001.html",
                    }
                }
            ]
        },
        "timestamp": 1234567891,
    }


@pytest.fixture
def sample_dispatch_event():
    """Sample dispatchEvent hook capture."""
    return {
        "type": "dispatch",
        "eventType": "search:firstDataReady:offerV2",
        "detail": {
            "response": {
                "data": {
                    "offerList": [
                        {
                            "offer": {
                                "offerId": "dispatch_001",
                                "title": "dispatch事件测试商品",
                                "priceInfo": {"value": "19.9"},
                                "companyName": "Dispatch供应商",
                            }
                        }
                    ]
                }
            }
        },
        "timestamp": 1234567892,
    }


# ── Test: Normal offerV2 Event Parsing ───────────────────────

class TestOfferV2Parsing:
    """Test offerV2 event parsing."""

    def test_parse_single_product(self, parser, sample_offer_v2_event):
        """Test parsing single product from offerV2 event."""
        products = parser.parse_events([sample_offer_v2_event])
        
        assert len(products) == 1
        p = products[0]
        assert p.title == "三只松鼠坚果礼盒装2024新款"
        assert p.price == 29.90
        assert p.shop_name == "杭州零食批发有限公司"
        assert p.offer_id == "123456789"
        assert p.sales == 1500
        assert "123456789" in p.url
        assert p.image == "https://cbu01.alicdn.com/test1.jpg"
        assert p.source == "1688"

    def test_parse_offer_event_directly(self, parser, sample_offer_v2_event):
        """Test parse_offer_event method."""
        products = parser.parse_offer_event(sample_offer_v2_event)
        
        assert len(products) == 1
        assert products[0].title == "三只松鼠坚果礼盒装2024新款"

    def test_parse_offer_event_empty_detail(self, parser):
        """Test offerV2 with empty detail."""
        event = {"type": "offerV2", "detail": {}}
        products = parser.parse_offer_event(event)
        assert products == []

    def test_parse_offer_event_no_detail(self, parser):
        """Test offerV2 without detail key."""
        event = {"type": "offerV2"}
        products = parser.parse_offer_event(event)
        assert products == []


# ── Test: Multiple Products ──────────────────────────────────

class TestMultipleProducts:
    """Test parsing multiple products."""

    def test_parse_multiple_products(self, parser):
        """Test parsing multiple products from one event."""
        event = {
            "type": "offerV2",
            "detail": {
                "response": {
                    "data": {
                        "offerList": [
                            {
                                "offer": {
                                    "offerId": "1",
                                    "title": "商品1",
                                    "priceInfo": {"price": "10"},
                                }
                            },
                            {
                                "offer": {
                                    "offerId": "2",
                                    "title": "商品2",
                                    "priceInfo": {"price": "20"},
                                }
                            },
                            {
                                "offer": {
                                    "offerId": "3",
                                    "title": "商品3",
                                    "priceInfo": {"price": "30"},
                                }
                            },
                        ]
                    }
                }
            },
        }
        
        products = parser.parse_events([event])
        
        assert len(products) == 3
        assert products[0].offer_id == "1"
        assert products[1].offer_id == "2"
        assert products[2].offer_id == "3"

    def test_parse_multiple_events(self, parser, sample_offer_v2_event, sample_message_event):
        """Test parsing multiple events."""
        products = parser.parse_events([sample_offer_v2_event, sample_message_event])
        
        assert len(products) == 2
        titles = {p.title for p in products}
        assert "三只松鼠坚果礼盒装2024新款" in titles
        assert "海苔卷即食脆紫菜零食批发" in titles

    def test_deduplication(self, parser):
        """Test product deduplication by offer_id."""
        event1 = {
            "type": "offerV2",
            "detail": {"response": {"data": {"offerList": [
                {"offer": {"offerId": "same_id", "title": "商品A", "priceInfo": {"price": "10"}}}
            ]}}},
        }
        event2 = {
            "type": "offerV2",
            "detail": {"response": {"data": {"offerList": [
                {"offer": {"offerId": "same_id", "title": "商品A", "priceInfo": {"price": "10"}}}
            ]}}},
        }
        
        products = parser.parse_events([event1, event2])
        
        assert len(products) == 1


# ── Test: Missing Fields ─────────────────────────────────────

class TestMissingFields:
    """Test parsing with missing fields."""

    def test_missing_price(self, parser):
        """Test product without price."""
        event = {
            "type": "offerV2",
            "detail": {"response": {"data": {"offerList": [
                {"offer": {"offerId": "1", "title": "无价格商品"}}
            ]}}},
        }
        
        products = parser.parse_events([event])
        
        assert len(products) == 1
        assert products[0].price == 0.0

    def test_missing_shop_name(self, parser):
        """Test product without shop name."""
        event = {
            "type": "offerV2",
            "detail": {"response": {"data": {"offerList": [
                {"offer": {"offerId": "1", "title": "无供应商商品", "priceInfo": {"price": "10"}}}
            ]}}},
        }
        
        products = parser.parse_events([event])
        
        assert len(products) == 1
        assert products[0].shop_name == ""

    def test_missing_offer_id(self, parser):
        """Test product without offer_id generates one."""
        event = {
            "type": "offerV2",
            "detail": {"response": {"data": {"offerList": [
                {"offer": {"title": "无ID商品", "priceInfo": {"price": "10"}}}
            ]}}},
        }
        
        products = parser.parse_events([event])
        
        assert len(products) == 1
        assert len(products[0].offer_id) > 0  # Generated ID

    def test_missing_title_skips_product(self, parser):
        """Test product without title is skipped."""
        event = {
            "type": "offerV2",
            "detail": {"response": {"data": {"offerList": [
                {"offer": {"offerId": "1", "priceInfo": {"price": "10"}}}
            ]}}},
        }
        
        products = parser.parse_events([event])
        
        assert len(products) == 0

    def test_price_with_currency_symbols(self, parser):
        """Test price parsing with currency symbols."""
        event = {
            "type": "offerV2",
            "detail": {"response": {"data": {"offerList": [
                {"offer": {"offerId": "1", "title": "测试", "priceInfo": {"price": "¥ 29.90 元"}}}
            ]}}},
        }
        
        products = parser.parse_events([event])
        
        assert len(products) == 1
        assert products[0].price == 29.90


# ── Test: Empty Events ───────────────────────────────────────

class TestEmptyEvents:
    """Test empty event handling."""

    def test_empty_list(self, parser):
        """Test empty event list."""
        products = parser.parse_events([])
        assert products == []

    def test_none_events(self, parser):
        """Test None input."""
        products = parser.parse_events(None)
        assert products == []

    def test_non_dict_events(self, parser):
        """Test events with non-dict items."""
        products = parser.parse_events(["string", 123, None])
        assert products == []

    def test_unknown_event_type(self, parser):
        """Test events with unknown type."""
        events = [{"type": "unknown", "data": {}}]
        products = parser.parse_events(events)
        assert products == []

    def test_empty_offer_list(self, parser):
        """Test event with empty offerList."""
        event = {
            "type": "offerV2",
            "detail": {"response": {"data": {"offerList": []}}},
        }
        products = parser.parse_events([event])
        assert products == []


# ── Test: Alternative Data Structures ────────────────────────

class TestAlternativeStructures:
    """Test alternative 1688 data structures."""

    def test_flat_offer_list(self, parser):
        """Test flat offerList structure."""
        event = {
            "type": "offerV2",
            "detail": {
                "offerList": [
                    {"offer": {"offerId": "1", "title": "扁平结构", "priceInfo": {"price": "10"}}}
                ]
            },
        }
        
        products = parser.parse_events([event])
        
        assert len(products) == 1
        assert products[0].title == "扁平结构"

    def test_message_event(self, parser, sample_message_event):
        """Test postMessage event parsing."""
        products = parser.parse_events([sample_message_event])
        
        assert len(products) == 1
        assert products[0].title == "海苔卷即食脆紫菜零食批发"
        assert products[0].offer_id == "msg_001"

    def test_dispatch_event(self, parser, sample_dispatch_event):
        """Test dispatchEvent hook capture."""
        products = parser.parse_events([sample_dispatch_event])
        
        assert len(products) == 1
        assert products[0].title == "dispatch事件测试商品"

    def test_alternative_field_names(self, parser):
        """Test alternative field name variations."""
        event = {
            "type": "offerV2",
            "detail": {"response": {"data": {"offerList": [
                {
                    "offer": {
                        "offerId": "alt_1",
                        "subject": "替代字段名商品",  # subject instead of title
                        "supplierName": "替代供应商",  # supplierName instead of companyName
                        "imageUrl": "https://test.com/img.jpg",  # imageUrl instead of image
                        "link": "/offer/alt_1.html",  # link instead of detailUrl
                    }
                }
            ]}}},
        }
        
        products = parser.parse_events([event])
        
        assert len(products) == 1
        assert products[0].title == "替代字段名商品"
        assert products[0].shop_name == "替代供应商"
        assert products[0].image == "https://test.com/img.jpg"
        assert "alt_1" in products[0].url


# ── Test: ParsedProduct ──────────────────────────────────────

class TestParsedProduct:
    """Test ParsedProduct dataclass."""

    def test_to_dict(self):
        """Test ParsedProduct to_dict conversion."""
        product = ParsedProduct(
            title="测试商品",
            price=29.9,
            sales=100,
            shop_name="测试店铺",
            offer_id="test_001",
            url="https://test.com",
            image="https://test.com/img.jpg",
            source="1688",
        )
        
        d = product.to_dict()
        
        assert d["title"] == "测试商品"
        assert d["price"] == 29.9
        assert d["sales"] == 100
        assert d["shop_name"] == "测试店铺"
        assert d["offer_id"] == "test_001"
        assert d["source"] == "1688"

    def test_default_values(self):
        """Test ParsedProduct default values."""
        product = ParsedProduct()
        
        assert product.title == ""
        assert product.price == 0.0
        assert product.sales == 0
        assert product.source == "1688"

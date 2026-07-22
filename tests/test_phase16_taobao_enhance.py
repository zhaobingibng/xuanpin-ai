"""Tests for Phase 16 Task 1: Taobao shop crawling enhancement."""

from __future__ import annotations

import pytest

from app.crawler.models.schemas import RawProduct
from app.crawler.taobao import TaobaoCrawler


class TestRawProductShopUrl:
    """RawProduct shop_url 字段测试。"""

    def test_shop_url_default_none(self):
        """shop_url 默认为 None。"""
        prod = RawProduct(
            name="test", platform="taobao", shop="test shop", price=100.0
        )
        assert prod.shop_url is None

    def test_shop_url_set(self):
        """可以设置 shop_url。"""
        prod = RawProduct(
            name="test", platform="taobao", shop="test shop", price=100.0,
            shop_url="https://shop123.taobao.com"
        )
        assert prod.shop_url == "https://shop123.taobao.com"

    def test_shop_url_not_in_to_db_kwargs(self):
        """shop_url 不应传入 ProductService (Product 模型无此字段)。"""
        prod = RawProduct(
            name="test", platform="taobao", shop="test shop", price=100.0,
            shop_url="https://shop123.taobao.com"
        )
        kwargs = prod.to_db_kwargs()
        assert "shop_url" not in kwargs


class TestExtractShopsFromResults:
    """extract_shops_from_results 静态方法测试。"""

    def test_extract_empty(self):
        """空列表返回空。"""
        result = TaobaoCrawler.extract_shops_from_results([])
        assert result == []

    def test_extract_single_shop(self):
        """单个店铺去重。"""
        products = [
            RawProduct(name="A", platform="taobao", shop="店铺1", price=100,
                       shop_url="https://shop1.taobao.com"),
            RawProduct(name="B", platform="taobao", shop="店铺1", price=200,
                       shop_url="https://shop1.taobao.com"),
        ]
        result = TaobaoCrawler.extract_shops_from_results(products)
        assert len(result) == 1
        assert result[0]["shop_name"] == "店铺1"
        assert result[0]["shop_url"] == "https://shop1.taobao.com"

    def test_extract_multiple_shops(self):
        """多个店铺各自独立。"""
        products = [
            RawProduct(name="A", platform="taobao", shop="店铺1", price=100,
                       shop_url="https://shop1.taobao.com"),
            RawProduct(name="B", platform="taobao", shop="店铺2", price=200,
                       shop_url="https://shop2.taobao.com"),
        ]
        result = TaobaoCrawler.extract_shops_from_results(products)
        assert len(result) == 2
        names = {r["shop_name"] for r in result}
        assert names == {"店铺1", "店铺2"}

    def test_ignore_unknown_shop(self):
        """未知店铺被过滤。"""
        products = [
            RawProduct(name="A", platform="taobao", shop="未知店铺", price=100),
            RawProduct(name="B", platform="taobao", shop="已知店铺", price=200,
                       shop_url="https://shop.taobao.com"),
        ]
        result = TaobaoCrawler.extract_shops_from_results(products)
        assert len(result) == 1
        assert result[0]["shop_name"] == "已知店铺"

    def test_fill_missing_shop_url(self):
        """如果第一个商品无 shop_url，后续商品补充。"""
        products = [
            RawProduct(name="A", platform="taobao", shop="店铺1", price=100,
                       shop_url=None),
            RawProduct(name="B", platform="taobao", shop="店铺1", price=200,
                       shop_url="https://shop1.taobao.com"),
        ]
        result = TaobaoCrawler.extract_shops_from_results(products)
        assert len(result) == 1
        assert result[0]["shop_url"] == "https://shop1.taobao.com"

    def test_platform_preserved(self):
        """平台信息保留。"""
        products = [
            RawProduct(name="A", platform="taobao", shop="店铺1", price=100),
        ]
        result = TaobaoCrawler.extract_shops_from_results(products)
        assert result[0]["platform"] == "taobao"


class TestTaobaoCrawlerShopUrlParsing:
    """TaobaoCrawler 解析 shop_url 能力测试。"""

    def test_parse_product_accepts_shop_name_override(self):
        """_parse_product 支持 shop_name_override 参数。"""
        import inspect
        sig = inspect.signature(TaobaoCrawler._parse_product)
        params = list(sig.parameters.keys())
        assert "shop_name_override" in params

    def test_has_extract_shops_from_results(self):
        """TaobaoCrawler 应有 extract_shops_from_results 静态方法。"""
        assert hasattr(TaobaoCrawler, "extract_shops_from_results")
        assert callable(TaobaoCrawler.extract_shops_from_results)

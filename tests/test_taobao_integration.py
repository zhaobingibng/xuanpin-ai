"""Tests for Phase 14 Task 1: Taobao crawler integration."""

import pytest

from app.crawler import TaobaoCrawler
from app.crawler.base import VALID_PLATFORMS, CookieManager
from app.tasks.jobs import PLATFORM_CRAWLERS


class TestTaobaoPlatformRegistration:
    """淘宝平台注册测试。"""

    def test_taobao_in_valid_platforms(self):
        """taobao 应在 VALID_PLATFORMS 中。"""
        assert "taobao" in VALID_PLATFORMS

    def test_taobao_in_platform_crawlers(self):
        """taobao 应在 PLATFORM_CRAWLERS 映射中。"""
        assert "taobao" in PLATFORM_CRAWLERS
        assert PLATFORM_CRAWLERS["taobao"] is TaobaoCrawler

    def test_cookie_manager_accepts_taobao(self, tmp_path):
        """CookieManager 应接受 taobao 平台。"""
        manager = CookieManager(tmp_path)
        path = manager.get_cookie_path("taobao")
        assert path.name == "taobao.json"

    def test_cookie_manager_taobao_save_load(self, tmp_path):
        """CookieManager 应能保存/加载 taobao cookies。"""
        manager = CookieManager(tmp_path)
        cookies = [{"name": "test", "value": "123", "domain": ".taobao.com"}]
        manager.save("taobao", cookies)
        loaded = manager.load("taobao")
        assert len(loaded) == 1
        assert loaded[0]["name"] == "test"


class TestTaobaoCrawlerAttributes:
    """TaobaoCrawler 属性测试。"""

    def test_platform_attribute(self):
        """TaobaoCrawler.PLATFORM 应为 'taobao'。"""
        assert TaobaoCrawler.PLATFORM == "taobao"

    def test_base_url(self):
        """TaobaoCrawler.BASE_URL 应指向淘宝。"""
        assert "taobao.com" in TaobaoCrawler.BASE_URL

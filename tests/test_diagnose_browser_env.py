"""Tests for scripts/diagnose_browser_env.py — 浏览器环境诊断脚本。"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import diagnose_browser_env  # noqa: E402


# ── Constants ───────────────────────────────────────────────────


class TestConstants:
    """验证脚本常量。"""

    def test_fingerprint_js_is_string(self):
        assert isinstance(diagnose_browser_env.BROWSER_FINGERPRINT_JS, str)
        assert "navigator.userAgent" in diagnose_browser_env.BROWSER_FINGERPRINT_JS
        assert "navigator.webdriver" in diagnose_browser_env.BROWSER_FINGERPRINT_JS

    def test_page_type_js_is_string(self):
        assert isinstance(diagnose_browser_env.PAGE_TYPE_JS, str)
        assert "J_ItemList" in diagnose_browser_env.PAGE_TYPE_JS
        assert "item.taobao.com" in diagnose_browser_env.PAGE_TYPE_JS

    def test_debug_dir_path(self):
        assert "taobao_debug" in str(diagnose_browser_env.DEBUG_DIR)
        assert "storage" in str(diagnose_browser_env.DEBUG_DIR)


# ── parse_args ──────────────────────────────────────────────────


class TestParseArgs:
    """验证命令行参数。"""

    def test_defaults(self):
        args = diagnose_browser_env.parse_args([])
        assert args.no_navigate is False
        assert args.keyword == "海苔卷"

    def test_no_navigate(self):
        sys.argv = ["diag.py", "--no-navigate"]
        args = diagnose_browser_env.parse_args()
        assert args.no_navigate is True

    def test_custom_keyword(self):
        sys.argv = ["diag.py", "--keyword", "蓝牙耳机"]
        args = diagnose_browser_env.parse_args()
        assert args.keyword == "蓝牙耳机"


# ── _print_fingerprint ──────────────────────────────────────────


class TestPrintFingerprint:
    """验证指纹打印函数。"""

    def test_full_fingerprint_output(self, capsys):
        fp = {
            "userAgent": "Mozilla/5.0 Chrome/125",
            "platform": "Win32",
            "vendor": "Google Inc.",
            "webdriver": False,
            "language": "zh-CN",
            "languages": ["zh-CN", "zh"],
            "timezone": "Asia/Shanghai",
            "timezoneOffset": -480,
            "screenWidth": 1920, "screenHeight": 1080,
            "screenAvailWidth": 1920, "screenAvailHeight": 1040,
            "innerWidth": 375, "innerHeight": 812,
            "outerWidth": 375, "outerHeight": 812,
            "devicePixelRatio": 2,
            "screenColorDepth": 24,
            "maxTouchPoints": 0,
            "hardwareConcurrency": 8,
            "deviceMemory": 8,
            "connectionType": "4g",
            "pluginCount": 3,
            "mimeTypesCount": 5,
            "pluginNames": ["Chrome PDF Plugin", "Chrome PDF Viewer", "Native Client"],
            "hasChrome": True,
            "hasChromeRuntime": True,
            "cookieEnabled": True,
            "doNotTrack": "1",
            "permissionsAvailable": True,
            "documentHidden": False,
            "visibilityState": "visible",
            "ontouchstart": False,
            "canvasHash": 1234,
            "webglVendor": "Google Inc.",
            "webglRenderer": "ANGLE (NVIDIA)",
        }
        diagnose_browser_env._print_fingerprint(fp)
        out = capsys.readouterr().out

        # Key sections present
        assert "WebDriver" in out
        assert "Locale" in out
        assert "Timezone" in out
        assert "Viewport" in out
        assert "Hardware" in out
        assert "Plugins" in out
        assert "Chrome" in out
        assert "Canvas/WebGL" in out

        # Key values
        assert "Mozilla/5.0 Chrome/125" in out
        assert "zh-CN" in out
        assert "Asia/Shanghai" in out
        assert "375x812" in out
        assert "[OK] 未暴露" in out

    def test_webdriver_true_warns(self, capsys):
        fp = {
            "userAgent": "HeadlessChrome",
            "platform": "Linux",
            "vendor": "Google Inc.",
            "webdriver": True,
            "language": "en-US",
            "languages": ["en-US"],
            "timezone": "UTC",
            "timezoneOffset": 0,
            "screenWidth": 1280, "screenHeight": 720,
            "screenAvailWidth": 1280, "screenAvailHeight": 720,
            "innerWidth": 1280, "innerHeight": 720,
            "outerWidth": 1280, "outerHeight": 720,
            "devicePixelRatio": 1,
            "screenColorDepth": 24,
            "maxTouchPoints": 0,
            "hardwareConcurrency": 4,
            "deviceMemory": 4,
            "connectionType": "not available",
            "pluginCount": 0,
            "mimeTypesCount": 0,
            "pluginNames": [],
            "hasChrome": False,
            "hasChromeRuntime": False,
            "cookieEnabled": True,
            "doNotTrack": None,
            "permissionsAvailable": False,
            "documentHidden": False,
            "visibilityState": "visible",
            "ontouchstart": False,
            "canvasHash": 200,
            "webglVendor": "Google Inc.",
            "webglRenderer": "Google SwiftShader",
        }
        diagnose_browser_env._print_fingerprint(fp)
        out = capsys.readouterr().out

        assert "[!!] 反自动化标志已暴露" in out


# ── _print_page_type ────────────────────────────────────────────


class TestPrintPageType:
    """验证页面类型分析打印函数。"""

    def test_search_result_page(self, capsys):
        pt = {
            "url": "https://s.taobao.com/search?q=海苔卷",
            "title": "海苔卷-淘宝搜索",
            "totalElements": 500,
            "hasJItemList": True,
            "hasLoginPrompt": False,
            "hasCaptcha": False,
            "cardCounts": {
                '.J_ItemList [data-nid]': 20,
                'a[href*="item.taobao.com"]': 44,
            },
            "bodyText": "海苔卷零食...",
        }
        diagnose_browser_env._print_page_type(pt)
        out = capsys.readouterr().out

        assert "搜索结果页 [OK]" in out
        assert "J_ItemList" in out
        assert "有" in out

    def test_login_page(self, capsys):
        pt = {
            "url": "https://login.taobao.com/",
            "title": "登录-淘宝",
            "totalElements": 200,
            "hasJItemList": False,
            "hasLoginPrompt": True,
            "hasCaptcha": False,
            "cardCounts": {},
            "bodyText": "亲，请登录",
        }
        diagnose_browser_env._print_page_type(pt)
        out = capsys.readouterr().out

        assert "登录页面 [!!]" in out

    def test_captcha_page(self, capsys):
        pt = {
            "url": "https://sec.taobao.com/",
            "title": "",
            "totalElements": 50,
            "hasJItemList": False,
            "hasLoginPrompt": False,
            "hasCaptcha": True,
            "cardCounts": {},
            "bodyText": "验证码",
        }
        diagnose_browser_env._print_page_type(pt)
        out = capsys.readouterr().out

        assert "验证码/风控页面 [!!]" in out

    def test_unknown_page(self, capsys):
        pt = {
            "url": "about:blank",
            "title": "",
            "totalElements": 0,
            "hasJItemList": False,
            "hasLoginPrompt": False,
            "hasCaptcha": False,
            "cardCounts": {},
            "bodyText": "",
        }
        diagnose_browser_env._print_page_type(pt)
        out = capsys.readouterr().out

        assert "未知/空白页面 [??]" in out


# ── main() ──────────────────────────────────────────────────────


class TestMain:
    """验证 main() 函数主要路径。"""

    @pytest.mark.asyncio
    async def test_no_navigate_mode(self, capsys):
        """--no-navigate 应跳过淘宝页面导航。"""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value={
            "userAgent": "Mozilla/5.0",
            "platform": "Win32",
            "vendor": "Google",
            "webdriver": False,
            "language": "zh-CN",
            "languages": ["zh-CN"],
            "timezone": "Asia/Shanghai",
            "timezoneOffset": -480,
            "screenWidth": 1920, "screenHeight": 1080,
            "screenAvailWidth": 1920, "screenAvailHeight": 1040,
            "innerWidth": 375, "innerHeight": 812,
            "outerWidth": 375, "outerHeight": 812,
            "devicePixelRatio": 2,
            "screenColorDepth": 24,
            "maxTouchPoints": 0,
            "hardwareConcurrency": 8,
            "deviceMemory": 8,
            "connectionType": "4g",
            "pluginCount": 3,
            "mimeTypesCount": 5,
            "pluginNames": ["PDF"],
            "hasChrome": True,
            "hasChromeRuntime": True,
            "cookieEnabled": True,
            "doNotTrack": "1",
            "permissionsAvailable": True,
            "documentHidden": False,
            "visibilityState": "visible",
            "ontouchstart": False,
            "canvasHash": 1000,
            "webglVendor": "Google",
            "webglRenderer": "ANGLE",
        })

        mock_page.goto = AsyncMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_crawler = MagicMock()
        mock_crawler._new_context = AsyncMock(return_value=mock_context)
        mock_crawler.load_cookies = AsyncMock()
        mock_crawler.load_storage_state = AsyncMock(return_value=True)
        mock_crawler._browser_manager = MagicMock()
        mock_crawler._browser_manager._persistent = True
        mock_crawler._browser_manager._persistent_ctx = MagicMock()
        mock_crawler._browser_manager._browser = None
        mock_crawler._browser_manager._user_data_dir = "./storage/browser_profile"
        mock_crawler.close = AsyncMock()

        mock_page.close = AsyncMock()
        mock_context.close = AsyncMock()

        sys.argv = ["diag.py", "--no-navigate"]
        with (
            patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler),
        ):
            result = await diagnose_browser_env.main()

        assert result == 0
        out = capsys.readouterr().out
        assert "浏览器指纹" in out
        assert "headless" in out.lower() or "Headless" in out
        # Should NOT have navigated to Taobao
        assert "Step 4" not in out

    @pytest.mark.asyncio
    async def test_full_diagnosis_with_navigate(self, tmp_path, capsys):
        """完整诊断包括淘宝导航。"""
        # Mock for fingerprint
        fp_result = {
            "userAgent": "Mozilla/5.0",
            "platform": "Win32",
            "vendor": "Google",
            "webdriver": False,
            "language": "en",
            "languages": ["en"],
            "timezone": "UTC",
            "timezoneOffset": 0,
            "screenWidth": 800, "screenHeight": 600,
            "screenAvailWidth": 800, "screenAvailHeight": 600,
            "innerWidth": 800, "innerHeight": 600,
            "outerWidth": 800, "outerHeight": 600,
            "devicePixelRatio": 1,
            "screenColorDepth": 24,
            "maxTouchPoints": 0,
            "hardwareConcurrency": 2,
            "deviceMemory": 2,
            "connectionType": "not available",
            "pluginCount": 0,
            "mimeTypesCount": 0,
            "pluginNames": [],
            "hasChrome": False,
            "hasChromeRuntime": False,
            "cookieEnabled": True,
            "doNotTrack": None,
            "permissionsAvailable": False,
            "documentHidden": False,
            "visibilityState": "visible",
            "ontouchstart": False,
            "canvasHash": 200,
            "webglVendor": "Google Inc.",
            "webglRenderer": "Google SwiftShader",
        }
        # Mock for page type
        pt_result = {
            "url": "https://s.taobao.com/search?q=海苔卷",
            "title": "海苔卷-淘宝",
            "totalElements": 100,
            "hasJItemList": True,
            "hasLoginPrompt": False,
            "hasCaptcha": False,
            "cardCounts": {"a[href*=\"item.taobao.com\"]": 10},
            "bodyText": "商品列表",
        }

        evaluate_results = iter([fp_result, pt_result])

        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=lambda _: next(evaluate_results))
        mock_page.goto = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.screenshot = AsyncMock()
        mock_page.close = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        mock_crawler = MagicMock()
        mock_crawler._new_context = AsyncMock(return_value=mock_context)
        mock_crawler.load_cookies = AsyncMock()
        mock_crawler.load_storage_state = AsyncMock(return_value=True)
        mock_crawler._browser_manager = MagicMock()
        mock_crawler._browser_manager._persistent = True
        mock_crawler._browser_manager._persistent_ctx = MagicMock()
        mock_crawler._browser_manager._browser = None
        mock_crawler._browser_manager._user_data_dir = "./storage/browser_profile"
        mock_crawler.close = AsyncMock()

        sys.argv = ["diag.py"]
        save_dir = tmp_path / "taobao_debug"
        with (
            patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler),
            patch("diagnose_browser_env.DEBUG_DIR", save_dir),
        ):
            result = await diagnose_browser_env.main()

        assert result == 0
        out = capsys.readouterr().out
        assert "搜索结果页 [OK]" in out
        assert "浏览器指纹" in out
        # Screenshot should have been taken
        mock_page.screenshot.assert_awaited_once()
        # Report JSON should exist
        report_files = list(save_dir.glob("browser_env_report_*.json"))
        assert len(report_files) == 1
        report = json.loads(report_files[0].read_text(encoding="utf-8"))
        assert "fingerprint" in report
        assert "page_type" in report

    @pytest.mark.asyncio
    async def test_webdriver_warning_in_summary(self, tmp_path, capsys):
        """webdriver=true 时总结应包含警告。"""
        fp_result = {
            "userAgent": "HeadlessChrome/125",
            "platform": "Linux",
            "vendor": "Google",
            "webdriver": True,
            "language": "en",
            "languages": ["en"],
            "timezone": "UTC",
            "timezoneOffset": 0,
            "screenWidth": 1280, "screenHeight": 720,
            "screenAvailWidth": 1280, "screenAvailHeight": 720,
            "innerWidth": 1280, "innerHeight": 720,
            "outerWidth": 1280, "outerHeight": 720,
            "devicePixelRatio": 1,
            "screenColorDepth": 24,
            "maxTouchPoints": 0,
            "hardwareConcurrency": 2,
            "deviceMemory": 2,
            "connectionType": "not available",
            "pluginCount": 0,
            "mimeTypesCount": 0,
            "pluginNames": [],
            "hasChrome": False,
            "hasChromeRuntime": False,
            "cookieEnabled": True,
            "doNotTrack": None,
            "permissionsAvailable": False,
            "documentHidden": False,
            "visibilityState": "visible",
            "ontouchstart": False,
            "canvasHash": 200,
            "webglVendor": "Google Inc.",
            "webglRenderer": "Google SwiftShader",
        }
        pt_result = {
            "url": "about:blank",
            "title": "",
            "totalElements": 0,
            "hasJItemList": False,
            "hasLoginPrompt": False,
            "hasCaptcha": False,
            "cardCounts": {},
            "bodyText": "",
        }

        evaluate_results = iter([fp_result, pt_result])

        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=lambda _: next(evaluate_results))
        mock_page.goto = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.screenshot = AsyncMock()
        mock_page.close = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        mock_crawler = MagicMock()
        mock_crawler._new_context = AsyncMock(return_value=mock_context)
        mock_crawler.load_cookies = AsyncMock()
        mock_crawler.load_storage_state = AsyncMock(return_value=True)
        mock_crawler._browser_manager = MagicMock()
        mock_crawler._browser_manager._persistent = True
        mock_crawler._browser_manager._persistent_ctx = MagicMock()
        mock_crawler._browser_manager._browser = None
        mock_crawler._browser_manager._user_data_dir = "./storage/browser_profile"
        mock_crawler.close = AsyncMock()

        sys.argv = ["diag.py", "--no-navigate"]
        with patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler):
            result = await diagnose_browser_env.main()

        assert result == 0
        out = capsys.readouterr().out
        assert "navigator.webdriver=true" in out or "[!!]" in out

    @pytest.mark.asyncio
    async def test_exception_returns_1(self):
        """异常时返回 1。"""
        mock_crawler = MagicMock()
        mock_crawler._new_context = AsyncMock(side_effect=RuntimeError("browser crash"))
        mock_crawler.close = AsyncMock()

        sys.argv = ["diag.py", "--no-navigate"]
        with patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler):
            result = await diagnose_browser_env.main()

        assert result == 1

    @pytest.mark.asyncio
    async def test_close_always_called(self):
        """无论成功或失败，资源都应被清理。"""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value={
            "userAgent": "test", "platform": "test", "vendor": "test",
            "webdriver": False, "language": "en", "languages": ["en"],
            "timezone": "UTC", "timezoneOffset": 0,
            "screenWidth": 800, "screenHeight": 600,
            "screenAvailWidth": 800, "screenAvailHeight": 600,
            "innerWidth": 800, "innerHeight": 600,
            "outerWidth": 800, "outerHeight": 600,
            "devicePixelRatio": 1, "screenColorDepth": 24, "maxTouchPoints": 0,
            "hardwareConcurrency": 2, "deviceMemory": 2,
            "connectionType": "not available",
            "pluginCount": 0, "mimeTypesCount": 0, "pluginNames": [],
            "hasChrome": False, "hasChromeRuntime": False,
            "cookieEnabled": True, "doNotTrack": None,
            "permissionsAvailable": False,
            "documentHidden": False, "visibilityState": "visible",
            "ontouchstart": False, "canvasHash": 200,
            "webglVendor": "test", "webglRenderer": "test",
        })
        mock_page.goto = AsyncMock()
        mock_page.close = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        mock_crawler = MagicMock()
        mock_crawler._new_context = AsyncMock(return_value=mock_context)
        mock_crawler.load_cookies = AsyncMock()
        mock_crawler.load_storage_state = AsyncMock(return_value=True)
        mock_crawler._browser_manager = MagicMock()
        mock_crawler._browser_manager._persistent = True
        mock_crawler._browser_manager._persistent_ctx = MagicMock()
        mock_crawler._browser_manager._browser = None
        mock_crawler._browser_manager._user_data_dir = "./storage/browser_profile"
        mock_crawler.close = AsyncMock()

        sys.argv = ["diag.py", "--no-navigate"]
        with patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler):
            await diagnose_browser_env.main()

        mock_page.close.assert_awaited_once()
        mock_context.close.assert_awaited_once()
        mock_crawler.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_report_json_contains_config(self, tmp_path):
        """报告 JSON 应包含配置信息。"""
        fp_result = {
            "userAgent": "test", "platform": "test", "vendor": "test",
            "webdriver": False, "language": "en", "languages": ["en"],
            "timezone": "UTC", "timezoneOffset": 0,
            "screenWidth": 800, "screenHeight": 600,
            "screenAvailWidth": 800, "screenAvailHeight": 600,
            "innerWidth": 800, "innerHeight": 600,
            "outerWidth": 800, "outerHeight": 600,
            "devicePixelRatio": 1, "screenColorDepth": 24, "maxTouchPoints": 0,
            "hardwareConcurrency": 2, "deviceMemory": 2,
            "connectionType": "not available",
            "pluginCount": 0, "mimeTypesCount": 0, "pluginNames": [],
            "hasChrome": False, "hasChromeRuntime": False,
            "cookieEnabled": True, "doNotTrack": None,
            "permissionsAvailable": False,
            "documentHidden": False, "visibilityState": "visible",
            "ontouchstart": False, "canvasHash": 200,
            "webglVendor": "test", "webglRenderer": "test",
        }
        pt_result = {
            "url": "test", "title": "test", "totalElements": 0,
            "hasJItemList": False, "hasLoginPrompt": False, "hasCaptcha": False,
            "cardCounts": {}, "bodyText": "",
        }

        evaluate_results = iter([fp_result, pt_result])
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=lambda _: next(evaluate_results))
        mock_page.goto = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.screenshot = AsyncMock()
        mock_page.close = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        mock_crawler = MagicMock()
        mock_crawler._new_context = AsyncMock(return_value=mock_context)
        mock_crawler.load_cookies = AsyncMock()
        mock_crawler.load_storage_state = AsyncMock(return_value=True)
        mock_crawler._browser_manager = MagicMock()
        mock_crawler._browser_manager._persistent = True
        mock_crawler._browser_manager._persistent_ctx = MagicMock()
        mock_crawler._browser_manager._browser = None
        mock_crawler._browser_manager._user_data_dir = "./storage/browser_profile"
        mock_crawler.close = AsyncMock()

        save_dir = tmp_path / "taobao_debug"
        sys.argv = ["diag.py"]
        with (
            patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler),
            patch("diagnose_browser_env.DEBUG_DIR", save_dir),
        ):
            await diagnose_browser_env.main()

        report_files = list(save_dir.glob("browser_env_report_*.json"))
        assert len(report_files) == 1
        report = json.loads(report_files[0].read_text(encoding="utf-8"))
        assert "config" in report
        assert "browser_headless" in report["config"]
        assert "fingerprint" in report
        assert "page_type" in report
        assert "webdriver" in report["fingerprint"]

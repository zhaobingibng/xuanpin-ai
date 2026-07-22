"""Tests for scripts/test_taobao_human_search.py — 淘宝拟人搜索诊断脚本。"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import test_taobao_human_search  # noqa: E402


# ── Constants ───────────────────────────────────────────────────


class TestConstants:
    """验证脚本常量和选择器定义。"""

    def test_search_input_selectors_defined(self):
        """应定义搜索输入框选择器列表。"""
        assert len(test_taobao_human_search.SEARCH_INPUT_SELECTORS) >= 3
        assert "#q" in test_taobao_human_search.SEARCH_INPUT_SELECTORS

    def test_search_button_selectors_defined(self):
        """应定义搜索按钮选择器列表。"""
        assert len(test_taobao_human_search.SEARCH_BUTTON_SELECTORS) >= 3
        assert "button[type='submit']" in test_taobao_human_search.SEARCH_BUTTON_SELECTORS

    def test_dirs_configured(self):
        """应配置正确的输出目录。"""
        assert "taobao_debug" in str(test_taobao_human_search.DEBUG_DIR)


# ── parse_args ──────────────────────────────────────────────────


class TestParseArgs:
    """验证命令行参数解析。"""

    def test_default_keyword(self):
        args = test_taobao_human_search.parse_args([])
        assert args.keyword == "海苔卷"

    def test_custom_keyword(self):
        sys.argv = ["search.py", "--keyword", "蓝牙耳机"]
        args = test_taobao_human_search.parse_args()
        assert args.keyword == "蓝牙耳机"

    def test_default_wait(self):
        args = test_taobao_human_search.parse_args([])
        assert args.wait_min == 3.0
        assert args.wait_max == 5.0

    def test_custom_wait(self):
        sys.argv = ["search.py", "--wait-min", "2.0", "--wait-max", "4.0"]
        args = test_taobao_human_search.parse_args()
        assert args.wait_min == 2.0
        assert args.wait_max == 4.0

    def test_default_result_wait(self):
        args = test_taobao_human_search.parse_args([])
        assert args.result_wait == 10.0

    def test_custom_result_wait(self):
        sys.argv = ["search.py", "--result-wait", "15.0"]
        args = test_taobao_human_search.parse_args()
        assert args.result_wait == 15.0

    def test_no_save_default(self):
        args = test_taobao_human_search.parse_args([])
        assert args.no_save is False

    def test_no_save_enabled(self):
        sys.argv = ["search.py", "--no-save"]
        args = test_taobao_human_search.parse_args()
        assert args.no_save is True


# ── _type_human / _try_find ─────────────────────────────────────


class TestHumanTyping:
    """验证拟人输入辅助函数。"""

    @pytest.mark.asyncio
    async def test_type_human_clears_first(self):
        """应先清空输入框再逐字输入。"""
        mock_page = AsyncMock()
        mock_page.fill = AsyncMock()
        mock_page.type = AsyncMock()
        mock_page.click = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()

        await test_taobao_human_search._type_human(mock_page, "#q", "海苔")

        mock_page.click.assert_awaited_once_with("#q")
        mock_page.fill.assert_awaited_once_with("#q", "")
        # Should type each character
        assert mock_page.type.await_count == 2  # 海, 苔

    @pytest.mark.asyncio
    async def test_try_find_returns_first_match(self):
        """应返回第一个匹配的选择器。"""
        mock_page = AsyncMock()
        mock_element = MagicMock()
        mock_page.query_selector = AsyncMock(side_effect=lambda sel: (
            mock_element if sel == "#q" else None
        ))

        result = await test_taobao_human_search._try_find(
            mock_page, ["#q", "input[name='q']", ".search-input"]
        )
        assert result == "#q"
        assert mock_page.query_selector.await_count == 1  # stops at first match

    @pytest.mark.asyncio
    async def test_try_find_none_matched(self):
        """无匹配应返回 None。"""
        mock_page = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=None)

        result = await test_taobao_human_search._try_find(
            mock_page, ["#q", "input[name='q']"]
        )
        assert result is None
        assert mock_page.query_selector.await_count == 2


# ── main() ──────────────────────────────────────────────────────


class TestMain:
    """验证 main() 函数的主要路径。"""

    @pytest.fixture(autouse=True)
    def _reset_sys_argv(self):
        """每个测试后重置 sys.argv。"""
        orig = sys.argv[:]
        yield
        sys.argv = orig

    def _make_mock_page(
        self,
        html: str = "<html></html>",
        title: str = "海苔卷-淘宝搜索",
        url: str = "https://s.taobao.com/search?q=海苔卷",
    ):
        """创建模拟 page 对象。"""
        mock_page = AsyncMock()
        mock_page.title = AsyncMock(return_value=title)
        mock_page.url = url
        mock_page.content = AsyncMock(return_value=html)
        mock_page.screenshot = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.click = AsyncMock()
        mock_page.fill = AsyncMock()
        mock_page.type = AsyncMock()
        mock_page.press = AsyncMock()
        mock_page.close = AsyncMock()
        return mock_page

    def _make_mock_crawler(self, mock_context):
        """创建模拟 TaobaoCrawler。"""
        mock_crawler = MagicMock()
        mock_crawler._new_context = AsyncMock(return_value=mock_context)
        mock_crawler.load_cookies = AsyncMock()
        mock_crawler.load_storage_state = AsyncMock(return_value=True)
        mock_crawler.close = AsyncMock()
        return mock_crawler

    @pytest.mark.asyncio
    async def test_successful_human_search_with_products(self, tmp_path, capsys):
        """拟人搜索成功找到商品链接 — 返回 0。"""
        mock_page = self._make_mock_page(
            html=(
                '<html><head><title>海苔卷-淘宝搜索</title></head>'
                '<body><div class="J_ItemList">'
                '<a href="//item.taobao.com/item.htm?id=1">商品1</a>'
                '<a href="//item.taobao.com/item.htm?id=2">商品2</a>'
                '<a href="//detail.tmall.com/item.htm?id=3">商品3</a>'
                '</div></body></html>'
            ),
        )
        # Mock search input and button found
        input_el = MagicMock()
        btn_el = MagicMock()
        mock_page.query_selector = AsyncMock(side_effect=lambda sel: (
            input_el if "input" in sel or sel == "#q"
            else btn_el if "btn" in sel or "submit" in sel or "button" in sel
            else None
        ))

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_crawler = self._make_mock_crawler(mock_context)

        sys.argv = ["search.py"]
        with (
            patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler),
            patch("test_taobao_human_search.DEBUG_DIR", tmp_path / "taobao_debug"),
        ):
            result = await test_taobao_human_search.main()

        assert result == 0
        out = capsys.readouterr().out
        # Product link count includes both href-prefix matches and full URL matches
        assert "商品链接数:" in out
        assert "item.taobao.com: 是" in out
        assert "登录页: 否" in out

    @pytest.mark.asyncio
    async def test_login_page_detected(self, tmp_path, capsys):
        """登录页应被正确检测。"""
        mock_page = self._make_mock_page(
            html=(
                '<html><head><title>登录</title></head>'
                '<body>'
                + "site-nav-login " * 15
                + '<a href="https://login.taobao.com/">亲，请登录</a>'
                '</body></html>'
            ),
            title="登录-淘宝",
            url="https://login.taobao.com/",
        )
        mock_page.query_selector = AsyncMock(side_effect=lambda sel: (
            MagicMock() if "input" in sel or sel == "#q" else None
        ))

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_crawler = self._make_mock_crawler(mock_context)

        sys.argv = ["search.py"]
        with (
            patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler),
            patch("test_taobao_human_search.DEBUG_DIR", tmp_path / "taobao_debug"),
        ):
            result = await test_taobao_human_search.main()

        assert result == 0
        out = capsys.readouterr().out
        assert "登录页: 是" in out

    @pytest.mark.asyncio
    async def test_captcha_page_detected(self, tmp_path, capsys):
        """验证码/风控页应被正确检测。"""
        mock_page = self._make_mock_page(
            html=(
                '<html><head><title></title></head>'
                '<body>检测到异常流量，请点击按钮进行验证'
                '<a href="https://sec.taobao.com/query">滑块验证</a>'
                '</body></html>'
            ),
            title="",
        )
        mock_page.query_selector = AsyncMock(side_effect=lambda sel: (
            MagicMock() if "input" in sel or sel == "#q" else None
        ))

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_crawler = self._make_mock_crawler(mock_context)

        sys.argv = ["search.py"]
        with (
            patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler),
            patch("test_taobao_human_search.DEBUG_DIR", tmp_path / "taobao_debug"),
        ):
            result = await test_taobao_human_search.main()

        assert result == 0
        out = capsys.readouterr().out
        assert "验证码: 是" in out

    @pytest.mark.asyncio
    async def test_input_not_found_returns_1(self, tmp_path, capsys):
        """未找到搜索输入框应返回 1。"""
        mock_page = self._make_mock_page()
        mock_page.query_selector = AsyncMock(return_value=None)

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_crawler = self._make_mock_crawler(mock_context)

        sys.argv = ["search.py"]
        with (
            patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler),
            patch("test_taobao_human_search.DEBUG_DIR", tmp_path / "taobao_debug"),
        ):
            result = await test_taobao_human_search.main()

        assert result == 1
        out = capsys.readouterr().out
        assert "未找到搜索输入框" in out

    @pytest.mark.asyncio
    async def test_button_fallback_to_enter(self, tmp_path, capsys):
        """搜索按钮未找到时回退到 Enter 键。"""
        mock_page = self._make_mock_page(
            html=(
                '<html><head><title>结果</title></head>'
                '<body><div class="J_ItemList">'
                '<a href="//item.taobao.com/item.htm?id=1">商品1</a>'
                '</div></body></html>'
            ),
        )
        # input found, button NOT found
        input_el = MagicMock()
        mock_page.query_selector = AsyncMock(side_effect=lambda sel: (
            input_el if "input" in sel or sel == "#q" else None
        ))

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_crawler = self._make_mock_crawler(mock_context)

        sys.argv = ["search.py"]
        with (
            patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler),
            patch("test_taobao_human_search.DEBUG_DIR", tmp_path / "taobao_debug"),
        ):
            result = await test_taobao_human_search.main()

        assert result == 0
        mock_page.press.assert_awaited_once_with("#q", "Enter")

    @pytest.mark.asyncio
    async def test_no_save_skips_files(self, tmp_path, capsys):
        """--no-save 应跳过文件保存。"""
        mock_page = self._make_mock_page()
        mock_page.query_selector = AsyncMock(side_effect=lambda sel: (
            MagicMock() if ("input" in sel or sel == "#q" or "btn" in sel or "submit" in sel or "button" in sel)
            else None
        ))

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_crawler = self._make_mock_crawler(mock_context)

        sys.argv = ["search.py", "--no-save"]
        save_dir = tmp_path / "taobao_debug"
        with (
            patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler),
            patch("test_taobao_human_search.DEBUG_DIR", save_dir),
        ):
            result = await test_taobao_human_search.main()

        assert result == 0
        mock_page.screenshot.assert_not_awaited()
        assert not save_dir.exists()

    @pytest.mark.asyncio
    async def test_saves_report_json(self, tmp_path):
        """应生成 human_search_report.json。"""
        mock_page = self._make_mock_page(
            html=(
                '<html><head><title>海苔卷-淘宝搜索</title></head>'
                '<body><a href="//item.taobao.com/item.htm?id=1">商品1</a></body></html>'
            ),
        )
        mock_page.query_selector = AsyncMock(side_effect=lambda sel: (
            MagicMock() if ("input" in sel or sel == "#q" or "btn" in sel or "submit" in sel or "button" in sel)
            else None
        ))

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_crawler = self._make_mock_crawler(mock_context)

        save_dir = tmp_path / "taobao_debug"
        sys.argv = ["search.py"]
        with (
            patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler),
            patch("test_taobao_human_search.DEBUG_DIR", save_dir),
        ):
            await test_taobao_human_search.main()

        report_path = save_dir / "human_search_report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["keyword"] == "海苔卷"
        assert "product_link_count" in report
        assert "has_product_links" in report
        assert "is_login_page" in report
        assert "is_captcha_page" in report
        assert "steps" in report

    @pytest.mark.asyncio
    async def test_saves_screenshot_and_html(self, tmp_path):
        """应保存截图和 HTML 文件。"""
        mock_page = self._make_mock_page(
            html=(
                '<html><head><title>测试</title></head>'
                '<body><a href="//item.taobao.com/item.htm?id=1">商品1</a></body></html>'
            ),
        )
        mock_page.query_selector = AsyncMock(side_effect=lambda sel: (
            MagicMock() if ("input" in sel or sel == "#q" or "btn" in sel or "submit" in sel or "button" in sel)
            else None
        ))

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_crawler = self._make_mock_crawler(mock_context)

        save_dir = tmp_path / "taobao_debug"
        sys.argv = ["search.py"]
        with (
            patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler),
            patch("test_taobao_human_search.DEBUG_DIR", save_dir),
        ):
            await test_taobao_human_search.main()

        # Mock screenshot doesn't write files — verify it was called instead
        mock_page.screenshot.assert_awaited()
        assert (save_dir / "human_search_report.json").exists()
        assert (save_dir / "human_search.html").exists()

    @pytest.mark.asyncio
    async def test_exception_returns_1(self, tmp_path, capsys):
        """异常应返回 1 并打印错误。"""
        mock_page = self._make_mock_page()
        # Make goto succeed, but then query_selector raises (simulating
        # context crash after homepage loads)
        mock_page.query_selector = AsyncMock(side_effect=RuntimeError("Simulated crash"))

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_crawler = self._make_mock_crawler(mock_context)

        sys.argv = ["search.py"]
        with (
            patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler),
            patch("test_taobao_human_search.DEBUG_DIR", tmp_path / "taobao_debug"),
        ):
            result = await test_taobao_human_search.main()

        assert result == 1
        out = capsys.readouterr().out
        # _try_find catches exceptions internally → shows "未找到" not "诊断失败"
        assert "未找到搜索输入框" in out

    @pytest.mark.asyncio
    async def test_close_always_called(self, tmp_path):
        """即使异常，close 也应被调用。"""
        mock_page = self._make_mock_page()
        mock_page.query_selector = AsyncMock(side_effect=RuntimeError("Simulated crash"))

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_crawler = self._make_mock_crawler(mock_context)

        sys.argv = ["search.py"]
        with (
            patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler),
            patch("test_taobao_human_search.DEBUG_DIR", tmp_path / "taobao_debug"),
        ):
            await test_taobao_human_search.main()

        mock_page.close.assert_awaited()
        mock_context.close.assert_awaited()
        mock_crawler.close.assert_awaited()

    @pytest.mark.asyncio
    async def test_zero_products_still_succeeds(self, tmp_path, capsys):
        """0 个商品链接仍应返回 0（不是错误）。"""
        mock_page = self._make_mock_page(
            html="<html><body>empty page</body></html>",
            title="淘宝网",
        )
        mock_page.query_selector = AsyncMock(side_effect=lambda sel: (
            MagicMock() if ("input" in sel or sel == "#q" or "btn" in sel or "submit" in sel or "button" in sel)
            else None
        ))

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_crawler = self._make_mock_crawler(mock_context)

        sys.argv = ["search.py"]
        with (
            patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler),
            patch("test_taobao_human_search.DEBUG_DIR", tmp_path / "taobao_debug"),
        ):
            result = await test_taobao_human_search.main()

        assert result == 0
        out = capsys.readouterr().out
        assert "商品链接数: 0" in out

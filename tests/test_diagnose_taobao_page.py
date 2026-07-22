"""Tests for scripts/diagnose_taobao_page.py — 淘宝页面 DOM 诊断脚本。"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import diagnose_taobao_page  # noqa: E402


# ── _count_keywords ──────────────────────────────────────────────


class TestCountKeywords:
    """验证 _count_keywords 关键词统计逻辑。"""

    def test_empty_html(self):
        """空 HTML 应返回全 0 计数。"""
        counts = diagnose_taobao_page._count_keywords("")
        assert all(v == 0 for v in counts.values())
        assert len(counts) > 0

    def test_product_links_counted(self):
        """应正确统计商品链接数量。"""
        html = (
            '<a href="//item.taobao.com/item.htm?id=123">商品1</a>'
            '<a href="//item.taobao.com/item.htm?id=456">商品2</a>'
            '<a href="//detail.tmall.com/item.htm?id=789">商品3</a>'
        )
        counts = diagnose_taobao_page._count_keywords(html)
        assert counts['href="//item.taobao.com'] == 2
        assert counts['href="//detail.tmall.com'] == 1

    def test_j_itemlist_detected(self):
        """应检测 J_ItemList 容器。"""
        html = '<div class="J_ItemList">content</div>'
        counts = diagnose_taobao_page._count_keywords(html)
        assert counts["J_ItemList"] == 1

    def test_block_keywords_detected(self):
        """应检测风控关键词。"""
        html = '<meta http-equiv="refresh" content="0;url=https://sec.taobao.com">'
        counts = diagnose_taobao_page._count_keywords(html)
        assert counts["sec.taobao.com"] == 1

    def test_login_prompt_detected(self):
        """应检测登录提示。"""
        html = '<div>亲，请登录</div>'
        counts = diagnose_taobao_page._count_keywords(html)
        assert counts["亲，请登录"] == 1

    def test_verify_code_detected(self):
        """应检测验证码/滑块。"""
        html = '<div>请输入验证码</div><div>滑块验证</div>'
        counts = diagnose_taobao_page._count_keywords(html)
        assert counts["验证码"] == 1
        assert counts["滑块验证"] == 1

    def test_case_insensitive(self):
        """正则匹配应忽略大小写。"""
        html = '<DIV CLASS="J_ITEMLIST">data-item="123"</DIV>'
        counts = diagnose_taobao_page._count_keywords(html)
        assert counts["J_ItemList"] == 1

    def test_all_keys_present(self):
        """结果字典应包含所有预定义关键词。"""
        counts = diagnose_taobao_page._count_keywords("test")
        for key in diagnose_taobao_page.KEYWORD_PATTERNS:
            assert key in counts, f"Missing key: {key}"


# ── parse_args ──────────────────────────────────────────────────


class TestParseArgs:
    """验证命令行参数解析。"""

    def test_default_keyword(self):
        args = diagnose_taobao_page.parse_args([])
        assert args.keyword == "海苔卷"

    def test_custom_keyword(self):
        sys.argv = ["diag.py", "--keyword", "蓝牙耳机"]
        args = diagnose_taobao_page.parse_args()
        assert args.keyword == "蓝牙耳机"

    def test_default_timeout(self):
        args = diagnose_taobao_page.parse_args([])
        assert args.timeout == 10

    def test_custom_timeout(self):
        sys.argv = ["diag.py", "--timeout", "15"]
        args = diagnose_taobao_page.parse_args()
        assert args.timeout == 15

    def test_no_save_flag(self):
        args = diagnose_taobao_page.parse_args([])
        assert args.no_save is False

    def test_no_save_enabled(self):
        sys.argv = ["diag.py", "--no-save"]
        args = diagnose_taobao_page.parse_args()
        assert args.no_save is True


# ── main() ──────────────────────────────────────────────────────


class TestMain:
    """验证 main() 函数的主要路径。"""

    @pytest.mark.asyncio
    async def test_successful_diagnosis(self, tmp_path, capsys):
        """正常诊断流程应返回 0，输出诊断信息。"""
        mock_page = AsyncMock()
        mock_page.title = AsyncMock(return_value="海苔卷-淘宝搜索")
        mock_page.url = "https://s.taobao.com/search?q=海苔卷"
        mock_page.content = AsyncMock(return_value=(
            '<html><head><title>海苔卷</title></head>'
            '<body><div class="J_ItemList">'
            '<a href="//item.taobao.com/item.htm?id=1">商品1</a>'
            '<a href="//item.taobao.com/item.htm?id=2">商品2</a>'
            '<span>¥29.90</span>'
            '</div></body></html>'
        ))
        mock_page.screenshot = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.goto = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_crawler = MagicMock()
        mock_crawler._new_context = AsyncMock(return_value=mock_context)
        mock_crawler.load_cookies = AsyncMock()
        mock_crawler.load_storage_state = AsyncMock(return_value=True)
        mock_crawler.close = AsyncMock()

        sys.argv = ["diag.py"]
        with (
            patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler),
            patch("diagnose_taobao_page.DEBUG_DIR", tmp_path / "taobao_debug"),
        ):
            result = await diagnose_taobao_page.main()

        assert result == 0
        out = capsys.readouterr().out
        assert "海苔卷-淘宝搜索" in out
        assert "J_ItemList" in out
        assert "HTML 大小" in out

    @pytest.mark.asyncio
    async def test_url_redirect_detected(self, tmp_path, capsys):
        """URL 跳转应被检测到并警告。"""
        mock_page = AsyncMock()
        mock_page.title = AsyncMock(return_value="登录-淘宝")
        mock_page.url = "https://login.taobao.com/"  # redirected!
        mock_page.content = AsyncMock(return_value="<html>login page</html>")
        mock_page.screenshot = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.goto = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_crawler = MagicMock()
        mock_crawler._new_context = AsyncMock(return_value=mock_context)
        mock_crawler.load_cookies = AsyncMock()
        mock_crawler.load_storage_state = AsyncMock(return_value=True)
        mock_crawler.close = AsyncMock()

        sys.argv = ["diag.py"]
        with (
            patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler),
            patch("diagnose_taobao_page.DEBUG_DIR", tmp_path / "taobao_debug"),
        ):
            result = await diagnose_taobao_page.main()

        assert result == 0
        out = capsys.readouterr().out
        assert "URL 已跳转" in out

    @pytest.mark.asyncio
    async def test_block_detected(self, tmp_path, capsys):
        """风控拦截应被检测到。"""
        mock_page = AsyncMock()
        mock_page.title = AsyncMock(return_value="")
        mock_page.url = "https://sec.taobao.com/query"
        mock_page.content = AsyncMock(return_value=(
            '<html>sec.taobao.com 验证码</html>'
        ))
        mock_page.screenshot = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.goto = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_crawler = MagicMock()
        mock_crawler._new_context = AsyncMock(return_value=mock_context)
        mock_crawler.load_cookies = AsyncMock()
        mock_crawler.load_storage_state = AsyncMock(return_value=True)
        mock_crawler.close = AsyncMock()

        sys.argv = ["diag.py"]
        with (
            patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler),
            patch("diagnose_taobao_page.DEBUG_DIR", tmp_path / "taobao_debug"),
        ):
            result = await diagnose_taobao_page.main()

        assert result == 0
        out = capsys.readouterr().out
        assert "风控拦截" in out
        assert "是" in out or "[!!]" in out

    @pytest.mark.asyncio
    async def test_no_save_skips_files(self, tmp_path, capsys):
        """--no-save 应跳过文件保存。"""
        mock_page = AsyncMock()
        mock_page.title = AsyncMock(return_value="test")
        mock_page.url = "https://s.taobao.com/search"
        mock_page.content = AsyncMock(return_value="<html></html>")
        mock_page.screenshot = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.goto = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_crawler = MagicMock()
        mock_crawler._new_context = AsyncMock(return_value=mock_context)
        mock_crawler.load_cookies = AsyncMock()
        mock_crawler.load_storage_state = AsyncMock(return_value=True)
        mock_crawler.close = AsyncMock()

        sys.argv = ["diag.py", "--no-save"]
        save_dir = tmp_path / "taobao_debug"
        with (
            patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler),
            patch("diagnose_taobao_page.DEBUG_DIR", save_dir),
        ):
            result = await diagnose_taobao_page.main()

        assert result == 0
        mock_page.screenshot.assert_not_awaited()
        # Directory should NOT exist (no save = no mkdir)
        assert not save_dir.exists()

    @pytest.mark.asyncio
    async def test_saves_html_and_screenshot(self, tmp_path, capsys):
        """默认应保存 HTML 和截图。"""
        html_content = "<html><div class='J_ItemList'>items</div></html>"

        mock_page = AsyncMock()
        mock_page.title = AsyncMock(return_value="test")
        mock_page.url = "https://s.taobao.com/search"
        mock_page.content = AsyncMock(return_value=html_content)
        mock_page.screenshot = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.goto = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_crawler = MagicMock()
        mock_crawler._new_context = AsyncMock(return_value=mock_context)
        mock_crawler.load_cookies = AsyncMock()
        mock_crawler.load_storage_state = AsyncMock(return_value=True)
        mock_crawler.close = AsyncMock()

        sys.argv = ["diag.py"]
        save_dir = tmp_path / "taobao_debug"
        with (
            patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler),
            patch("diagnose_taobao_page.DEBUG_DIR", save_dir),
        ):
            result = await diagnose_taobao_page.main()

        assert result == 0
        mock_page.screenshot.assert_awaited_once()
        # Verify screenshot path contains keyword (no file check — mock doesn't write)
        assert "taobao_search_" in str(mock_page.screenshot.await_args.kwargs["path"])
        assert (save_dir / "taobao_search_海苔卷.html").exists()

    @pytest.mark.asyncio
    async def test_exception_returns_1(self):
        """异常时返回 1。"""
        mock_crawler = MagicMock()
        mock_crawler._new_context = AsyncMock(side_effect=RuntimeError("browser crash"))
        mock_crawler.close = AsyncMock()

        sys.argv = ["diag.py"]
        with patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler):
            result = await diagnose_taobao_page.main()

        assert result == 1

    @pytest.mark.asyncio
    async def test_close_always_called(self):
        """无论成功或失败，所有资源都应被关闭。"""
        mock_page = AsyncMock()
        mock_page.close = AsyncMock()

        mock_context = AsyncMock()
        mock_context.close = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_crawler = MagicMock()
        mock_crawler._new_context = AsyncMock(return_value=mock_context)
        mock_crawler.load_cookies = AsyncMock()
        mock_crawler.load_storage_state = AsyncMock(return_value=True)
        mock_crawler.close = AsyncMock()

        mock_page.title = AsyncMock(return_value="ok")
        mock_page.url = "https://s.taobao.com/search"
        mock_page.content = AsyncMock(return_value="<html></html>")
        mock_page.screenshot = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.goto = AsyncMock()

        sys.argv = ["diag.py", "--no-save"]
        with patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler):
            await diagnose_taobao_page.main()

        mock_page.close.assert_awaited_once()
        mock_context.close.assert_awaited_once()
        mock_crawler.close.assert_awaited_once()


# ── Constants ───────────────────────────────────────────────────


class TestConstants:
    """验证脚本常量。"""

    def test_debug_dir_path(self):
        assert "taobao_debug" in str(diagnose_taobao_page.DEBUG_DIR)
        assert "storage" in str(diagnose_taobao_page.DEBUG_DIR)

    def test_search_url(self):
        assert diagnose_taobao_page.SEARCH_URL == "https://s.taobao.com/search"

    def test_keyword_patterns_complete(self):
        """KEYWORD_PATTERNS 应覆盖所有必要的诊断维度。"""
        assert len(diagnose_taobao_page.KEYWORD_PATTERNS) >= 15
        # Must include product detection keys
        keys_text = " ".join(diagnose_taobao_page.KEYWORD_PATTERNS.keys())
        for essential in ["J_ItemList", "data-item", "月销", "item.taobao.com"]:
            assert essential in keys_text, f"Missing essential key: {essential}"

"""Tests for scripts/test_taobao_crawl.py — 淘宝采集验证脚本。"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Import script module ────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import test_taobao_crawl  # noqa: E402


# ── parse_args ──────────────────────────────────────────────────


class TestParseArgs:
    """验证命令行参数解析。"""

    def test_default_keyword(self):
        """--keyword 默认值应为 '海苔卷'。"""
        args = test_taobao_crawl.parse_args([])
        assert args.keyword == "海苔卷"

    def test_default_limit(self):
        """--limit 默认值应为 10。"""
        args = test_taobao_crawl.parse_args([])
        assert args.limit == 10

    def test_default_save_json_false(self):
        """--save-json 默认为 False。"""
        args = test_taobao_crawl.parse_args([])
        assert args.save_json is False

    def test_custom_keyword(self):
        """应支持自定义关键词。"""
        sys.argv = ["test_taobao_crawl.py", "--keyword", "蓝牙耳机"]
        args = test_taobao_crawl.parse_args()
        assert args.keyword == "蓝牙耳机"

    def test_custom_limit(self):
        """应支持自定义 limit。"""
        sys.argv = ["test_taobao_crawl.py", "--limit", "5"]
        args = test_taobao_crawl.parse_args()
        assert args.limit == 5

    def test_save_json_flag(self):
        """应支持 --save-json 标志。"""
        sys.argv = ["test_taobao_crawl.py", "--save-json"]
        args = test_taobao_crawl.parse_args()
        assert args.save_json is True


# ── _print_product ──────────────────────────────────────────────


class TestPrintProduct:
    """验证 _print_product 格式化输出。"""

    def test_basic_product(self, capsys):
        """应输出标题、价格、店铺、URL。"""
        p = MagicMock()
        p.name = "海苔卷零食大礼包"
        p.price = 29.90
        p.shop = "海苔专卖店"
        p.url = "https://item.taobao.com/123"

        test_taobao_crawl._print_product(1, p)
        out = capsys.readouterr().out

        assert "1." in out
        assert "海苔卷零食大礼包" in out
        assert "29.90" in out
        assert "海苔专卖店" in out
        assert "https://item.taobao.com/123" in out

    def test_long_name_truncated(self, capsys):
        """超长标题应被截断并显示 '...'。"""
        p = MagicMock()
        p.name = "超长商品名称" * 10  # ~70 chars
        p.price = 9.90
        p.shop = "测试店"
        p.url = None

        test_taobao_crawl._print_product(1, p, max_name_len=20)
        out = capsys.readouterr().out

        # Should contain truncation indicator
        assert "..." in out
        # Should not contain the full name
        assert len([c for c in out.split("  ") if "超长" in c][0]) < len(p.name)

    def test_no_url_shows_dash(self, capsys):
        """无 URL 时显示 '—'。"""
        p = MagicMock()
        p.name = "测试商品"
        p.price = 10.00
        p.shop = "店铺"
        p.url = None

        test_taobao_crawl._print_product(1, p, max_name_len=40)
        out = capsys.readouterr().out

        assert "—" in out

    def test_index_numbering(self, capsys):
        """序号应正确递增。"""
        for i in range(1, 4):
            p = MagicMock()
            p.name = f"商品{i}"
            p.price = 10.0
            p.shop = "店"
            p.url = None
            test_taobao_crawl._print_product(i, p, max_name_len=40)

        out = capsys.readouterr().out
        assert " 1." in out
        assert " 2." in out
        assert " 3." in out


# ── _print_header ───────────────────────────────────────────────


class TestPrintHeader:
    """验证 _print_header 输出格式。"""

    def test_header_format(self, capsys):
        test_taobao_crawl._print_header("测试标题")
        out = capsys.readouterr().out

        assert "测试标题" in out
        assert "─" in out   # section separator


# ── _check_and_warn_login ───────────────────────────────────────


class TestCheckAndWarnLogin:
    """验证 _check_and_warn_login 行为。"""

    @pytest.mark.asyncio
    async def test_logged_in_returns_true(self, capsys):
        """已登录时返回 True 并打印 OK。"""
        crawler = MagicMock()
        crawler.check_login = AsyncMock(return_value=True)

        result = await test_taobao_crawl._check_and_warn_login(crawler)
        out = capsys.readouterr().out

        assert result is True
        assert "[OK]" in out
        assert "已登录" in out

    @pytest.mark.asyncio
    async def test_not_logged_in_returns_false(self, capsys):
        """未登录时返回 False 并提示 login_taobao.py。"""
        crawler = MagicMock()
        crawler.check_login = AsyncMock(return_value=False)

        result = await test_taobao_crawl._check_and_warn_login(crawler)
        out = capsys.readouterr().out

        assert result is False
        assert "[!!]" in out
        assert "login_taobao.py" in out


# ── main() ──────────────────────────────────────────────────────


class TestMain:
    """验证 main() 函数的各种路径。"""

    @pytest.mark.asyncio
    async def test_successful_crawl(self, capsys):
        """成功采集时返回 0，输出商品列表。"""
        from app.crawler.models.schemas import RawProduct

        mock_products = [
            RawProduct(
                name="海苔卷原味",
                price=29.90,
                shop="海苔店",
                platform="taobao",
                url="https://item.taobao.com/1",
            ),
            RawProduct(
                name="海苔卷辣味",
                price=32.50,
                shop="零食铺",
                platform="taobao",
                url="https://item.taobao.com/2",
            ),
        ]

        mock_crawler = MagicMock()
        mock_crawler.check_login = AsyncMock(return_value=True)
        mock_crawler.crawl = AsyncMock(return_value=mock_products)
        mock_crawler.close = AsyncMock()

        sys.argv = ["test_taobao_crawl.py"]
        with patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler):
            result = await test_taobao_crawl.main()

        assert result == 0
        out = capsys.readouterr().out
        assert "海苔卷原味" in out
        assert "29.90" in out
        assert "2 条商品" in out or "共" in out

    @pytest.mark.asyncio
    async def test_no_products_logged_in_returns_0(self, capsys):
        """已登录但无商品时返回 0。"""
        mock_crawler = MagicMock()
        mock_crawler.check_login = AsyncMock(return_value=True)
        mock_crawler.crawl = AsyncMock(return_value=[])
        mock_crawler.close = AsyncMock()

        sys.argv = ["test_taobao_crawl.py"]
        with patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler):
            result = await test_taobao_crawl.main()

        assert result == 0
        out = capsys.readouterr().out
        assert "未采集到商品" in out

    @pytest.mark.asyncio
    async def test_no_products_not_logged_in_returns_1(self, capsys):
        """未登录且无商品时返回 1。"""
        mock_crawler = MagicMock()
        mock_crawler.check_login = AsyncMock(return_value=False)
        mock_crawler.crawl = AsyncMock(return_value=[])
        mock_crawler.close = AsyncMock()

        sys.argv = ["test_taobao_crawl.py"]
        with patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler):
            result = await test_taobao_crawl.main()

        assert result == 1

    @pytest.mark.asyncio
    async def test_crawl_exception_returns_2(self, capsys):
        """采集异常时返回 2。"""
        mock_crawler = MagicMock()
        mock_crawler.check_login = AsyncMock(return_value=True)
        mock_crawler.crawl = AsyncMock(side_effect=RuntimeError("browser crash"))
        mock_crawler.close = AsyncMock()

        sys.argv = ["test_taobao_crawl.py"]
        with patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler):
            result = await test_taobao_crawl.main()

        assert result == 2
        out = capsys.readouterr().out
        assert "[ERROR]" in out

    @pytest.mark.asyncio
    async def test_save_json_writes_file(self, tmp_path, capsys):
        """--save-json 应保存结果文件。"""
        from app.crawler.models.schemas import RawProduct

        mock_products = [
            RawProduct(
                name="海苔卷",
                price=15.00,
                shop="店铺A",
                platform="taobao",
                url="https://item.taobao.com/x",
                viewers=100,
                sales_24h=50,
                image="https://img.taobao.com/x.jpg",
            ),
        ]

        mock_crawler = MagicMock()
        mock_crawler.check_login = AsyncMock(return_value=True)
        mock_crawler.crawl = AsyncMock(return_value=mock_products)
        mock_crawler.close = AsyncMock()

        # Patch PROJECT_ROOT to tmp_path
        sys.argv = ["test_taobao_crawl.py", "--save-json"]
        with (
            patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler),
            patch("test_taobao_crawl.PROJECT_ROOT", tmp_path),
        ):
            result = await test_taobao_crawl.main()

        assert result == 0

        # Verify JSON file
        json_path = tmp_path / "storage" / "test_taobao_crawl_result.json"
        assert json_path.exists()

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["keyword"] == "海苔卷"
        assert data["total"] == 1
        assert data["products"][0]["name"] == "海苔卷"
        assert data["products"][0]["price"] == 15.00

    @pytest.mark.asyncio
    async def test_close_always_called(self):
        """无论成功或失败，crawler.close() 都应被调用。"""
        mock_crawler = MagicMock()
        mock_crawler.check_login = AsyncMock(return_value=True)
        mock_crawler.crawl = AsyncMock(side_effect=Exception("fail"))
        mock_crawler.close = AsyncMock()

        sys.argv = ["test_taobao_crawl.py"]
        with patch("app.crawler.taobao.TaobaoCrawler", return_value=mock_crawler):
            await test_taobao_crawl.main()

        mock_crawler.close.assert_awaited_once()


# ── Constants ───────────────────────────────────────────────────


class TestConstants:
    """验证脚本中的常量定义。"""

    def test_project_root_is_absolute(self):
        """PROJECT_ROOT 应为绝对路径。"""
        assert test_taobao_crawl.PROJECT_ROOT.is_absolute()

    def test_project_root_contains_xuanpin(self):
        """PROJECT_ROOT 路径应包含项目名。"""
        assert "xuanpin-ai" in str(test_taobao_crawl.PROJECT_ROOT)

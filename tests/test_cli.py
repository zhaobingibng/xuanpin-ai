"""Tests for CLI tool."""

import asyncio
from unittest.mock import patch

import pytest

from app.cli import (
    _demo_products,
    _score_color,
    _truncate,
    build_parser,
    cmd_demo,
    cmd_score,
)


class TestHelpers:
    """Test CLI helper functions."""

    def test_score_color_high(self):
        assert _score_color(90.0) == "green"
        assert _score_color(80.0) == "green"

    def test_score_color_mid(self):
        assert _score_color(70.0) == "yellow"
        assert _score_color(60.0) == "yellow"

    def test_score_color_low_mid(self):
        assert _score_color(50.0) == "bright_yellow"
        assert _score_color(40.0) == "bright_yellow"

    def test_score_color_low(self):
        assert _score_color(30.0) == "red"
        assert _score_color(0.0) == "red"

    def test_truncate_short(self):
        assert _truncate("短文本", 30) == "短文本"

    def test_truncate_long(self):
        long_text = "这是一个非常长的商品名称需要被截断显示"
        result = _truncate(long_text, 10)
        assert len(result) == 11  # 10 chars + …
        assert result.endswith("…")

    def test_truncate_exact(self):
        text = "刚好三十个字符长度的文本内容填充数据占位"
        result = _truncate(text, len(text))
        assert result == text

    def test_demo_products_count(self):
        products = _demo_products()
        assert len(products) == 12

    def test_demo_products_platforms(self):
        products = _demo_products()
        platforms = {p.platform for p in products}
        assert "xiaohongshu" in platforms
        assert "douyin" in platforms
        assert "kuaishou" in platforms


class TestParser:
    """Test argparse configuration."""

    def test_run_command(self):
        parser = build_parser()
        args = parser.parse_args(["run", "-k", "防晒霜", "-p", "xiaohongshu", "douyin", "-n", "5", "--save"])
        assert args.command == "run"
        assert args.keyword == "防晒霜"
        assert args.platforms == ["xiaohongshu", "douyin"]
        assert args.pages == 5
        assert args.save is True

    def test_run_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["run", "-k", "耳机"])
        assert args.command == "run"
        assert args.keyword == "耳机"
        assert args.platforms is None
        assert args.pages == 3
        assert args.save is False

    def test_demo_command(self):
        parser = build_parser()
        args = parser.parse_args(["demo"])
        assert args.command == "demo"

    def test_score_command(self):
        parser = build_parser()
        args = parser.parse_args(["score", "--sales", "5000", "--viewers", "10000", "--price", "99.9"])
        assert args.command == "score"
        assert args.sales == 5000
        assert args.viewers == 10000
        assert args.price == 99.9

    def test_score_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["score"])
        assert args.sales == 0
        assert args.viewers == 0
        assert args.price == 0.0

    def test_no_command(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.command is None


class TestCommands:
    """Test CLI command functions (async)."""

    @pytest.mark.asyncio
    async def test_demo_runs_without_error(self):
        """Demo command should complete without errors."""
        parser = build_parser()
        args = parser.parse_args(["demo"])
        # Suppress console output during test
        with patch("app.cli.console"):
            await cmd_demo(args)

    @pytest.mark.asyncio
    async def test_score_runs_without_error(self):
        """Score command should complete without errors."""
        parser = build_parser()
        args = parser.parse_args(["score", "--sales", "5000", "--viewers", "10000", "--price", "99.9"])
        with patch("app.cli.console"):
            await cmd_score(args)

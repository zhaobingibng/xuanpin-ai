"""Tests for assistant integration with strategy generation."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.assistant.assistant import SelectionAssistant


class TestStrategyClassification:
    """运营方案问题分类测试。"""

    def test_classify_copy(self):
        assert SelectionAssistant._classify("帮我写文案") == "strategy"

    def test_classify_strategy(self):
        assert SelectionAssistant._classify("生成运营方案") == "strategy"

    def test_classify_how_to_sell(self):
        assert SelectionAssistant._classify("怎么卖这个商品") == "strategy"

    def test_classify_marketing(self):
        assert SelectionAssistant._classify("帮我做营销方案") == "strategy"

    def test_classify_promotion(self):
        assert SelectionAssistant._classify("写个推广方案") == "strategy"

    def test_classify_script(self):
        assert SelectionAssistant._classify("成交话术怎么写") == "strategy"

    def test_recommend_still_works(self):
        """推荐类问题不被策略关键词干扰。"""
        assert SelectionAssistant._classify("推荐什么好") == "recommend"

    def test_risk_overrides_strategy(self):
        """风险类优先于策略类。"""
        # "竞争" is in risk, should be risk
        assert SelectionAssistant._classify("竞争大怎么写文案") == "risk"


class TestStrategyHandler:
    """运营方案处理测试（使用 mock session）。"""

    def _make_assistant(self):
        mock_session = MagicMock()
        return SelectionAssistant.__new__(SelectionAssistant)

    @pytest.mark.anyio
    async def test_strategy_no_report(self):
        """无推荐数据时返回提示。"""
        assistant = self._make_assistant()
        mock_repo = MagicMock()
        mock_repo.get_latest = AsyncMock(return_value=None)
        assistant._report_repo = mock_repo
        assistant._knowledge_repo = MagicMock()
        assistant._session = MagicMock()

        result = await assistant._handle_strategy("帮我写文案")
        assert "暂无" in result["answer"]
        assert result["products"] == []

    @pytest.mark.anyio
    async def test_strategy_with_report(self):
        """有推荐数据时生成运营方案。"""
        assistant = self._make_assistant()

        # Mock report
        mock_item = MagicMock()
        mock_item.product_id = 1
        mock_item.name = "蓝牙耳机"
        mock_item.price = 99.0
        mock_item.score = 90

        mock_report = MagicMock()
        mock_report.items = [mock_item]

        mock_repo = MagicMock()
        mock_repo.get_latest = AsyncMock(return_value=mock_report)
        assistant._report_repo = mock_repo

        # Mock knowledge repo
        mock_knowledge = MagicMock()
        mock_knowledge.get_product_tags = AsyncMock(return_value=[])
        assistant._knowledge_repo = mock_knowledge

        # Mock session
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        assistant._session = mock_session

        with patch("app.services.strategy.generator.ProductStrategyGenerator") as mock_cls:
            mock_gen = MagicMock()
            mock_gen.generate = AsyncMock(return_value={
                "product_id": 1,
                "title": "学生党必备降噪 蓝牙耳机",
                "selling_points": ["高音质", "长续航", "高性价比"],
                "xiaohongshu_copy": "小红书文案",
                "xianyu_copy": "闲鱼文案",
                "price_strategy": {"cost": 60, "sell": 99, "profit": 39},
                "profit_analysis": {"profit_margin": "39.4%"},
            })
            mock_cls.return_value = mock_gen

            result = await assistant._handle_strategy("帮我写文案")

        assert "已为" in result["answer"]
        assert len(result["products"]) == 1
        assert "strategy" in result["products"][0]
        assert len(result["insights"]) == 3

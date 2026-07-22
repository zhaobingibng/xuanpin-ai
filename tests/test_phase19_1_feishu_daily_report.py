"""Tests for Phase 19 Task 1: Feishu Daily Report Notification."""

import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

from app.models.product import Product
from app.models.opportunity_score import OpportunityScore
from app.models.supplier_match import SupplierMatch
from app.services.feishu_notification import FeishuNotificationService
from app.services.daily_report import DailyReportGenerator, daily_report_task


# ── FeishuNotificationService Tests ────────────────────────────


class TestFeishuNotificationService:
    """Test FeishuNotificationService."""

    def test_init_with_config_disabled(self, tmp_path):
        """Test initialization with disabled config."""
        config_file = tmp_path / "feishu.json"
        config_file.write_text(json.dumps({
            "enabled": False,
            "webhook_url": "",
            "secret": "",
        }))

        service = FeishuNotificationService(config_path=str(config_file))
        assert not service.is_enabled

    def test_init_with_config_enabled(self, tmp_path):
        """Test initialization with enabled config."""
        config_file = tmp_path / "feishu.json"
        config_file.write_text(json.dumps({
            "enabled": True,
            "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
            "secret": "test_secret",
        }))

        service = FeishuNotificationService(config_path=str(config_file))
        assert service.is_enabled
        assert service._webhook_url == "https://open.feishu.cn/open-apis/bot/v2/hook/test"
        assert service._secret == "test_secret"

    def test_init_with_direct_params(self):
        """Test initialization with direct parameters."""
        service = FeishuNotificationService(
            webhook_url="https://example.com/webhook",
            secret="my_secret",
        )
        assert service.is_enabled
        assert service._webhook_url == "https://example.com/webhook"
        assert service._secret == "my_secret"

    def test_init_missing_config_file(self, tmp_path):
        """Test initialization with missing config file."""
        service = FeishuNotificationService(config_path=str(tmp_path / "nonexistent.json"))
        assert not service.is_enabled

    def test_generate_sign_without_secret(self):
        """Test sign generation without secret."""
        service = FeishuNotificationService(webhook_url="https://example.com")
        service._secret = None
        sign = service._generate_sign("1234567890")
        assert sign == ""

    def test_generate_sign_with_secret(self):
        """Test sign generation with secret."""
        service = FeishuNotificationService(
            webhook_url="https://example.com",
            secret="test_secret",
        )
        sign = service._generate_sign("1234567890")
        assert len(sign) > 0

    @pytest.mark.asyncio
    async def test_send_message_disabled(self):
        """Test send_message when disabled."""
        service = FeishuNotificationService(webhook_url=None)
        service._enabled = False

        result = await service.send_message("Hello")
        assert result["success"] is False
        assert "disabled" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_send_message_success(self):
        """Test send_message success."""
        service = FeishuNotificationService(
            webhook_url="https://example.com/webhook",
            secret="test_secret",
        )

        # Mock httpx
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 0, "msg": "success"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            result = await service.send_message("Test message")

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_send_message_failure(self):
        """Test send_message failure."""
        service = FeishuNotificationService(
            webhook_url="https://example.com/webhook",
        )

        # Mock httpx with error response
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 1001, "msg": "Invalid webhook"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            result = await service.send_message("Test message")

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_send_daily_report(self):
        """Test send_daily_report."""
        service = FeishuNotificationService(webhook_url=None)
        service._enabled = False

        result = await service.send_daily_report("Daily report content")
        assert result["success"] is False


# ── DailyReportGenerator Tests ─────────────────────────────────


class TestDailyReportGenerator:
    """Test DailyReportGenerator."""

    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        session = MagicMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def sample_product(self):
        """Create sample product."""
        return Product(
            id=1,
            name="三只松鼠芋泥吐司卷",
            platform="taobao",
            shop="三只松鼠旗舰店",
            price=69.9,
            lifecycle_stage="NEW",
        )

    @pytest.fixture
    def sample_score(self):
        """Create sample opportunity score."""
        return OpportunityScore(
            id=1,
            product_id=1,
            new_product_score=25.0,
            shop_score=20.0,
            supplier_score=25.0,
            profit_score=20.0,
            competition_score=5.0,
            total_score=95.0,
            recommendation="★★★★★ 强烈推荐",
        )

    @pytest.fixture
    def sample_match(self):
        """Create sample supplier match."""
        return SupplierMatch(
            id=1,
            product_id=1,
            supplier_title="芋泥吐司卷 厂家直销",
            supplier_price=20.0,
            similarity_score=80.0,
            estimated_profit=49.9,
            profit_margin=71.4,
        )

    def test_format_report_with_data(
        self, mock_session, sample_product, sample_score, sample_match
    ):
        """Test format_report with sample data."""
        generator = DailyReportGenerator(mock_session)

        opportunities = [{
            "product": sample_product,
            "score": sample_score,
            "supplier_match": sample_match,
        }]

        report = generator.format_report(opportunities)

        assert "# 今日选品机会" in report
        assert "三只松鼠芋泥吐司卷" in report
        assert "69.9" in report
        assert "20.0" in report
        assert "71.4%" in report
        assert "95.0" in report
        assert "★★★★★ 强烈推荐" in report

    def test_format_report_without_match(self, mock_session, sample_product, sample_score):
        """Test format_report without supplier match."""
        generator = DailyReportGenerator(mock_session)

        opportunities = [{
            "product": sample_product,
            "score": sample_score,
            "supplier_match": None,
        }]

        report = generator.format_report(opportunities)

        assert "未匹配" in report
        assert "--" in report

    def test_format_report_empty(self, mock_session):
        """Test format_report with empty opportunities."""
        generator = DailyReportGenerator(mock_session)
        report = generator.format_report([])
        assert "0 个值得跟卖的机会" in report

    def test_format_report_includes_reasons(
        self, mock_session, sample_product, sample_score, sample_match
    ):
        """Test format_report includes recommendation reasons."""
        generator = DailyReportGenerator(mock_session)

        opportunities = [{
            "product": sample_product,
            "score": sample_score,
            "supplier_match": sample_match,
        }]

        report = generator.format_report(opportunities)

        assert "推荐理由" in report
        assert "新品发现" in report
        assert "头部店铺" in report
        assert "找到供应链" in report
        assert "高利润空间" in report

    @pytest.mark.asyncio
    async def test_get_top_opportunities(self, mock_session, sample_product, sample_score, sample_match):
        """Test get_top_opportunities."""
        # Mock query results
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_score]
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Mock product query
        mock_product_result = MagicMock()
        mock_product_result.scalar_one_or_none.return_value = sample_product

        # Mock match query
        mock_match_result = MagicMock()
        mock_match_result.scalar_one_or_none.return_value = sample_match

        # Alternate between score, product, match results
        mock_session.execute.side_effect = [
            mock_result,  # score query
            mock_product_result,  # product query
            mock_match_result,  # match query
        ]

        generator = DailyReportGenerator(mock_session)
        opportunities = await generator.get_top_opportunities(limit=10)

        assert len(opportunities) == 1
        assert opportunities[0]["product"] == sample_product
        assert opportunities[0]["score"] == sample_score

    @pytest.mark.asyncio
    async def test_generate_daily_opportunity_report(
        self, mock_session, sample_product, sample_score, sample_match
    ):
        """Test generate_daily_opportunity_report."""
        # Mock query results
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_score]
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_product_result = MagicMock()
        mock_product_result.scalar_one_or_none.return_value = sample_product

        mock_match_result = MagicMock()
        mock_match_result.scalar_one_or_none.return_value = sample_match

        mock_session.execute.side_effect = [
            mock_result,
            mock_product_result,
            mock_match_result,
        ]

        generator = DailyReportGenerator(mock_session)
        report = await generator.generate_daily_opportunity_report(limit=5)

        assert "今日选品机会" in report
        assert "三只松鼠芋泥吐司卷" in report

    @pytest.mark.asyncio
    async def test_generate_report_no_opportunities(self, mock_session):
        """Test generate report with no opportunities."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        generator = DailyReportGenerator(mock_session)
        report = await generator.generate_daily_opportunity_report()

        assert "暂无" in report


# ── Daily Report Task Tests ────────────────────────────────────


class TestDailyReportTask:
    """Test daily_report_task function."""

    @pytest.mark.asyncio
    async def test_daily_report_task_success(self):
        """Test daily_report_task success."""
        mock_session = MagicMock()
        mock_feishu = MagicMock()
        mock_feishu.is_enabled = False

        # Mock the generator
        with patch.object(DailyReportGenerator, "generate_daily_opportunity_report", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Test report content"

            result = await daily_report_task(mock_session, mock_feishu, limit=5)

        assert result["success"] is True
        assert "report" in result

    @pytest.mark.asyncio
    async def test_daily_report_task_with_feishu(self):
        """Test daily_report_task with feishu enabled."""
        mock_session = MagicMock()
        mock_feishu = MagicMock()
        mock_feishu.is_enabled = True
        mock_feishu.send_daily_report = AsyncMock(return_value={"success": True})

        with patch.object(DailyReportGenerator, "generate_daily_opportunity_report", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Test report"

            result = await daily_report_task(mock_session, mock_feishu, limit=5)

        assert result["success"] is True
        mock_feishu.send_daily_report.assert_called_once_with("Test report")

    @pytest.mark.asyncio
    async def test_daily_report_task_error(self):
        """Test daily_report_task error handling."""
        mock_session = MagicMock()

        with patch.object(DailyReportGenerator, "generate_daily_opportunity_report", new_callable=AsyncMock) as mock_gen:
            mock_gen.side_effect = Exception("Database error")

            result = await daily_report_task(mock_session, None, limit=5)

        assert result["success"] is False
        assert "error" in result

"""Tests for Phase 13: Pipeline LLM integration — Step 5b and Step 10b."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Step 5b: LLM Report Summary ───────────────────────────────


class TestPipelineLLMReportSummary:
    """Pipeline Step 5b: LLM 报告摘要测试。"""

    @pytest.mark.anyio
    async def test_llm_report_summary_unavailable(self):
        """LLM 不可用时静默跳过，不影响 Pipeline。"""
        from app.tasks.jobs import daily_crawl_job

        with patch("app.tasks.jobs.CrawlerManager") as mock_manager_cls:
            mock_manager = MagicMock()
            mock_manager.crawl = AsyncMock(return_value=[])
            mock_manager.close_all = AsyncMock()
            mock_manager_cls.return_value = mock_manager

            # save_to_db=False 跳过数据库操作
            result = await daily_crawl_job(
                keywords=["test"], platforms=["xiaohongshu"], save_to_db=False
            )
            # 空采集，Pipeline 正常结束
            assert result["raw_count"] == 0
            # LLM 报告摘要不应存在（因为 save_to_db=False）
            assert "llm_report_summary" not in result


# ── Step 10b: LLM Product Analysis ────────────────────────────


class TestPipelineLLMProductAnalysis:
    """Pipeline Step 10b: LLM 商品分析测试。"""

    @pytest.mark.anyio
    async def test_llm_product_analysis_empty_crawl(self):
        """空采集时 LLM 商品分析不执行。"""
        from app.tasks.jobs import daily_crawl_job

        with patch("app.tasks.jobs.CrawlerManager") as mock_manager_cls:
            mock_manager = MagicMock()
            mock_manager.crawl = AsyncMock(return_value=[])
            mock_manager.close_all = AsyncMock()
            mock_manager_cls.return_value = mock_manager

            result = await daily_crawl_job(
                keywords=["test"], platforms=["xiaohongshu"], save_to_db=False
            )
            # 空采集，Pipeline 正常结束
            assert "llm_product_analyses" not in result


# ── LLM Degradation ───────────────────────────────────────────


class TestPipelineLLMDegradation:
    """Pipeline LLM 降级测试。"""

    @pytest.mark.anyio
    async def test_pipeline_completes_without_llm(self):
        """LLM 完全不可用时 Pipeline 正常完成。"""
        from app.tasks.jobs import daily_crawl_job

        with patch("app.tasks.jobs.CrawlerManager") as mock_manager_cls:
            mock_manager = MagicMock()
            mock_manager.crawl = AsyncMock(return_value=[])
            mock_manager.close_all = AsyncMock()
            mock_manager_cls.return_value = mock_manager

            # 不 mock LLM，让它自然降级（API Key 未配置）
            result = await daily_crawl_job(
                keywords=["test"], platforms=["xiaohongshu"], save_to_db=False
            )
            assert result["raw_count"] == 0
            # Pipeline 应该正常完成，不因 LLM 失败而报错

    @pytest.mark.anyio
    async def test_pipeline_result_structure_unchanged(self):
        """Pipeline result 结构不变，LLM 字段是可选的。"""
        from app.tasks.jobs import daily_crawl_job

        with patch("app.tasks.jobs.CrawlerManager") as mock_manager_cls:
            mock_manager = MagicMock()
            mock_manager.crawl = AsyncMock(return_value=[])
            mock_manager.close_all = AsyncMock()
            mock_manager_cls.return_value = mock_manager

            result = await daily_crawl_job(
                keywords=["test"], platforms=["xiaohongshu"], save_to_db=False
            )

            # 必须存在的字段
            assert "job_id" in result
            assert "started_at" in result
            assert "keywords" in result
            assert "platforms" in result
            assert "raw_count" in result
            assert "errors" in result

            # LLM 字段是可选的，不存在也不应报错
            if "llm_report_summary" in result:
                assert isinstance(result["llm_report_summary"], str)
            if "llm_product_analyses" in result:
                assert isinstance(result["llm_product_analyses"], list)

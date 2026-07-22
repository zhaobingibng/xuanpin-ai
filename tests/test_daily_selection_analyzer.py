"""Tests for DailySelectionAnalyzer — Phase 38.2.

Covers: LLM available/unavailable, success/failure, validation,
fallback rules, edge cases (empty/minimal report), and no-DB guarantee.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ai_analysis.daily_selection_analyzer import DailySelectionAnalyzer


# ── Helpers ───────────────────────────────────────────────────


def _mock_report(**overrides) -> dict:
    """Build a realistic DailySelectionReport dict for testing."""
    defaults = {
        "report_date": "2026-07-21",
        "generated_at": "2026-07-21T08:00:00",
        "summary": "共扫描 100 件商品，其中 50 件有供应商匹配。经评分过滤后，30 件商品进入候选池。"
        "Top 20 平均机会评分 65.0，平均预估利润 ¥35.0。其中 12 件商品机会评分 ≥ 60 分。"
        "评分分布: ★★★★★8 | ★★★★10 | ★★★12",
        "top_products": [
            {
                "product_id": 1,
                "title": "爆款蓝牙耳机",
                "price": 99.0,
                "opportunity_score": 92.0,
                "recommendation": "STRONGLY_RECOMMENDED",
                "supplier_info": {
                    "supplier_title": "蓝牙耳机工厂直供",
                    "supplier_price": 29.0,
                    "supplier_product_id": 1001,
                    "profit_margin": 70.0,
                    "final_score": 0.85,
                    "match_count": 3,
                },
                "estimated_profit": 70.0,
                "reasons": ["机会评分: 92.0分 (STRONGLY_RECOMMENDED)", "匹配度: 85%", "利润率: 70%"],
                "risks": ["无明显风险"],
            },
            {
                "product_id": 2,
                "title": "便携充电宝",
                "price": 129.0,
                "opportunity_score": 78.0,
                "recommendation": "STRONGLY_RECOMMENDED",
                "supplier_info": {
                    "supplier_title": "充电宝批发",
                    "supplier_price": 80.0,
                    "profit_margin": 38.0,
                    "final_score": 0.72,
                    "match_count": 2,
                },
                "estimated_profit": 49.0,
                "reasons": ["机会评分: 78.0分 (STRONGLY_RECOMMENDED)"],
                "risks": ["仅1个可靠供应商, 供应风险"],
            },
            {
                "product_id": 3,
                "title": "手机支架桌面款",
                "price": 29.0,
                "opportunity_score": 65.0,
                "recommendation": "WORTH_STUDYING",
                "supplier_info": {
                    "supplier_title": "手机支架厂家",
                    "supplier_price": 8.0,
                    "profit_margin": 72.0,
                    "final_score": 0.60,
                    "match_count": 4,
                },
                "estimated_profit": 21.0,
                "reasons": ["机会评分: 65.0分 (WORTH_STUDYING)"],
                "risks": ["利润率异常高, 可能是虚假商品"],
            },
        ],
        "statistics": {
            "total_products": 100,
            "matched_products": 50,
            "filtered_products": 30,
            "avg_score": 65.0,
            "avg_profit": 35.0,
            "high_opportunity_count": 12,
            "distribution": {
                "strongly_recommended": 8,
                "worth_studying": 10,
                "observe": 12,
            },
        },
    }
    defaults.update(overrides)
    return defaults


def _mock_llm_client(available: bool = True) -> MagicMock:
    """Build a mock LLMClient."""
    client = MagicMock()
    client.available = available
    client.model = "deepseek-chat"
    client.base_url = "https://api.deepseek.com"
    return client


def _mock_llm_success_result() -> dict:
    """Standard LLM success response."""
    return {
        "overall_summary": "本期共扫描100件商品，发现8件强烈推荐商品，平均利润¥35，蓝牙耳机领跑。",
        "highlights": ["蓝牙耳机利润空间大", "充电宝匹配度72%", "手机支架有4家供应商可选"],
        "warnings": ["手机支架利润率异常需核实", "充电宝仅1个可靠供应商"],
        "action_suggestions": ["立即联系蓝牙耳机供应商确认货源", "对充电宝启动小规模测试"],
        "profit_insight": "TOP商品平均利润¥35，其中蓝牙耳机单品利润¥70表现突出。",
        "market_trend": "数码配件类商品机会丰富，建议持续跟进。",
        "top_pick_notes": [
            {"product_id": 1, "note": "高利润高分，强烈推荐"},
            {"product_id": 2, "note": "匹配稳定，可小规模测试"},
            {"product_id": 3, "note": "供应商充足但需核实价格"},
        ],
    }


# ── LLM Available → Success ───────────────────────────────────


class TestAnalyzeLLMSuccess:
    """LLM 可用且返回有效结果。"""

    @pytest.mark.anyio
    async def test_returns_ai_insights_on_success(self):
        """LLM 成功返回时，ai_available=True 且字段完整。"""
        mock_client = _mock_llm_client(available=True)
        mock_client.chat_json = AsyncMock(return_value=_mock_llm_success_result())

        with patch(
            "app.services.ai_analysis.daily_selection_analyzer.get_llm_client",
            return_value=mock_client,
        ):
            analyzer = DailySelectionAnalyzer()
            result = await analyzer.analyze(_mock_report())

        assert result["ai_available"] is True
        assert "overall_summary" in result
        assert len(result["highlights"]) > 0
        assert len(result["action_suggestions"]) > 0
        assert len(result["top_pick_notes"]) > 0

    @pytest.mark.anyio
    async def test_returns_correct_fields(self):
        """返回结果包含所有预期字段。"""
        mock_client = _mock_llm_client(available=True)
        mock_client.chat_json = AsyncMock(return_value=_mock_llm_success_result())

        with patch(
            "app.services.ai_analysis.daily_selection_analyzer.get_llm_client",
            return_value=mock_client,
        ):
            analyzer = DailySelectionAnalyzer()
            result = await analyzer.analyze(_mock_report())

        expected_keys = {
            "ai_available", "overall_summary", "highlights",
            "warnings", "action_suggestions", "profit_insight",
            "market_trend", "top_pick_notes",
        }
        assert expected_keys.issubset(result.keys())

    @pytest.mark.anyio
    async def test_top_pick_notes_preserved(self):
        """LLM 返回的 top_pick_notes 被正确保留。"""
        mock_client = _mock_llm_client(available=True)
        mock_client.chat_json = AsyncMock(return_value=_mock_llm_success_result())

        with patch(
            "app.services.ai_analysis.daily_selection_analyzer.get_llm_client",
            return_value=mock_client,
        ):
            analyzer = DailySelectionAnalyzer()
            result = await analyzer.analyze(_mock_report())

        notes = result["top_pick_notes"]
        assert len(notes) == 3
        assert notes[0]["product_id"] == 1
        assert len(notes[0]["note"]) > 0


# ── LLM Unavailable / Failure → Fallback ──────────────────────


class TestAnalyzeLLMUnavailable:
    """LLM 不可用时降级到规则兜底。"""

    @pytest.mark.anyio
    async def test_fallbacks_when_client_unavailable(self):
        """LLM client.available=False → 规则兜底。"""
        mock_client = _mock_llm_client(available=False)

        with patch(
            "app.services.ai_analysis.daily_selection_analyzer.get_llm_client",
            return_value=mock_client,
        ):
            analyzer = DailySelectionAnalyzer()
            result = await analyzer.analyze(_mock_report())

        assert result["ai_available"] is False
        assert len(result["overall_summary"]) > 0
        # 规则兜底也应有亮点
        assert isinstance(result["highlights"], list)

    @pytest.mark.anyio
    async def test_fallbacks_when_llm_returns_none(self):
        """LLM chat_json 返回 None → 规则兜底。"""
        mock_client = _mock_llm_client(available=True)
        mock_client.chat_json = AsyncMock(return_value=None)

        with patch(
            "app.services.ai_analysis.daily_selection_analyzer.get_llm_client",
            return_value=mock_client,
        ):
            analyzer = DailySelectionAnalyzer()
            result = await analyzer.analyze(_mock_report())

        assert result["ai_available"] is False
        assert len(result["overall_summary"]) > 0

    @pytest.mark.anyio
    async def test_fallbacks_on_llm_exception(self):
        """LLM 调用抛出异常 → 规则兜底（不抛异常）。"""
        mock_client = _mock_llm_client(available=True)
        mock_client.chat_json = AsyncMock(side_effect=Exception("Connection refused"))

        with patch(
            "app.services.ai_analysis.daily_selection_analyzer.get_llm_client",
            return_value=mock_client,
        ):
            analyzer = DailySelectionAnalyzer()
            result = await analyzer.analyze(_mock_report())

        assert result["ai_available"] is False
        assert len(result["overall_summary"]) > 0

    @pytest.mark.anyio
    async def test_fallbacks_on_timeout(self):
        """LLM 超时 → 规则兜底。"""
        import httpx

        mock_client = _mock_llm_client(available=True)
        mock_client.chat_json = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch(
            "app.services.ai_analysis.daily_selection_analyzer.get_llm_client",
            return_value=mock_client,
        ):
            analyzer = DailySelectionAnalyzer()
            result = await analyzer.analyze(_mock_report())

        assert result["ai_available"] is False


# ── Validation ─────────────────────────────────────────────────


class TestValidation:
    """字段校验测试。"""

    @pytest.mark.anyio
    async def test_missing_overall_summary_triggers_fallback(self):
        """LLM 返回缺少 overall_summary → 规则降级。"""
        mock_client = _mock_llm_client(available=True)
        mock_client.chat_json = AsyncMock(return_value={
            "highlights": ["test"],
        })

        with patch(
            "app.services.ai_analysis.daily_selection_analyzer.get_llm_client",
            return_value=mock_client,
        ):
            analyzer = DailySelectionAnalyzer()
            result = await analyzer.analyze(_mock_report())

        assert result["ai_available"] is False  # fell back

    @pytest.mark.anyio
    async def test_empty_overall_summary_triggers_fallback(self):
        """LLM 返回空 overall_summary → 规则降级。"""
        mock_client = _mock_llm_client(available=True)
        mock_client.chat_json = AsyncMock(return_value={
            "overall_summary": "",
            "highlights": ["test"],
        })

        with patch(
            "app.services.ai_analysis.daily_selection_analyzer.get_llm_client",
            return_value=mock_client,
        ):
            analyzer = DailySelectionAnalyzer()
            result = await analyzer.analyze(_mock_report())

        assert result["ai_available"] is False

    @pytest.mark.anyio
    async def test_non_list_fields_normalized(self):
        """LLM 返回非 list 的高亮/警告/建议 → 规范化为空列表。"""
        mock_client = _mock_llm_client(available=True)
        mock_client.chat_json = AsyncMock(return_value={
            "overall_summary": "有效摘要",
            "highlights": "not a list",
            "warnings": 123,
            "action_suggestions": None,
        })

        with patch(
            "app.services.ai_analysis.daily_selection_analyzer.get_llm_client",
            return_value=mock_client,
        ):
            analyzer = DailySelectionAnalyzer()
            result = await analyzer.analyze(_mock_report())

        assert result["ai_available"] is True
        assert result["highlights"] == []
        assert result["warnings"] == []
        assert result["action_suggestions"] == []

    @pytest.mark.anyio
    async def test_invalid_top_pick_notes_filtered(self):
        """无效的 top_pick_notes 项被过滤掉。"""
        mock_client = _mock_llm_client(available=True)
        mock_client.chat_json = AsyncMock(return_value={
            "overall_summary": "有效摘要",
            "top_pick_notes": [
                {"product_id": 1, "note": "好商品"},
                "not_a_dict",
                {"no_note_field": True},
                {"product_id": 2, "note": "另一个"},
            ],
        })

        with patch(
            "app.services.ai_analysis.daily_selection_analyzer.get_llm_client",
            return_value=mock_client,
        ):
            analyzer = DailySelectionAnalyzer()
            result = await analyzer.analyze(_mock_report())

        notes = result["top_pick_notes"]
        assert len(notes) == 2  # only valid items
        assert notes[0]["product_id"] == 1
        assert notes[1]["product_id"] == 2


# ── Fallback Rule Methods (direct) ─────────────────────────────


class TestFallbackMethods:
    """规则兜底方法直接测试。"""

    def test_fallback_returns_all_fields(self):
        """analyze_fallback 返回完整字段。"""
        analyzer = DailySelectionAnalyzer()
        result = analyzer.analyze_fallback(_mock_report())

        assert result["ai_available"] is False
        assert isinstance(result["overall_summary"], str)
        assert isinstance(result["highlights"], list)
        assert isinstance(result["warnings"], list)
        assert isinstance(result["action_suggestions"], list)
        assert isinstance(result["profit_insight"], str)
        assert isinstance(result["market_trend"], str)
        assert isinstance(result["top_pick_notes"], list)

    def test_fallback_summary_non_empty(self):
        """规则摘要不为空。"""
        analyzer = DailySelectionAnalyzer()
        result = analyzer.analyze_fallback(_mock_report())
        assert len(result["overall_summary"]) > 10

    def test_fallback_highlights_from_strong_products(self):
        """包含强烈推荐商品时，亮点中有提及。"""
        analyzer = DailySelectionAnalyzer()
        result = analyzer.analyze_fallback(_mock_report())
        highlights = result["highlights"]
        assert any("强烈推荐" in h or "高分" in h for h in highlights)

    def test_fallback_warnings_from_risks(self):
        """风险来自商品数据。"""
        analyzer = DailySelectionAnalyzer()
        result = analyzer.analyze_fallback(_mock_report())
        # At least one warning (risk signals are extracted)
        assert len(result["warnings"]) >= 1

    def test_fallback_actions_non_empty(self):
        """行动建议不为空。"""
        analyzer = DailySelectionAnalyzer()
        result = analyzer.analyze_fallback(_mock_report())
        assert len(result["action_suggestions"]) >= 1

    def test_fallback_profit_insight_positive(self):
        """有利润时生成利润洞察。"""
        analyzer = DailySelectionAnalyzer()
        result = analyzer.analyze_fallback(_mock_report())
        assert "¥" in result["profit_insight"]

    def test_fallback_market_trend(self):
        """市场趋势判断。"""
        analyzer = DailySelectionAnalyzer()
        result = analyzer.analyze_fallback(_mock_report())
        assert len(result["market_trend"]) > 0

    def test_fallback_top_notes_count(self):
        """TOP3 简评数量 ≤ 3。"""
        analyzer = DailySelectionAnalyzer()
        result = analyzer.analyze_fallback(_mock_report())
        assert len(result["top_pick_notes"]) <= 3

    def test_fallback_top_notes_structure(self):
        """TOP3 简评每项含 product_id 和 note。"""
        analyzer = DailySelectionAnalyzer()
        result = analyzer.analyze_fallback(_mock_report())
        for note in result["top_pick_notes"]:
            assert "product_id" in note
            assert "note" in note


# ── Edge Cases ─────────────────────────────────────────────────


class TestEdgeCases:
    """边界情况测试。"""

    def test_empty_report(self):
        """空报告也能正常返回。"""
        analyzer = DailySelectionAnalyzer()
        empty = {
            "report_date": "2026-07-21",
            "summary": "",
            "top_products": [],
            "statistics": {
                "total_products": 0,
                "matched_products": 0,
                "filtered_products": 0,
                "avg_score": 0.0,
                "avg_profit": 0.0,
                "high_opportunity_count": 0,
                "distribution": {"strongly_recommended": 0, "worth_studying": 0, "observe": 0},
            },
        }
        result = analyzer.analyze_fallback(empty)

        assert result["ai_available"] is False
        assert len(result["overall_summary"]) > 0
        assert result["top_pick_notes"] == []

    def test_minimal_report(self):
        """最小报告（仅有核心字段）。"""
        analyzer = DailySelectionAnalyzer()
        minimal = {
            "report_date": "2026-07-21",
            "summary": "",
            "top_products": [
                {
                    "product_id": 1,
                    "title": "单品",
                    "price": 50.0,
                    "opportunity_score": 60.0,
                    "recommendation": "WORTH_STUDYING",
                    "supplier_info": None,
                    "estimated_profit": None,
                    "reasons": [],
                    "risks": ["无供应商匹配 — 无法跟卖"],
                }
            ],
            "statistics": {
                "total_products": 1,
                "matched_products": 0,
                "filtered_products": 1,
                "avg_score": 60.0,
                "avg_profit": 0.0,
                "high_opportunity_count": 0,
                "distribution": {"strongly_recommended": 0, "worth_studying": 1, "observe": 0},
            },
        }
        result = analyzer.analyze_fallback(minimal)

        assert result["ai_available"] is False
        assert len(result["warnings"]) >= 1  # should have "暂无供应商匹配"

    @pytest.mark.anyio
    async def test_analyze_never_throws(self):
        """任何情况下 analyze() 都不抛异常。"""
        # 故意传残缺 dict
        analyzer = DailySelectionAnalyzer()
        mock_client = _mock_llm_client(available=True)
        mock_client.chat_json = AsyncMock(side_effect=RuntimeError("crash"))

        with patch(
            "app.services.ai_analysis.daily_selection_analyzer.get_llm_client",
            return_value=mock_client,
        ):
            result = await analyzer.analyze({"top_products": [], "statistics": {}})

        # 不抛异常，返回有效 dict
        assert isinstance(result, dict)
        assert "ai_available" in result

    @pytest.mark.anyio
    async def test_report_with_no_top_products(self):
        """无 top_products 时也能正常分析。"""
        mock_client = _mock_llm_client(available=False)

        with patch(
            "app.services.ai_analysis.daily_selection_analyzer.get_llm_client",
            return_value=mock_client,
        ):
            analyzer = DailySelectionAnalyzer()
            result = await analyzer.analyze({
                "report_date": "2026-07-21",
                "summary": "无商品",
                "top_products": [],
                "statistics": {
                    "total_products": 0, "matched_products": 0,
                    "filtered_products": 0, "avg_score": 0.0,
                    "avg_profit": 0.0, "high_opportunity_count": 0,
                    "distribution": {"strongly_recommended": 0, "worth_studying": 0, "observe": 0},
                },
            })

        assert result["ai_available"] is False
        assert len(result["overall_summary"]) > 0


# ── No DB Dependency ───────────────────────────────────────────


class TestNoDB:
    """验证 DailySelectionAnalyzer 无数据库依赖。"""

    def test_no_session_required(self):
        """构造函数不需要 session 参数。"""
        analyzer = DailySelectionAnalyzer()
        assert analyzer is not None

    def test_analyze_fallback_no_async_required(self):
        """规则兜底方法是同步的（无需 async）。"""
        import inspect
        assert not inspect.iscoroutinefunction(DailySelectionAnalyzer.analyze_fallback)

    @pytest.mark.anyio
    async def test_analyze_uses_only_llm_client(self):
        """analyze() 仅依赖 LLMClient，不需要数据库连接。"""
        mock_client = _mock_llm_client(available=True)
        mock_client.chat_json = AsyncMock(return_value=_mock_llm_success_result())

        with patch(
            "app.services.ai_analysis.daily_selection_analyzer.get_llm_client",
            return_value=mock_client,
        ):
            analyzer = DailySelectionAnalyzer()
            # 不应抛出数据库连接异常
            result = await analyzer.analyze(_mock_report())
            assert result["ai_available"] is True


# ── User Prompt Building ───────────────────────────────────────


class TestUserPromptBuilder:
    """_build_user_prompt 测试。"""

    def test_builds_prompt_with_report_data(self):
        """正常报告构建完整 prompt。"""
        analyzer = DailySelectionAnalyzer()
        prompt = analyzer._build_user_prompt(_mock_report())

        assert prompt is not None
        assert "2026-07-21" in prompt
        assert "100" in prompt  # total_products
        assert "50" in prompt   # matched_products
        assert "爆款蓝牙耳机" in prompt
        assert "TOP 商品" in prompt

    def test_prompt_handles_empty_products(self):
        """空商品列表构建 prompt。"""
        analyzer = DailySelectionAnalyzer()
        report = _mock_report()
        report["top_products"] = []
        prompt = analyzer._build_user_prompt(report)

        assert prompt is not None
        assert "（无商品数据）" in prompt

    def test_prompt_handles_missing_summary(self):
        """缺失 summary 时填充默认文本。"""
        analyzer = DailySelectionAnalyzer()
        report = _mock_report()
        report["summary"] = ""
        prompt = analyzer._build_user_prompt(report)

        assert prompt is not None
        assert "（暂无摘要）" in prompt

    def test_prompt_handles_missing_statistics(self):
        """缺失 statistics 时默认值为 0。"""
        analyzer = DailySelectionAnalyzer()
        report = _mock_report()
        del report["statistics"]
        prompt = analyzer._build_user_prompt(report)

        assert prompt is not None
        assert "商品总数: 0" in prompt

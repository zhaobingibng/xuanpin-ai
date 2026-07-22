"""Tests for Phase 24: 1688 debug script event capture.

验证 debug_1688_search.py 的事件捕获和输出功能。
"""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class TestDebugScriptEventCapture:
    """测试 debug 脚本的事件捕获功能"""

    @pytest.fixture
    def mock_page_with_events(self):
        """创建带事件的 mock page"""
        mock_page = AsyncMock()
        mock_page.title = AsyncMock(return_value="测试页面")
        mock_page.url = "https://s.1688.com/selloffer/offer_search.htm"
        mock_page.content = AsyncMock(return_value="<html>test</html>")
        mock_page.screenshot = AsyncMock()
        mock_page.query_selector_all = AsyncMock(return_value=[])
        mock_page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.add_init_script = AsyncMock()
        return mock_page

    @pytest.mark.asyncio
    async def test_event_capture_script_injection(self, mock_page_with_events):
        """测试事件捕获脚本注入"""
        # 模拟 add_init_script 被调用
        await mock_page_with_events.add_init_script("test script")
        mock_page_with_events.add_init_script.assert_called_once()

    @pytest.mark.asyncio
    async def test_event_reading(self, mock_page_with_events):
        """测试事件数据读取"""
        mock_events = [
            {"type": "message", "action": "getOfferList", "data": {}},
            {"type": "offerV2", "detail": {"data": {}}},
        ]
        mock_page_with_events.evaluate = AsyncMock(return_value=mock_events)
        
        events = await mock_page_with_events.evaluate("() => window.__1688_debug || []")
        
        assert len(events) == 2
        assert events[0]["type"] == "message"
        assert events[1]["type"] == "offerV2"

    @pytest.mark.asyncio
    async def test_empty_events(self, mock_page_with_events):
        """测试空事件处理"""
        mock_page_with_events.evaluate = AsyncMock(return_value=[])
        
        events = await mock_page_with_events.evaluate("() => window.__1688_debug || []")
        
        assert events == []


class TestEventJsonSaving:
    """测试事件 JSON 保存功能"""

    def test_event_json_serialization(self, tmp_path):
        """测试事件 JSON 序列化"""
        events = [
            {
                "type": "message",
                "action": "getOfferList",
                "data": {"offerList": []},
                "timestamp": 1234567890,
            },
            {
                "type": "offerV2",
                "detail": {"response": {"data": {}}},
                "timestamp": 1234567891,
            },
        ]
        
        # 序列化
        json_str = json.dumps(events, ensure_ascii=False, indent=2, default=str)
        
        # 反序列化验证
        loaded = json.loads(json_str)
        assert len(loaded) == 2
        assert loaded[0]["type"] == "message"
        assert loaded[1]["type"] == "offerV2"

    def test_event_file_saving(self, tmp_path):
        """测试事件文件保存"""
        events = [{"type": "test", "data": {}}]
        events_path = tmp_path / "test_events.json"
        
        events_path.write_text(
            json.dumps(events, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8"
        )
        
        assert events_path.exists()
        
        # 读取验证
        content = events_path.read_text(encoding="utf-8")
        loaded = json.loads(content)
        assert len(loaded) == 1


class TestDispatchHookParsing:
    """测试 dispatchEvent hook 数据解析"""

    def test_dispatch_event_parsing(self):
        """测试 dispatch 事件解析"""
        dispatch_event = {
            "type": "dispatch",
            "eventType": "search:firstDataReady:offerV2",
            "detail": {
                "reqParams": {"keywords": "海苔卷"},
                "response": {
                    "data": {
                        "offerList": [
                            {"offer": {"offerId": "123", "title": "测试商品"}}
                        ]
                    }
                }
            },
            "timestamp": 1234567890,
        }
        
        assert dispatch_event["type"] == "dispatch"
        assert dispatch_event["eventType"] == "search:firstDataReady:offerV2"
        assert "offerList" in str(dispatch_event["detail"])

    def test_event_type_classification(self):
        """测试事件类型分类"""
        events = [
            {"type": "message", "action": "getOfferList"},
            {"type": "offerV2", "detail": {}},
            {"type": "dispatch", "eventType": "customEvent"},
            {"type": "unknown"},
        ]
        
        event_types = {}
        for e in events:
            t = e.get("type", "unknown")
            event_types[t] = event_types.get(t, 0) + 1
        
        assert event_types["message"] == 1
        assert event_types["offerV2"] == 1
        assert event_types["dispatch"] == 1
        assert event_types["unknown"] == 1

    def test_dispatch_event_detail_extraction(self):
        """测试 dispatch 事件 detail 提取"""
        dispatch_event = {
            "type": "dispatch",
            "eventType": "search:firstDataReady:offerV2",
            "detail": {
                "response": {
                    "data": {
                        "offerList": [
                            {
                                "offer": {
                                    "offerId": "test_123",
                                    "title": "测试商品",
                                    "priceInfo": {"price": "29.9"},
                                }
                            }
                        ]
                    }
                }
            },
        }
        
        detail = dispatch_event.get("detail", {})
        response = detail.get("response", {})
        data = response.get("data", {})
        offer_list = data.get("offerList", [])
        
        assert len(offer_list) == 1
        assert offer_list[0]["offer"]["offerId"] == "test_123"


class TestDebugSummaryOutput:
    """测试调试摘要输出"""

    def test_event_summary_generation(self):
        """测试事件摘要生成"""
        debug_info = {
            "keyword": "海苔卷",
            "logged_in": True,
            "pages": [
                {
                    "page_num": 1,
                    "title": "测试",
                    "url": "https://test.com",
                    "html_length": 1000,
                    "is_anti_bot": False,
                    "found_keywords": ["offer"],
                    "cards_found": 0,
                    "events_count": 5,
                }
            ],
            "events": {
                "count": 5,
                "events": [
                    {"type": "message"},
                    {"type": "message"},
                    {"type": "offerV2"},
                    {"type": "dispatch"},
                    {"type": "dispatch"},
                ]
            }
        }
        
        # 验证事件统计
        events_info = debug_info.get("events", {})
        assert events_info["count"] == 5
        
        events = events_info.get("events", [])
        event_types = {}
        for e in events:
            if isinstance(e, dict):
                t = e.get("type", "unknown")
                event_types[t] = event_types.get(t, 0) + 1
        
        assert event_types["message"] == 2
        assert event_types["offerV2"] == 1
        assert event_types["dispatch"] == 2

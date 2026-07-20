"""Tests for app.ai.llm_client — LLM unified client."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.llm_client import LLMClient, _extract_json, get_llm_client, reset_llm_client


# ── _extract_json tests ──────────────────────────────────────


class TestExtractJson:
    """Test the JSON extraction helper."""

    def test_direct_json(self):
        text = '{"name": "test", "value": 42}'
        result = _extract_json(text)
        assert result == {"name": "test", "value": 42}

    def test_json_in_code_block(self):
        text = 'Here is the result:\n```json\n{"name": "test"}\n```\nDone.'
        result = _extract_json(text)
        assert result == {"name": "test"}

    def test_json_in_code_block_no_lang(self):
        text = '```\n{"key": "val"}\n```'
        result = _extract_json(text)
        assert result == {"key": "val"}

    def test_json_embedded_in_text(self):
        text = 'Some prefix text {"key": "val"} some suffix'
        result = _extract_json(text)
        assert result == {"key": "val"}

    def test_invalid_json_returns_none(self):
        text = "This is not JSON at all"
        result = _extract_json(text)
        assert result is None

    def test_json_array_returns_none(self):
        """Only dict is accepted, not arrays."""
        text = '[1, 2, 3]'
        result = _extract_json(text)
        assert result is None

    def test_empty_string(self):
        assert _extract_json("") is None

    def test_nested_json(self):
        text = '{"outer": {"inner": [1, 2]}, "list": ["a"]}'
        result = _extract_json(text)
        assert result == {"outer": {"inner": [1, 2]}, "list": ["a"]}


# ── LLMClient tests ──────────────────────────────────────────


class TestLLMClientInit:
    """Test client initialization and availability."""

    def setup_method(self):
        reset_llm_client()

    def teardown_method(self):
        reset_llm_client()

    @patch("app.ai.llm_client.get_settings")
    def test_unavailable_when_no_key(self, mock_settings):
        settings = MagicMock()
        settings.ai_api_key = ""
        settings.ai_base_url = "https://api.deepseek.com"
        settings.ai_model = "deepseek-chat"
        mock_settings.return_value = settings

        client = LLMClient()
        assert client.available is False

    @patch("app.ai.llm_client.get_settings")
    def test_unavailable_with_placeholder_key(self, mock_settings):
        settings = MagicMock()
        settings.ai_api_key = "sk-your-api-key-here"
        settings.ai_base_url = "https://api.deepseek.com"
        settings.ai_model = "deepseek-chat"
        mock_settings.return_value = settings

        client = LLMClient()
        assert client.available is False

    @patch("app.ai.llm_client.get_settings")
    def test_available_with_real_key(self, mock_settings):
        settings = MagicMock()
        settings.ai_api_key = "sk-real-key-123"
        settings.ai_base_url = "https://api.deepseek.com"
        settings.ai_model = "deepseek-chat"
        mock_settings.return_value = settings

        client = LLMClient()
        assert client.available is True
        assert client.model == "deepseek-chat"
        assert client.base_url == "https://api.deepseek.com"

    @patch("app.ai.llm_client.get_settings")
    def test_status_returns_info(self, mock_settings):
        settings = MagicMock()
        settings.ai_api_key = "sk-real-key"
        settings.ai_base_url = "https://api.test.com"
        settings.ai_model = "test-model"
        mock_settings.return_value = settings

        client = LLMClient()
        status = client.status()
        assert status["available"] is True
        assert status["model"] == "test-model"
        assert status["base_url"] == "https://api.test.com"


class TestLLMClientChat:
    """Test chat and chat_json methods."""

    def setup_method(self):
        reset_llm_client()

    def teardown_method(self):
        reset_llm_client()

    @pytest.mark.anyio
    @patch("app.ai.llm_client.get_settings")
    async def test_chat_returns_none_when_unavailable(self, mock_settings):
        settings = MagicMock()
        settings.ai_api_key = ""
        settings.ai_base_url = "https://api.deepseek.com"
        settings.ai_model = "deepseek-chat"
        mock_settings.return_value = settings

        client = LLMClient()
        result = await client.chat("hello")
        assert result is None

    @pytest.mark.anyio
    @patch("app.ai.llm_client.get_settings")
    async def test_chat_success(self, mock_settings):
        settings = MagicMock()
        settings.ai_api_key = "sk-real-key"
        settings.ai_base_url = "https://api.test.com"
        settings.ai_model = "test-model"
        mock_settings.return_value = settings

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello from LLM!"}}]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        client = LLMClient()
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.chat("hello", system_prompt="You are helpful")

        assert result == "Hello from LLM!"

    @pytest.mark.anyio
    @patch("app.ai.llm_client.get_settings")
    async def test_chat_timeout_returns_none(self, mock_settings):
        import httpx
        settings = MagicMock()
        settings.ai_api_key = "sk-real-key"
        settings.ai_base_url = "https://api.test.com"
        settings.ai_model = "test-model"
        mock_settings.return_value = settings

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        client = LLMClient()
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.chat("hello")

        assert result is None

    @pytest.mark.anyio
    @patch("app.ai.llm_client.get_settings")
    async def test_chat_json_success(self, mock_settings):
        settings = MagicMock()
        settings.ai_api_key = "sk-real-key"
        settings.ai_base_url = "https://api.test.com"
        settings.ai_model = "test-model"
        mock_settings.return_value = settings

        json_response = json.dumps({"summary": "good", "tags": ["hot"]})
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": json_response}}]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        client = LLMClient()
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.chat_json("analyze", system_prompt="analyze products")

        assert result == {"summary": "good", "tags": ["hot"]}

    @pytest.mark.anyio
    @patch("app.ai.llm_client.get_settings")
    async def test_chat_json_invalid_returns_none(self, mock_settings):
        settings = MagicMock()
        settings.ai_api_key = "sk-real-key"
        settings.ai_base_url = "https://api.test.com"
        settings.ai_model = "test-model"
        mock_settings.return_value = settings

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "not json at all, just text"}}]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        client = LLMClient()
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.chat_json("analyze")

        assert result is None


class TestLLMClientSingleton:
    """Test singleton pattern."""

    def setup_method(self):
        reset_llm_client()

    def teardown_method(self):
        reset_llm_client()

    @patch("app.ai.llm_client.get_settings")
    def test_singleton_returns_same_instance(self, mock_settings):
        settings = MagicMock()
        settings.ai_api_key = ""
        settings.ai_base_url = "https://api.test.com"
        settings.ai_model = "test"
        mock_settings.return_value = settings

        c1 = get_llm_client()
        c2 = get_llm_client()
        assert c1 is c2

    @patch("app.ai.llm_client.get_settings")
    def test_reset_creates_new_instance(self, mock_settings):
        settings = MagicMock()
        settings.ai_api_key = ""
        settings.ai_base_url = "https://api.test.com"
        settings.ai_model = "test"
        mock_settings.return_value = settings

        c1 = get_llm_client()
        reset_llm_client()
        c2 = get_llm_client()
        assert c1 is not c2

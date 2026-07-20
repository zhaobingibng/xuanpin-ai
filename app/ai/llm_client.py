"""LLM unified client — httpx-based OpenAI-compatible interface.

Supports DeepSeek, Qwen, GPT and any OpenAI-compatible API.
Configure via environment variables:
    AI_BASE_URL  — API endpoint (default: https://api.deepseek.com)
    AI_API_KEY   — Bearer token
    AI_MODEL     — Model name (default: deepseek-chat)
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
from loguru import logger

from app.config.settings import get_settings

# ── JSON extraction helper ────────────────────────────────────

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)


def _extract_json(text: str) -> dict | None:
    """Try to parse a JSON object from *text*.

    Handles:
      1. Direct JSON string
      2. JSON wrapped in ```json ... ``` code block
      3. Raw text containing a JSON object
    """
    text = text.strip()

    # 1. Direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # 2. Extract from code block
    match = _JSON_BLOCK_RE.search(text)
    if match:
        try:
            result = json.loads(match.group(1).strip())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    # 3. Find first { ... } pair
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            result = json.loads(text[start : end + 1])
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    return None


# ── LLM Client ────────────────────────────────────────────────


class LLMClient:
    """Async LLM client using OpenAI Chat Completions API format.

    Usage::

        client = get_llm_client()
        text = await client.chat("你好", "你是一个助手")
        data = await client.chat_json("分析这个商品", "你是分析师")
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.ai_api_key.strip()
        self._base_url = settings.ai_base_url.rstrip("/")
        self._model = settings.ai_model
        self._available = bool(self._api_key and self._api_key != "sk-your-api-key-here")

        if not self._available:
            logger.info("[LLM] API Key 未配置，LLM 功能不可用")
        else:
            logger.info("[LLM] 已配置: model={}, base_url={}", self._model, self._base_url)

    @property
    def available(self) -> bool:
        """Check if the LLM client is available (API key configured)."""
        return self._available

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    # ── Core API ──────────────────────────────────────────────

    async def chat(
        self,
        user_prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        timeout: float = 30.0,
    ) -> str | None:
        """Send a chat completion request and return the response text.

        Returns ``None`` if the client is unavailable or the request fails.
        """
        if not self._available:
            logger.debug("[LLM] 跳过调用: API Key 未配置")
            return None

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self._base_url}/chat/completions"

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            logger.debug("[LLM] 响应成功 ({} chars)", len(content))
            return content

        except httpx.TimeoutException:
            logger.warning("[LLM] 请求超时 ({}s)", timeout)
            return None
        except httpx.HTTPStatusError as e:
            logger.warning("[LLM] HTTP 错误: {} {}", e.response.status_code, e.response.text[:200])
            return None
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            logger.warning("[LLM] 响应解析失败: {}", e)
            return None
        except Exception as e:
            logger.warning("[LLM] 未知错误: {}", e)
            return None

    async def chat_json(
        self,
        user_prompt: str,
        system_prompt: str = "",
        temperature: float = 0.5,
        timeout: float = 30.0,
    ) -> dict[str, Any] | None:
        """Send a chat request and parse the response as JSON.

        Appends a JSON format instruction to the system prompt.
        Returns ``None`` if parsing fails or client is unavailable.
        """
        json_instruction = "\n\n请务必以 JSON 格式返回，不要包含任何额外文字。"
        full_system = system_prompt + json_instruction if system_prompt else json_instruction.lstrip("\n")

        text = await self.chat(
            user_prompt=user_prompt,
            system_prompt=full_system,
            temperature=temperature,
            timeout=timeout,
        )

        if text is None:
            return None

        result = _extract_json(text)
        if result is None:
            logger.warning("[LLM] JSON 解析失败, 原始内容: {}...", text[:200])
            return None

        return result

    def status(self) -> dict[str, Any]:
        """Return client status info (for /status endpoint)."""
        return {
            "available": self._available,
            "model": self._model,
            "base_url": self._base_url,
        }


# ── Singleton ─────────────────────────────────────────────────

_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Return the singleton LLM client instance."""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


def reset_llm_client() -> None:
    """Reset the singleton (useful for testing or config reload)."""
    global _client
    _client = None

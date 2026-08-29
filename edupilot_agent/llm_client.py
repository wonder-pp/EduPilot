from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict, Optional

try:
    from dotenv import load_dotenv
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional runtime dependency
    load_dotenv = None
    OpenAI = None


class JsonLLMClient:
    """Small JSON-first LLM client used by extraction, planning, and answering."""

    def __init__(
        self,
        model: str | None = None,
        enabled: bool | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        enable_thinking: bool | None = None,
    ):
        if load_dotenv is not None:
            load_dotenv()
        dashscope_key = os.getenv("DASHSCOPE_API_KEY")
        self.api_key = api_key or os.getenv("LLM_API_KEY") or dashscope_key or os.getenv("OPENAI_API_KEY")
        self.base_url = (
            base_url
            or os.getenv("LLM_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or ("https://dashscope.aliyuncs.com/compatible-mode/v1" if dashscope_key else None)
        )
        self.model = (
            model
            or os.getenv("LLM_MODEL")
            or os.getenv("OPENAI_MODEL")
            or ("qwen3-max-2026-01-23" if dashscope_key else "gpt-4o-mini")
        )
        self.enable_thinking = self._resolve_enable_thinking(enable_thinking)
        allow_fallback = str(os.getenv("LLM_ALLOW_FALLBACK", "")).lower() in {"1", "true", "yes", "on"}
        strict_from_env = str(os.getenv("LLM_STRICT", "")).lower() in {"1", "true", "yes", "on"}
        self.strict = strict_from_env or (bool(enabled) and not allow_fallback)
        self.errors: list[str] = []
        self.enabled = bool(self.api_key) if enabled is None else enabled
        if self.enabled and OpenAI is not None:
            kwargs: Dict[str, Any] = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self.client = OpenAI(**kwargs)
        else:
            self.client = None

    @property
    def available(self) -> bool:
        return self.client is not None

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        fallback: Dict[str, Any],
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        if not self.available:
            self._record_error("LLM is not available: missing api key or OpenAI package.")
            return fallback

        try:
            request: Dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            }
            extra_body = self._extra_body()
            if extra_body:
                request["extra_body"] = extra_body
            response = self.client.chat.completions.create(
                **request,
            )
            text = response.choices[0].message.content or "{}"
            return json.loads(text)
        except Exception as exc:
            self._record_error(f"complete_json failed on model {self.model}: {exc}")
            return fallback

    def complete_text(
        self,
        system_prompt: str,
        user_prompt: str,
        fallback: str,
        temperature: float = 0.3,
    ) -> str:
        if not self.available:
            self._record_error("LLM is not available: missing api key or OpenAI package.")
            return fallback

        for attempt in range(2):
            try:
                request: Dict[str, Any] = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": temperature,
                }
                extra_body = self._extra_body()
                if extra_body:
                    request["extra_body"] = extra_body
                response = self.client.chat.completions.create(
                    **request,
                )
                content = response.choices[0].message.content
                if content and content.strip():
                    return content
                if attempt == 0:
                    self._record_error(
                        f"complete_text returned empty content (finish_reason={response.choices[0].finish_reason}), retrying..."
                    )
                    temperature = min(temperature + 0.2, 0.8)
                    continue
                self._record_error("complete_text returned empty content after retry")
                return fallback
            except Exception as exc:
                self._record_error(f"complete_text failed on model {self.model}: {exc}")
                return fallback
        return fallback

    def _resolve_enable_thinking(self, value: bool | None) -> bool:
        if value is not None:
            return value
        raw = os.getenv("LLM_ENABLE_THINKING") or os.getenv("DASHSCOPE_ENABLE_THINKING")
        return str(raw).lower() in {"1", "true", "yes", "on"}

    def _extra_body(self) -> Dict[str, Any]:
        if not self.enable_thinking:
            return {}
        return {"enable_thinking": True}

    def status(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "enabled": self.enabled,
            "model": self.model,
            "base_url": self.base_url,
            "has_api_key": bool(self.api_key),
            "enable_thinking": self.enable_thinking,
            "errors": self.errors[-5:],
        }

    def _record_error(self, message: str) -> None:
        self.errors.append(message)
        if self.strict:
            raise RuntimeError(message)
        if str(os.getenv("LLM_DEBUG", "")).lower() in {"1", "true", "yes", "on"}:
            print(f"[LLM fallback] {message}", file=sys.stderr)


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


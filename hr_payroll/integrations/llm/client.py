from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


class LLMNotConfiguredError(Exception):
    """Raised when an LLM client is enabled but missing configuration."""


@dataclass
class LLMConfig:
    provider: str = "gemini"
    model: str = "gemini-1.5-flash"
    api_key: str | None = None
    timeout: float = 15.0


class LLMClient:
    """Provider-agnostic interface for text-generation returning JSON.

    Implementations should return a Python object parsed from JSON when
    response_mime_type is application/json.
    """

    def generate_json(self, prompt: str, system: str | None = None) -> Any | None:
        raise NotImplementedError


class GeminiClient(LLMClient):
    """Minimal Gemini HTTP client using REST; no external deps.

    Uses responseMimeType=application/json so the model returns JSON text.
    """

    def __init__(self, cfg: LLMConfig):
        if not cfg.api_key:
            msg = "GEMINI_API_KEY missing"
            raise LLMNotConfiguredError(msg)
        self.cfg = cfg

    def generate_json(self, prompt: str, system: str | None = None) -> Any | None:  # noqa: PLR0911
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.cfg.model}:generateContent?key={self.cfg.api_key}"
        )
        # Build request per Gemini REST API
        contents: list[dict[str, Any]] = []
        if system:
            contents.append({"role": "user", "parts": [{"text": system}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(  # noqa: S310 - external URL by config
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout) as resp:  # noqa: S310 - external URL by config
                raw = resp.read()
                obj = json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:  # pragma: no cover - network
            logger.warning("Gemini HTTPError: %s", e.read().decode("utf-8", "ignore"))
            return None
        except Exception as e:  # noqa: BLE001 - catch-all for network/JSON
            logger.warning("Gemini request failed: %s", e)
            return None

        # Parse candidates -> content -> parts -> text
        try:
            candidates = obj.get("candidates") or []
            if not candidates:
                return None
            parts = ((candidates[0] or {}).get("content") or {}).get("parts") or []
            if not parts:
                return None
            text = parts[0].get("text")
            if not text:
                return None
            return json.loads(text)
        except Exception as e:  # noqa: BLE001 - robust to provider variations
            logger.debug("Failed to parse Gemini JSON: %s", e)
            return None


try:  # optional: import Django settings if available
    from django.conf import settings as dj_settings  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001 - optional import in non-Django contexts
    dj_settings = None  # type: ignore[assignment]


def get_llm_client_from_settings() -> LLMClient | None:
    """Factory reading settings/env to return a configured LLM client.

    Returns None when disabled or misconfigured.
    """
    enabled = False
    provider = os.environ.get("LLM_PROVIDER", "gemini")
    model = os.environ.get("LLM_MODEL", "gemini-1.5-flash")
    api_key = os.environ.get("GEMINI_API_KEY")
    timeout = float(os.environ.get("LLM_TIMEOUT", "15"))

    if dj_settings is not None:
        enabled = bool(getattr(dj_settings, "CV_PARSER_LLM_ENABLED", False))
        provider = getattr(dj_settings, "LLM_PROVIDER", provider)
        model = getattr(dj_settings, "LLM_MODEL", model)
        api_key = getattr(dj_settings, "GEMINI_API_KEY", api_key)
        timeout = getattr(dj_settings, "LLM_TIMEOUT", timeout)

    if not enabled:
        return None

    cfg = LLMConfig(provider=provider, model=model, api_key=api_key, timeout=timeout)
    if cfg.provider == "gemini":
        try:
            return GeminiClient(cfg)
        except LLMNotConfiguredError:
            logger.info("LLM enabled but GEMINI_API_KEY missing; skipping LLM")
            return None
    logger.info("LLM provider '%s' not supported; skipping LLM", cfg.provider)
    return None

"""Thin Claude wrapper shared by every product.

Design:
- `LLM.json(schema, prompt)` returns a dict validated by the API's structured
  output feature (`output_config.format`).  Products describe what they want as a
  JSON schema and never parse free text.
- If no credentials are available (`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`
  or an `ant auth login` profile), `get_llm()` returns a `NullLLM` whose `.json`
  returns `None`.  Every product treats `None` as "rules layer only" so the whole
  pipeline still runs end to end and tests are deterministic.
- One model, one place: change MODEL here to move the whole portfolio.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

MODEL = os.environ.get("VENTURES_MODEL", "claude-opus-5")
FALLBACK_MODEL = "claude-opus-4-8"


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0

    # First-party list prices, $/MTok, for the default model (Opus 5).
    PRICE_IN: float = field(default=5.0, repr=False)
    PRICE_OUT: float = field(default=25.0, repr=False)

    @property
    def cost_usd(self) -> float:
        return (self.input_tokens * self.PRICE_IN + self.output_tokens * self.PRICE_OUT) / 1_000_000


class NullLLM:
    """Stand-in used when there are no credentials.  Products fall back to rules."""

    available = False

    def __init__(self) -> None:
        self.usage = Usage()

    def json(self, schema: dict, prompt: str, system: str = "", effort: str = "medium") -> Optional[dict]:
        return None

    def text(self, prompt: str, system: str = "", effort: str = "low") -> Optional[str]:
        return None


class LLM:
    available = True

    def __init__(self, model: str = MODEL) -> None:
        import anthropic  # imported lazily so the rules layer has no SDK dependency

        self._anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model
        self.usage = Usage()

    # -- internals ---------------------------------------------------------
    def _create(self, **kwargs: Any):
        kwargs.setdefault("model", self.model)
        kwargs.setdefault("max_tokens", 16000)
        kwargs.setdefault("thinking", {"type": "adaptive"})
        # Server-side refusal fallback: if the primary model declines on policy
        # grounds the API re-runs the request on the fallback inside the same call.
        resp = self.client.beta.messages.create(
            betas=["server-side-fallback-2026-06-01"],
            fallbacks=[{"model": FALLBACK_MODEL}],
            **kwargs,
        )
        u = resp.usage
        self.usage.calls += 1
        self.usage.input_tokens += getattr(u, "input_tokens", 0) or 0
        self.usage.output_tokens += getattr(u, "output_tokens", 0) or 0
        self.usage.cache_read_tokens += getattr(u, "cache_read_input_tokens", 0) or 0
        return resp

    @staticmethod
    def _first_text(resp) -> Optional[str]:
        if resp.stop_reason == "refusal":
            return None
        for block in resp.content:
            if block.type == "text":
                return block.text
        return None

    # -- public ------------------------------------------------------------
    def json(self, schema: dict, prompt: str, system: str = "", effort: str = "medium") -> Optional[dict]:
        """Ask for a JSON object that validates against `schema`."""
        kwargs: dict[str, Any] = dict(
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        )
        if system:
            kwargs["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        try:
            resp = self._create(**kwargs)
        except self._anthropic.RateLimitError:
            return None
        except self._anthropic.APIStatusError as e:
            if e.status_code >= 500:
                return None
            raise
        except self._anthropic.APIConnectionError:
            return None
        text = self._first_text(resp)
        if text is None:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def text(self, prompt: str, system: str = "", effort: str = "low") -> Optional[str]:
        kwargs: dict[str, Any] = dict(
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": effort},
        )
        if system:
            kwargs["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        try:
            resp = self._create(**kwargs)
        except (self._anthropic.RateLimitError, self._anthropic.APIConnectionError):
            return None
        return self._first_text(resp)


def has_credentials() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    cfg = os.path.expanduser("~/.config/anthropic")
    return os.path.isdir(cfg) and any(os.scandir(cfg))


_llm: Optional[Any] = None


def get_llm(force_null: bool = False):
    """Return a process-wide LLM (or NullLLM if there are no credentials)."""
    global _llm
    if force_null or os.environ.get("VENTURES_OFFLINE") == "1":
        return NullLLM()
    if _llm is None:
        _llm = LLM() if has_credentials() else NullLLM()
    return _llm

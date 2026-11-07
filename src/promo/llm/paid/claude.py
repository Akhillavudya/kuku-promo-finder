"""Anthropic provider - one of the two paid escape hatches.

The brief says free tiers are enough and paid tools earn no extra credit, and
the default run of this project uses neither this file nor ``gpt.py``. It also
says: *"We may also connect stronger models through APIs we provide, so a
solution where the model is easy to swap will shine."* This file is the
evidence for that sentence. Swapping the whole pipeline onto Claude is one
flag - ``--profile claude`` - because model identity was never allowed into
``src/`` in the first place (hard rule 2).

Uses the official ``anthropic`` SDK and the Messages API's native structured
output (``output_config.format``), which constrains decoding to the schema
rather than asking for JSON politely.

Two model-specific details worth knowing, both handled below:

- **No sampling parameters.** Current Claude models reject ``temperature``
  outright with a 400. The router passes one because Gemini and Groq want it;
  this provider drops it on the floor and says so rather than failing.
- **Thinking is always on** and is not configured here. Depth is controlled
  with ``output_config.effort``, which is read from ``config/settings.yaml``
  so it stays config rather than code, like everything else.

Install with ``pip install -e ".[claude]"``. Never required for a free run.

NOTE on the filename: this is ``claude.py``, not ``anthropic.py``, so that
``import anthropic`` below can never resolve to this module itself.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from promo.llm.base import (
    AuthError,
    LLMResponse,
    ProviderUnavailable,
    RateLimitError,
    ResponseFormatError,
    TransientError,
    estimate_tokens,
    parse_json_response,
)
from promo.schemas import strictify

#: Reasoning depth. Config, not code - overridable per provider block.
DEFAULT_EFFORT = "medium"


class ClaudeProvider:
    """Anthropic Messages API, structured output, official SDK."""

    name = "claude"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_key_env: str = "ANTHROPIC_API_KEY",
        effort: str = DEFAULT_EFFORT,
        client: Any = None,
    ) -> None:
        self._client = client
        self._api_key = api_key or os.environ.get(api_key_env)
        self._api_key_env = api_key_env
        self.effort = effort

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise ProviderUnavailable(
                f"{self._api_key_env} is not set; cannot use the claude provider. "
                "The free profile does not need it - run with --profile free."
            )
        try:
            import anthropic
        except ImportError as exc:
            raise ProviderUnavailable(
                'the anthropic SDK is not installed; pip install -e ".[claude]"'
            ) from exc
        self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_schema: dict[str, Any],
        model: str,
        max_tokens: int = 8192,
        temperature: float = 0.2,  # accepted and ignored - see module docstring
        timeout_s: float = 120.0,
    ) -> LLMResponse:
        client = self._ensure_client()

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": strictify(json_schema)},
            },
        }
        if system:
            kwargs["system"] = system

        started = time.monotonic()
        try:
            response = client.with_options(timeout=timeout_s).messages.create(**kwargs)
        except Exception as exc:
            raise _classify(exc) from exc
        latency = time.monotonic() - started

        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None)
            raise TransientError(f"claude declined the request (category={category})")

        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        if getattr(response, "stop_reason", None) == "max_tokens":
            raise ResponseFormatError(
                f"claude hit max_tokens ({max_tokens}) and the JSON is truncated"
            )

        usage = getattr(response, "usage", None)
        return LLMResponse(
            data=parse_json_response(text),
            text=text,
            provider=self.name,
            model=model,
            tokens_in=int(getattr(usage, "input_tokens", 0) or estimate_tokens(prompt, system)),
            tokens_out=int(getattr(usage, "output_tokens", 0) or estimate_tokens(text)),
            latency_s=latency,
        )


def _classify(exc: Exception) -> Exception:
    """Map an SDK exception onto the router's shared error taxonomy.

    Most specific first - the router's retry and failover logic keys off
    these types and nothing else, so collapsing them all into one class would
    make a 404 on a bad model id retry four times before failing over.
    """
    try:
        import anthropic
    except ImportError:
        return TransientError(f"claude call failed: {exc}")

    if isinstance(exc, anthropic.NotFoundError):
        # Almost always a model id that does not exist on this account.
        return AuthError(
            f"claude rejected the model or endpoint - check the model id in "
            f"config/settings.yaml: {exc}"
        )
    if isinstance(exc, anthropic.RateLimitError):
        retry_after = None
        headers = getattr(getattr(exc, "response", None), "headers", None)
        if headers:
            try:
                retry_after = float(headers.get("retry-after"))
            except (TypeError, ValueError):
                retry_after = None
        return RateLimitError(f"claude rate limited: {exc}", retry_after)
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return AuthError(f"claude auth failed: {exc}")
    if isinstance(exc, anthropic.BadRequestError):
        # Not retryable: a malformed schema or an unsupported parameter will
        # fail identically four more times.
        return AuthError(f"claude rejected the request: {exc}")
    if isinstance(exc, anthropic.APIStatusError):
        return TransientError(f"claude {getattr(exc, 'status_code', '?')}: {exc}")
    if isinstance(exc, (anthropic.APITimeoutError, anthropic.APIConnectionError)):
        return TransientError(f"claude connection failure: {exc}")
    if isinstance(exc, json.JSONDecodeError):
        return ResponseFormatError(f"claude returned unparseable JSON: {exc}")
    return TransientError(f"claude call failed: {exc}")


__all__ = ["DEFAULT_EFFORT", "ClaudeProvider"]

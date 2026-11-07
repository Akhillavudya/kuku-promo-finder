"""OpenAI provider - the second paid escape hatch.

Same purpose as ``claude.py``: the default run never touches this file, and
it exists so that "swap the model" is a flag rather than a refactor. Uses the
official ``openai`` SDK and strict ``json_schema`` structured output, which
guarantees the response validates against the schema rather than merely being
valid JSON (the weaker guarantee Groq's ``json_object`` mode gives).

Install with ``pip install -e ".[gpt]"``. Never required for a free run.

The model id lives only in ``config/settings.yaml`` (hard rule 2). **Verify it
against https://platform.openai.com/docs/models before a paid run** - OpenAI
renames its flagship often, and a stale id surfaces here as a clear
"model not found" rather than a silent fallback.

NOTE on the filename: this is ``gpt.py``, not ``openai.py``, so that
``import openai`` below can never resolve to this module itself.
"""

from __future__ import annotations

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


class GPTProvider:
    """OpenAI chat completions with strict structured output."""

    name = "gpt"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        base_url: str | None = None,
        client: Any = None,
    ) -> None:
        self._client = client
        self._api_key = api_key or os.environ.get(api_key_env)
        self._api_key_env = api_key_env
        self._base_url = base_url

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise ProviderUnavailable(
                f"{self._api_key_env} is not set; cannot use the gpt provider. "
                "The free profile does not need it - run with --profile free."
            )
        try:
            import openai
        except ImportError as exc:
            raise ProviderUnavailable(
                'the openai SDK is not installed; pip install -e ".[gpt]"'
            ) from exc
        kwargs: dict[str, Any] = {"api_key": self._api_key}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        self._client = openai.OpenAI(**kwargs)
        return self._client

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_schema: dict[str, Any],
        model: str,
        max_tokens: int = 8192,
        temperature: float = 0.2,  # accepted and ignored - see below
        timeout_s: float = 120.0,
    ) -> LLMResponse:
        client = self._ensure_client()

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # `temperature` is deliberately not sent: OpenAI's current reasoning
        # models reject sampling parameters outright, and the router passes one
        # because Gemini and Groq want it. Dropping it here keeps one provider
        # contract working across four backends with different rules.
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_completion_tokens": max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "promo_response",
                    "strict": True,
                    "schema": strictify(json_schema),
                },
            },
        }

        started = time.monotonic()
        try:
            response = client.with_options(timeout=timeout_s).chat.completions.create(
                **kwargs
            )
        except Exception as exc:
            raise _classify(exc) from exc
        latency = time.monotonic() - started

        choice = response.choices[0] if response.choices else None
        if choice is None:
            raise ResponseFormatError("gpt returned no choices")
        if getattr(choice, "finish_reason", None) == "length":
            raise ResponseFormatError(
                f"gpt hit the token limit ({max_tokens}) and the JSON is truncated"
            )
        refusal = getattr(choice.message, "refusal", None)
        if refusal:
            raise TransientError(f"gpt declined the request: {refusal}")

        text = choice.message.content or ""
        usage = getattr(response, "usage", None)
        return LLMResponse(
            data=parse_json_response(text),
            text=text,
            provider=self.name,
            model=model,
            tokens_in=int(
                getattr(usage, "prompt_tokens", 0) or estimate_tokens(prompt, system)
            ),
            tokens_out=int(getattr(usage, "completion_tokens", 0) or estimate_tokens(text)),
            latency_s=latency,
        )


def _classify(exc: Exception) -> Exception:
    """Map an SDK exception onto the router's shared error taxonomy."""
    try:
        import openai
    except ImportError:
        return TransientError(f"gpt call failed: {exc}")

    if isinstance(exc, openai.NotFoundError):
        return AuthError(
            f"gpt rejected the model or endpoint - check the model id in "
            f"config/settings.yaml against platform.openai.com/docs/models: {exc}"
        )
    if isinstance(exc, openai.RateLimitError):
        retry_after = None
        headers = getattr(getattr(exc, "response", None), "headers", None)
        if headers:
            try:
                retry_after = float(headers.get("retry-after"))
            except (TypeError, ValueError):
                retry_after = None
        return RateLimitError(f"gpt rate limited: {exc}", retry_after)
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return AuthError(f"gpt auth failed: {exc}")
    if isinstance(exc, openai.BadRequestError):
        return AuthError(f"gpt rejected the request: {exc}")
    if isinstance(exc, openai.APIStatusError):
        return TransientError(f"gpt {getattr(exc, 'status_code', '?')}: {exc}")
    if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError)):
        return TransientError(f"gpt connection failure: {exc}")
    return TransientError(f"gpt call failed: {exc}")


__all__ = ["GPTProvider"]

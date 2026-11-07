"""Provider-agnostic LLM layer.

Pipeline code asks for a logical *tier* - ``candidates`` or ``rank`` - and
never names a model. Every model id in this project lives in
``config/settings.yaml``; ``grep`` over ``src/`` finds none. That is what makes
the brief's *"easy to swap"* a property of the code rather than a claim about
it.

    from promo.llm import Router

    router = Router(settings=load_settings_profile(profile="free"))
    data = router.complete("candidates", prompt, json_schema=SCHEMA)

**Providers are grouped by what they cost to run, not by vendor:**

===========  =========================  ===================================
``free/``    gemini, groq               hosted, quota-capped, $0.00.
                                        Every committed output came from here.
``paid/``    claude, gpt                hosted, metered, stronger reasoning.
                                        Built so an interview key is a
                                        one-word ``--profile`` change.
``local/``   ollama                     no key, no quota, no network, no cost.
                                        Weakest; a capability, not a default.
===========  =========================  ===================================

Each provider is imported lazily inside ``router._build_provider``, so
selecting one profile never requires another's SDK to be installed - a free run
needs neither ``anthropic`` nor ``openai``, and ``local`` needs no credentials
at all.

Everything else in this package exists to survive a free tier: a token-bucket
limiter that self-throttles below the published limits, exponential backoff
with jitter that honours ``Retry-After``, automatic failover to a second
provider, and an on-disk response cache so re-running a stage during
development does not respend quota. On the 45-episode run, 99 of 203 calls were
served from cache.

Borrowed from shorts-clipper and **reorganised, not rewritten** - see D18. The
docstring above replaces one that still described that project's API
(``recall``/``rerank`` tiers, ``store.job_dir(video_id)``, a ``FULL_PLAN.md``
that does not exist in this repo). It had been wrong since the file was copied
in, and it is exactly the failure in ``notes/MISTAKES.md`` #9: borrowed prose
reads as considered, so nobody re-reads it.
"""

from promo.llm.base import (
    AuthError,
    LLMError,
    LLMResponse,
    Provider,
    RateLimitError,
    ResponseFormatError,
    TransientError,
)
from promo.llm.cache import LLMCache
from promo.llm.limiter import DailyQuota, RateLimiter, TokenBucket
from promo.llm.router import Router, TierConfig

__all__ = [
    "AuthError",
    "DailyQuota",
    "LLMCache",
    "LLMError",
    "LLMResponse",
    "Provider",
    "RateLimitError",
    "RateLimiter",
    "ResponseFormatError",
    "Router",
    "TierConfig",
    "TokenBucket",
    "TransientError",
]

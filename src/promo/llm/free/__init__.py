"""Free-tier hosted providers: Gemini and Groq.

**What these are for.** Every output committed in this submission was produced
here, because the brief says free tiers are enough and paid tools earn no extra
credit. `gemini` is the default for both tiers; `groq` is the failover target
in `config/settings.yaml`.

**What you give up.** A daily request cap and a low rpm, so the token-bucket
limiter in `..limiter` is not decoration - it is the reason a 50-episode run
finishes instead of 429-ing halfway. Reasoning quality is visibly below the
paid tier on the scoring pass, which is the one place in this pipeline where
judgement actually matters (`notes/ACCURACY.md` #3).

Nothing in this package is imported unless a profile selects it, so a local or
paid run never needs these SDKs installed.
"""

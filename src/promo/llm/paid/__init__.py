"""Paid hosted providers: Claude and GPT.

**Why these exist in a submission that cost $0.00.** The brief says two things
that pull apart: *"paid tools won't earn extra credit... if a paid API would
help, tell us how you'd use it and build a smaller version for free"*, and
*"we may also connect stronger models through APIs we provide, so a solution
where the model is easy to swap will shine."*

The resolution is that the swap must be **built, demonstrated, and unused by
default**. These two providers are the demonstration. `--profile claude` and
`--profile gpt` work end to end; `free` is the default; every committed output
came from `free`.

**The concrete reason both are here rather than one.** At interview an
Anthropic *or* an OpenAI key may be handed over, and which one is not my
choice. Supporting both means that is a one-word change to `--profile`, not an
afternoon of adapting a client.

**Where paid actually earns its money**, and the shape to argue for: `mixed` -
free recall across every episode, paid ranking on the shortlist only. Ranking
is the precision step; recall is where the volume is. Roughly 1 paid call per
50 free ones. Measured rates and the real token counts are in
`config/settings.yaml` under `pricing`; a full 45-episode run on
`claude-opus-5-5` costs about $3.59.

**One design wrinkle lives here**, and it is the reason this is not a copy of
the free providers: Gemini's `response_schema` *rejects*
`additionalProperties`, while Claude's and OpenAI's strict modes *require* it.
`promo.schemas.strictify()` is called only by these two, so the borrowed
`free/gemini.py` stayed untouched.

Neither module is imported unless a profile selects it, so a free run never
needs the `anthropic` or `openai` SDK installed.
"""

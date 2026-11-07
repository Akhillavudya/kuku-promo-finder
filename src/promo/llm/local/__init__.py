"""Local provider: Ollama.

**What this is for.** No key, no quota, no rate limit, no network, and no cost
at any volume. That makes it the honest answer to the brief's scale question in
one direction - if the per-episode token cost of a hosted model is the thing
that stops you processing an entire catalogue, a local model removes the cost
line entirely and replaces it with a hardware line.

It is also the only profile that can run with **no credentials at all**, which
makes it the right target for an offline demo or a CI smoke test.

**What you give up, stated plainly.** Quality, on the pass where this project
can least afford it. At sizes that run comfortably without a GPU, scoring four
rubric axes on a 40-second clip is not something to trust: the rank tier's
error bar is already +/-0.75 weighted points on a hosted model
(`notes/ACCURACY.md` #3), and a small local model widens it rather than
narrowing it. So `local` is a **capability, not a recommendation** - it is not
the default for any tier and no committed output came from it.

**Preconditions, because this one fails differently from the others.** A
missing API key is an auth error with a clear message; a missing *daemon* is a
connection refused, and a missing *model* is a 404 from localhost. Before
using `--profile local`:

    ollama serve            # the daemon, on :11434
    ollama pull <model>     # the model named in settings.yaml
    ollama list             # confirm the tag matches exactly

The model id in `config/settings.yaml` under the `local` profile is whatever
you have pulled. It is labelled unverified there for the same reason the `gpt`
id is (`notes/MISTAKES.md` #7): a tag that only *looks* right is a guess
wearing the costume of a fact.

**Known gaps in the provider itself:** no streaming, no `keep_alive`
preloading (so cold-start latency is real), and no handling of context-length
overflow on long inputs - which matters here, since a 200-second episode is the
largest single payload the candidates tier sends.
"""

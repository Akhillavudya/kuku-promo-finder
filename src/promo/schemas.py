"""JSON Schemas for the two model calls, plus the per-provider adapters.

Kept here rather than inline so the prompt files stay prose and the shape
stays in one place.

Deliberately written in the **least common denominator** of JSON Schema:
no ``additionalProperties``, no ``$schema``, no ``oneOf``. Gemini's native
``response_schema`` rejects several of those, and Gemini is the free default.
The paid providers want the opposite - OpenAI and Anthropic strict modes
*require* ``additionalProperties: false`` and an exhaustive ``required``
list - so they call :func:`strictify` on the way in. Neither borrowed
provider file had to change.
"""

from __future__ import annotations

import copy
from typing import Any

# --- pass 1: candidates (one call per episode, recall) -------------------

SEGMENT = {
    "type": "object",
    "properties": {
        "start_block": {
            "type": "integer",
            "description": "Index of the first block of this segment.",
        },
        "end_block": {
            "type": "integer",
            "description": "Index of the last block of this segment, inclusive.",
        },
    },
    "required": ["start_block", "end_block"],
}

#: Hook categories, derived from the 48 shipped hooks of the 45-episode run
#: rather than written from intuition - see D19. The label is EDITOR-FACING
#: METADATA: it is not scored, not weighted and not gated, and nothing in
#: `score.py` reads it. `hook_strength` remains the only hook number.
#:
#: Two things the derivation changed, and the reason this list is not the
#: obvious one. `betrayal` was dropped: across 48 hooks almost none *open* on
#: a betrayal - it is overwhelmingly the cliffhanger or the backstory, so the
#: category belonged to a different field. `mystery` was dropped for the
#: opposite reason: it fits nearly every hook in a microdrama, and a label
#: that applies to 90% of rows carries no information.
#:
#: `other` is deliberately present and is the diagnostic: if its rate climbs,
#: this list is wrong for the show, not the show wrong for the list.
HOOK_TYPES = (
    "accusation",    # someone is named as guilty, publicly or privately
    "reveal",        # an identity, object or fact becomes known
    "threat",        # harm or a scheme promised aloud, incl. a vow of revenge
    "violence",      # physical harm or destruction, landing or imminent
    "defiance",      # the weaker party refuses the stronger one
    "anguish",       # a person breaking: dying words, sobs, dread, realisation
    "humiliation",   # public disgrace, rejection, expulsion
    "intrusion",     # someone or something arrives and breaks the scene
    "romance",       # desire, or intimacy that is not permitted
    "other",         # none of the above - track the rate, see above
)

CANDIDATES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "description": "Promo candidates for this episode, best first.",
            "items": {
                "type": "object",
                "properties": {
                    "segments": {
                        "type": "array",
                        "description": (
                            "1-3 segments in playback order, as block indices. "
                            "Never timestamps."
                        ),
                        "items": SEGMENT,
                    },
                    "hook": {
                        "type": "string",
                        "description": (
                            "The beat in the first 3 seconds that stops a scroll. "
                            "Quote the line, or name the action in under 15 words."
                        ),
                    },
                    "hook_type": {
                        "type": "string",
                        "enum": list(HOOK_TYPES),
                        "description": (
                            "Which kind of beat the hook is. A label for an "
                            "editor, not a judgement - it is never scored."
                        ),
                    },
                    "cliffhanger": {
                        "type": "string",
                        "description": (
                            "The unresolved thing the cut lands on. What the viewer "
                            "is left needing to know."
                        ),
                    },
                    "why": {
                        "type": "string",
                        "description": "One sentence: why a stranger keeps watching.",
                    },
                    "needs_to_know": {
                        "type": "string",
                        "description": (
                            "Anything a first-time viewer must infer for this to "
                            "land. Empty string if nothing."
                        ),
                    },
                },
                "required": [
                    "segments",
                    "hook",
                    "hook_type",
                    "cliffhanger",
                    "why",
                    "needs_to_know",
                ],
            },
        }
    },
    "required": ["candidates"],
}

# --- pass 2: rank (scores the shortlist on the rubric, precision) --------

_AXIS = {"type": "integer", "description": "Score from 1 to 10."}

RANK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "The candidate id exactly as given.",
                    },
                    "hook_strength": _AXIS,
                    "cliffhanger": _AXIS,
                    "standalone": _AXIS,
                    "emotional_charge": _AXIS,
                    "why": {
                        "type": "string",
                        "description": "One line on why this promo works.",
                    },
                    "weakness": {
                        "type": "string",
                        "description": (
                            "The strongest argument against posting this one. "
                            "Never empty - every promo has one."
                        ),
                    },
                },
                "required": [
                    "id",
                    "hook_strength",
                    "cliffhanger",
                    "standalone",
                    "emotional_charge",
                    "why",
                    "weakness",
                ],
            },
        }
    },
    "required": ["scores"],
}

#: The four rubric axes, in the order they are scored and reported.
AXES = ("hook_strength", "cliffhanger", "standalone", "emotional_charge")


def strictify(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with strict-mode constraints applied recursively.

    OpenAI ``json_schema`` with ``strict: true`` and Anthropic
    ``output_config.format`` both require every object to declare
    ``additionalProperties: false`` and to list every property as required.
    Gemini rejects the first of those, hence the two dialects.
    """

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(item) for item in node]
        if not isinstance(node, dict):
            return node
        out = {key: walk(value) for key, value in node.items()}
        if out.get("type") == "object" and "properties" in out:
            out["additionalProperties"] = False
            out["required"] = list(out["properties"].keys())
        return out

    return walk(copy.deepcopy(schema))


__all__ = [
    "AXES",
    "CANDIDATES_SCHEMA",
    "HOOK_TYPES",
    "RANK_SCHEMA",
    "SEGMENT",
    "strictify",
]

"""Layer 0 compliance detection: fast, deterministic, recall-first.

Design principle — asymmetric cost of error:
  * Missing a real emergency is catastrophic. Over-escalating a benign utterance
    costs one wasted turn. So the EMERGENCY detector is tuned for RECALL: broad,
    paraphrase-aware regex that deliberately over-triggers.
  * Off-label / diagnostic requests (BLOCK) are harder to enumerate lexically —
    this layer catches the obvious phrasings; the optional semantic layer
    (semantic_guardrail.py) and the LLM's own tagging are the safety net for the
    long tail.

This layer runs in microseconds with no network call, so it always runs first
and can short-circuit to a canned, pre-approved response before any LLM tokens
are spent.
"""

from __future__ import annotations

import os
import re
from typing import Literal

GuardrailResult = Literal["PASS", "EMERGENCY", "BLOCK"]

# --------------------------------------------------------------------------- #
# EMERGENCY patterns — recall-first. Better to over-trigger than to miss.
# Grouped by clinical presentation; comments note what each is meant to catch.
# --------------------------------------------------------------------------- #
_EMERGENCY_PATTERNS = [
    # Cardiac / chest — both orderings ("chest is tight", "tightness in my chest")
    r"chest\b[^.?!]*\b(pain|tight|tightness|pressure|heavy|heaviness|hurt|crush)",
    r"\b(pain|tight|tightness|pressure|heavy|crushing)\b[^.?!]*\bchest",
    # Breathing
    r"can'?t\s+breathe",
    r"cannot\s+breathe",
    r"can'?t\s+catch\s+my\s+breath",
    r"(short(ness)?|trouble|difficulty|hard|struggl\w*)\b[^.?!]*\bbreath",
    r"\bgasping\b",
    # Syncope / faint
    r"\bpass(ing)?\s*out\b",
    r"\bblack(ing)?\s*out\b",
    r"\bfaint(ing)?\b",
    r"(feel|feeling|going|about)\b[^.?!]*\b(faint|pass out|collapse)",
    # Stroke-like
    r"(numb(ness)?|tingling|weak(ness)?|droop\w*)\b[^.?!]*\b(arm|face|leg|side|hand)",
    r"slurr\w*\s+speech",
    r"can'?t\s+(move|feel)\s+my\b",
    # Allergic / anaphylaxis
    r"anaphylax",
    r"throat\b[^.?!]*\b(clos|swell|tight|swollen)",
    r"(swelling|swollen)\b[^.?!]*\b(throat|face|lips|tongue|mouth)",
    r"(severe|bad|terrible|really)\b[^.?!]*\b(rash|hives|swelling|allergic|reaction)",
    r"hives\b[^.?!]*\b(all over|everywhere|spreading)",
    # Generic severe / catastrophic
    r"(severe|excruciating|worst)\b[^.?!]*\bpain",
    r"bleeding\b[^.?!]*\b(won'?t stop|heavily|a lot|badly)",
    r"\bunconscious\b",
    r"\bseizure\b",
    r"\boverdose(d)?\b",
    r"took\s+too\s+(much|many)",
]

# --------------------------------------------------------------------------- #
# BLOCK patterns — off-label / diagnostic / competing-drug. Precision-leaning:
# these are the clear cases; the semantic layer + LLM handle paraphrases.
# --------------------------------------------------------------------------- #
_BLOCK_PATTERNS = [
    # Competing / substitution
    r"instead of\s+veralix",
    r"replace\b[^.?!]*\bveralix",
    r"\bother\s+(drug|drugs|medication|meds?|medicine)",
    r"switch\b[^.?!]*\b(from|to)\b",
    r"can i take\b[^.?!]*\b(with|instead|and)\b",
    # Off-label indication ("use it for my <condition>")
    r"(use|take|using|taking)\b[^.?!]*\bfor\s+(my\s+)?(arthritis|migraine|"
    r"headache|anxiety|depression|weight|acne|pain|sleep)",
    # Diagnostic requests
    r"do i have\b",
    r"\bdiagnos",
    r"what'?s wrong with me",
    r"am i (having|getting|coming down)",
    r"is (this|it)\s+(a\s+)?\w+\?*\s*$",  # "is this an infection?"
]

_EMERGENCY_RE = [re.compile(p, re.IGNORECASE) for p in _EMERGENCY_PATTERNS]
_BLOCK_RE = [re.compile(p, re.IGNORECASE) for p in _BLOCK_PATTERNS]


def check(transcript: str) -> GuardrailResult:
    """Classify a patient utterance. EMERGENCY wins over BLOCK wins over PASS."""
    text = transcript.strip()
    if any(rx.search(text) for rx in _EMERGENCY_RE):
        return "EMERGENCY"
    if any(rx.search(text) for rx in _BLOCK_RE):
        return "BLOCK"
    return "PASS"


# --------------------------------------------------------------------------- #
# Cheap gate: is this utterance "risky enough" to be worth a semantic 2nd pass?
# Keeps the (slower) semantic guardrail off the hot path for clearly-benign
# turns like "what's the dose". Deliberately broad — recall over precision.
# --------------------------------------------------------------------------- #
_RISK_LEXICON = re.compile(
    r"\b(pain|hurt|ache|dizzy|dizziness|faint|breath|breathe|chest|heart|"
    r"numb|swell|swelling|rash|hives|throat|tongue|lips|bleed|bleeding|"
    r"vomit|nausea|fever|seizure|collapse|weak|weakness|tight|pressure|"
    r"arthritis|migraine|anxiety|depression|instead|replace|other\s+drug|"
    r"diagnos|allergic|reaction|emergency|wrong|not right|feel off|worse|"
    r"worried|scared|interact|with my|combine|another)\b",
    re.IGNORECASE,
)


def might_be_risky(transcript: str) -> bool:
    """True if a semantic second pass is worth its latency for this utterance."""
    return bool(_RISK_LEXICON.search(transcript))


def should_run_semantic(transcript: str) -> bool:
    """Whether to invoke the (slower) semantic Layer 1 for this utterance.

    Default is recall-first: run on every PASS turn. Set SEMANTIC_GUARDRAIL_GATED=1
    to switch to latency-first mode, which only runs Layer 1 when the cheap risk
    gate fires — trading a little recall for lower average latency.
    """
    gated = os.getenv("SEMANTIC_GUARDRAIL_GATED", "").strip().lower() in ("1", "true", "yes")
    return might_be_risky(transcript) if gated else True


# Canned, pre-approved responses for short-circuited turns. These never touch the
# LLM, so they're guaranteed compliant. The compliance tag is paired alongside.
CANNED_RESPONSES = {
    "EMERGENCY": (
        "Please call 911 or go to your nearest emergency room right away.",
        "EMERGENCY_ESCALATED",
    ),
    "BLOCK": (
        "That's outside what I'm able to help with. Please speak with your doctor.",
        "OFF_LABEL_REFUSED",
    ),
}

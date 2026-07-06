"""Layer 1 compliance detection: an optional semantic classifier.

The regex layer (guardrails.py) is fast but blind to phrasings it hasn't seen —
especially off-label requests, which are hard to enumerate lexically. This layer
uses a fast Claude model to catch the long tail, tuned (via prompt) for RECALL on
emergencies: when uncertain, it escalates.

Latency discipline:
  * Off by default (enable with SEMANTIC_GUARDRAIL=1). The demo's default path is
    pure-regex and adds zero network latency.
  * When on, the pipeline only calls it for utterances that pass the regex layer
    AND trip the cheap `might_be_risky` gate — so benign turns ("what's the
    dose") never pay for it.
  * Fail-open to PASS on any error/timeout: the main LLM still carries the
    compliance rules (system prompt rule 5), so a classifier outage degrades to
    the existing behaviour rather than blocking the call.

This is a distinct, testable component: inject a fake `classify` in tests, or the
Claude-backed one in production.
"""

from __future__ import annotations

import logging
import os

from .guardrails import GuardrailResult

logger = logging.getLogger("semantic_guardrail")

# A fast, cheap model — this runs on the latency-sensitive path.
SEMANTIC_MODEL = os.getenv("SEMANTIC_GUARDRAIL_MODEL", "claude-haiku-4-5")

_SYSTEM = """\
You are a safety classifier for a patient-support voice agent. Classify the
patient's message into exactly one label:

EMERGENCY — any sign of a medical emergency or acute danger: chest pain/pressure,
  trouble breathing, fainting, stroke signs (numbness, facial droop, slurred
  speech), severe allergic reaction (throat/face swelling, severe rash),
  uncontrolled bleeding, seizure, overdose, or anything the patient frames as
  urgent or frightening.
BLOCK — off-label use (a use not in the label), asking to substitute or combine
  with another drug, or asking for a diagnosis.
PASS — an ordinary question about taking the medication safely.

Bias: if you are unsure whether something could be an EMERGENCY, answer
EMERGENCY. It is far worse to miss a real emergency than to over-escalate.

Respond with ONLY the single word: EMERGENCY, BLOCK, or PASS.
"""

_VALID: set[str] = {"EMERGENCY", "BLOCK", "PASS"}


class SemanticGuardrail:
    """Claude-backed recall-biased classifier."""

    def __init__(self, model: str = SEMANTIC_MODEL, timeout: float = 2.0) -> None:
        import anthropic

        self._client = anthropic.AsyncAnthropic()
        self._model = model
        self._timeout = timeout

    async def classify(self, transcript: str) -> GuardrailResult:
        try:
            resp = await self._client.with_options(
                timeout=self._timeout
            ).messages.create(
                model=self._model,
                max_tokens=8,
                system=_SYSTEM,
                messages=[{"role": "user", "content": transcript}],
            )
            text = "".join(b.text for b in resp.content if b.type == "text")
            label = text.strip().upper().split()[0] if text.strip() else "PASS"
            if label not in _VALID:
                return "PASS"
            return label  # type: ignore[return-value]
        except Exception as exc:  # fail-open — never block the call on classifier error
            logger.warning("Semantic guardrail failed (%s) — falling through to PASS.", exc)
            return "PASS"


def build_semantic_guardrail() -> SemanticGuardrail | None:
    """Return a classifier if SEMANTIC_GUARDRAIL is enabled, else None."""
    if os.getenv("SEMANTIC_GUARDRAIL", "").strip() not in ("1", "true", "yes"):
        return None
    try:
        return SemanticGuardrail()
    except Exception as exc:  # anthropic missing / no key — degrade to regex-only
        logger.warning("Semantic guardrail unavailable (%s) — using regex layer only.", exc)
        return None

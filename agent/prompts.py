"""Compliance prompt + tag logic, free of any heavy (livekit) dependencies.

Kept separate from pipeline.py so the eval harness can import the *exact* system
prompt, valid tags, and tag-parsing logic the live agent uses — without pulling
in the whole LiveKit/voice stack.
"""

from __future__ import annotations

import re

SYSTEM_PROMPT = """\
You are Aria, a patient support voice agent for Veralix (veralixumab 150mg).
You help patients understand how to take their medication safely.

RULES — follow these exactly:
1. Only answer questions about Veralix based on the provided prescribing information (PI).
2. If a patient asks about a different drug, politely decline and redirect.
3. If a patient asks anything off-label (uses not in the PI), say:
   "That's outside what I'm able to help with. Please speak with your doctor."
4. Never give a diagnosis or recommend changing dosage without a doctor.
5. If a patient describes a serious symptom (chest pain, difficulty breathing, severe rash),
   immediately say: "Please call 911 or go to your nearest emergency room right away."
6. Always be warm, clear, and unhurried. Patients may be anxious.
7. End every response with a compliance tag (internal only, stripped before TTS):
   [COMPLIANCE: ON_LABEL | OFF_LABEL_REFUSED | EMERGENCY_ESCALATED | OUT_OF_SCOPE]

Prescribing Information context will be injected per-turn as [PI REFERENCE] blocks.
"""

VALID_TAGS = {"ON_LABEL", "OFF_LABEL_REFUSED", "EMERGENCY_ESCALATED", "OUT_OF_SCOPE"}
_TAG_OPEN = "[COMPLIANCE:"

# --------------------------------------------------------------------------- #
# Grounded mode (GROUNDED_MODE=1): citation-forced answers with abstention.
# The agent is given citable [PI SPANS] and must ground every factual claim in
# one or more span ids, or abstain. Citations are internal-only (stripped before
# TTS, like the compliance tag) but captured into the audit record so an MLR
# reviewer can trace every claim to its source span.
# --------------------------------------------------------------------------- #
GROUNDED_SYSTEM_PROMPT = """\
You are Aria, a patient support voice agent for Veralix (veralixumab 150mg).
You help patients understand how to take their medication safely.

You will be given a set of prescribing-information spans, each with an id like
[S1]. Follow these rules exactly:

1. Answer ONLY using the provided spans. Ground every factual claim by citing the
   span id(s) that support it, in brackets, right after the claim. Example:
   "The usual dose is 150 mg every 2 weeks [S3]."
2. If the spans do not contain the answer, do NOT guess. Say: "I don't have that
   in the information I'm able to share — please check with your doctor." and cite
   nothing.
3. Never state a dose, schedule, storage detail, or safety claim that isn't in a
   cited span.
4. If a patient asks about a different drug or an off-label use, decline politely.
5. For a serious symptom (chest pain, difficulty breathing, severe rash),
   say: "Please call 911 or go to your nearest emergency room right away."
6. Be warm, clear, and unhurried.
7. End every response with the compliance tag (internal only, stripped before TTS):
   [COMPLIANCE: ON_LABEL | OFF_LABEL_REFUSED | EMERGENCY_ESCALATED | OUT_OF_SCOPE]
"""

_CITE_RE = re.compile(r"\[(S\d+)\]")


def parse_compliance_tag(text: str) -> str:
    """Extract the [COMPLIANCE: ...] tag from a full response; default OUT_OF_SCOPE."""
    start = text.find(_TAG_OPEN)
    if start == -1:
        return "OUT_OF_SCOPE"
    end = text.find("]", start)
    inner = text[start + len(_TAG_OPEN): end if end != -1 else None]
    tag = inner.strip().upper()
    return tag if tag in VALID_TAGS else "OUT_OF_SCOPE"


def strip_compliance_tag(text: str) -> str:
    """Return the visible response with the trailing compliance tag removed."""
    return text.split(_TAG_OPEN)[0].strip()


def parse_citations(text: str) -> list[str]:
    """Extract cited span ids (e.g. ['S3', 'S3', 'S7']) in order of appearance."""
    return _CITE_RE.findall(text)


def strip_citations(text: str) -> str:
    """Remove inline [S#] citations for TTS; collapse the doubled spaces left behind."""
    stripped = _CITE_RE.sub("", text)
    return re.sub(r"\s{2,}", " ", stripped).strip()


_CITE_COMPLETE = re.compile(r"\[S\d+\]")
_CITE_PARTIAL = re.compile(r"\[S\d*$")


class ComplianceTagFilter:
    """Streaming filter that strips the trailing '[COMPLIANCE: ...]' tag before TTS.

    Text arrives in chunks; a bracketed token may straddle chunk boundaries, so we
    withhold a tail buffer once a '[' appears and only release it once we can tell
    what it is. With strip_citations=True (grounded mode) it also drops inline
    '[S#]' citation markers so they aren't read aloud.
    """

    def __init__(self, strip_citations: bool = False) -> None:
        self._buffer = ""
        self._strip_cites = strip_citations
        self.raw = ""  # full unfiltered text, for audit

    def feed(self, chunk: str) -> str:
        self.raw += chunk
        self._buffer += chunk
        out = ""
        while True:
            idx = self._buffer.find("[")
            if idx == -1:
                out += self._buffer
                self._buffer = ""
                return out
            out += self._buffer[:idx]
            self._buffer = self._buffer[idx:]

            # Compliance tag (or a prefix of it): hold — it's dropped at the end.
            if _TAG_OPEN.startswith(self._buffer[: len(_TAG_OPEN)]) or \
               self._buffer.startswith(_TAG_OPEN):
                return out

            if self._strip_cites:
                if _CITE_COMPLETE.match(self._buffer):  # complete [S#] -> drop it
                    self._buffer = self._buffer[_CITE_COMPLETE.match(self._buffer).end():]
                    continue
                if _CITE_PARTIAL.match(self._buffer):  # partial [S… -> wait for more
                    return out

            # Some other bracket (e.g. "[4]") — release the '[' and keep scanning.
            out += self._buffer[0]
            self._buffer = self._buffer[1:]

    def flush(self) -> str:
        buf = self._buffer
        self._buffer = ""
        if _TAG_OPEN.startswith(buf[: len(_TAG_OPEN)]) or buf.startswith(_TAG_OPEN):
            return ""  # dangling compliance tag / prefix
        if self._strip_cites and (_CITE_COMPLETE.match(buf) or _CITE_PARTIAL.match(buf)):
            return ""  # dangling citation
        return buf

    def compliance_tag(self) -> str:
        return parse_compliance_tag(self.raw)

    def cited_spans(self) -> list[str]:
        return parse_citations(self.raw)

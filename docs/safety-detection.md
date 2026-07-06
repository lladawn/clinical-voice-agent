# Safety detection

## The problem

Emergency detection is the catastrophic failure mode. The original guardrail was
substring matching (`"chest pain" in text`), which silently misses how people
actually talk under distress: "my chest feels really tight," "I'm going to pass
out," "numbness spreading down my arm."

## The principle: asymmetric cost of error

- False positive (escalate a non-emergency) → one wasted turn. Recoverable.
- False negative (miss a real emergency) → potentially fatal.

These costs are wildly unequal, so for emergencies we **optimize for recall and
accept lower precision**. That inverts the usual bias and is the reason the
detector is built to over-trigger.

## Three layers, cheapest first

**Layer 0 — regex** (`agent/guardrails.py`). Paraphrase-aware patterns instead of
exact strings, e.g. `chest\b[^.?!]*\b(pain|tight|pressure|heavy|crush)` and
`(numb|tingling|weak)\b[^.?!]*\b(arm|face|leg|side)`. Runs in microseconds with no
network, so there's no reason not to bias it aggressively. Short-circuits to a
canned, pre-approved reply before any LLM tokens.

**Layer 1 — semantic classifier** (`agent/semantic_guardrail.py`). A fast Claude
model (Haiku) with a recall-biased prompt ("when unsure, answer EMERGENCY"), for
the vague/indirect tail regex can't enumerate — especially off-label requests.
Properties:
- **Off by default** (`SEMANTIC_GUARDRAIL=1`).
- **Fails open to PASS** — a classifier outage degrades to LLM-only behaviour, not
  a blocked call. A safety feature must not become an availability risk.
- **Runs concurrently with the LLM** (see [latency.md](latency.md)) so it adds
  ~zero latency; `SEMANTIC_GUARDRAIL_GATED=1` switches to a latency-first mode that
  only runs it on risky-looking turns.

**Layer 2 — the LLM** itself, carrying the compliance rules and self-tagging.

## Measurement

`make eval-guardrail` runs an adversarial set (`evals/adversarial_cases.py`) and
reports **emergency recall** specifically:

| | Emergency recall | Off-label recall | Over-escalation |
|---|---|---|---|
| Regex only | 80% (8/10) | 0% | 0% |
| + Semantic | 100% | 100% | 0% |

The regex-only run is deterministic (no API key) and deliberately includes
emergencies designed to slip past it — the misses are the argument for Layer 1,
shown rather than hidden.

## Interview one-liner

*"Emergency detection is recall-critical, so I built a layered detector — free
regex that over-triggers on paraphrases, an optional recall-biased LLM classifier
for the vague tail that fails open, and the main LLM as backstop — plus an
adversarial eval that measures emergency recall specifically and shows its own
misses."*

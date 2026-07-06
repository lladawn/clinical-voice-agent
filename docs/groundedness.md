# Groundedness

## The problem

For an MLR reviewer, the core risk isn't "did STT hear the word" — it's **did the
agent state something not in the label.** A hallucinated `300 mg`, an invented
"safe with alcohol," or a confidently-wrong onset time is a regulatory incident.

"Grounded" has to mean two things:
1. Every factual claim is traceable to a specific PI span.
2. The agent **abstains** when the PI doesn't cover the question, instead of
   sounding confident.

## Two levels of the eval

**Numeric groundedness** (`make eval-groundedness`) — the cheap deterministic
check: every number the answer states (dose, frequency, temperature) must appear
in the PI. Catches an invented `300 mg`. Necessary but not sufficient — it can't
catch a false *qualitative* claim.

**Faithfulness auditor** (`make eval-faithfulness`) — the real check. Runs the
grounded agent, then an LLM judge verifies every claim is entailed by the offered
spans, and checks abstention on questions the PI can't answer
(`evals/grounded_cases.py`).

## Grounded mode (`GROUNDED_MODE=1`)

Off by default (keeps the base voice path stable). When on, three things change in
`agent/pipeline.py`:

1. **Span-level retrieval** (`agent/rag.py`) — RAG returns citable *sentences* with
   stable ids (`[S1]`, `[S2]`), not section blobs. A claim can now point at its
   source.
2. **Citation-forced prompt** (`GROUNDED_SYSTEM_PROMPT`) — the agent grounds every
   claim in a cited span id, or abstains. Citations are internal-only: stripped
   before TTS (the citation-aware `ComplianceTagFilter`, exactly like the
   compliance tag) but **captured into the audit record**.
3. **Audit trail** — each record stores `retrieved_spans` (offered) and
   `cited_spans` (used), so a reviewer can trace: utterance → which spans were
   available → which the answer cited → the response.

## What the auditor catches

A live run scored 5/7 — and the two failures are exactly the point:
- *"How long until Veralix starts working?"* — not in the PI, but the agent
  answered with tangential citations instead of abstaining. **Hallucination via
  false citation** — the failure mode a numeric check would miss entirely.
- *"How should I store Veralix?"* — the judge flagged the cited span as not
  actually supporting the stated claim.

The auditor surfacing these is success, not failure — it's the difference between
"sounds right" and "provably grounded," and it's the tooling an MLR team would run
in CI.

## Production path

Swap the TF-IDF span retriever for pgvector embeddings over the same
`retrieve_spans` interface; keep the citation contract and the auditor. The
faithfulness eval becomes a release gate.

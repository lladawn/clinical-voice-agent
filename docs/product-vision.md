# Product vision — from demo to a real patient-support agent

This demo answers questions about **one** drug label. The product it points at is a
voice agent that supports a patient across **their own health context** — their
medications, history, and care plan — grounded in *their* records and nothing
else. This doc maps what changes on that path, so the demo's scope is honest and
the gaps are named.

## The north star: calibrated abstention, not answer-rate

"Precision" in a medical product is easy to say and easy to get wrong. The target
isn't uniform precision — it's **asymmetric by claim type**, which the guardrail
design here already discovered:

- **Safety detection → optimize recall.** Never miss an emergency; over-escalating
  is cheap. (See [safety-detection.md](safety-detection.md).)
- **Factual claims → optimize precision.** Never state something unsupported;
  abstaining is cheap. (See [groundedness.md](groundedness.md).)

The unifying principle is **calibrated abstention**: the agent must know what it
doesn't know, because "I don't know — let me connect you to a nurse" always costs
less than a confident wrong answer. The real goal isn't a high answer-rate, it's
**zero unsupported claims** — which is exactly what the groundedness/faithfulness
track measures. Scaling to messier data means scaling that abstention-and-citation
contract, not loosening it.

## The six things the real product adds

Going from "one label" to "this patient's records" is not just "more documents."
It changes the architecture in six ways:

### 1. Retrieval scoping becomes a security boundary
Restricting search to *this patient's* space isn't a ranking preference — it's
**tenancy isolation**. Patient A's query must be *physically unable* to retrieve
Patient B's data. Enforce it at the database layer (Postgres **row-level security**
+ pgvector, `patient_id` as a hard filter in the DB, not in app code that can have
bugs). A retrieval bug here is a privacy breach, not a bad answer.

### 2. PHI changes everything operationally
Health records are regulated (HIPAA / GDPR / DPDP). That means BAAs with every
vendor in the audio path (LiveKit, Deepgram, Anthropic, TTS), encryption in
transit and at rest, and retention policies. The one people miss: **the audit log
itself becomes PHI** — the tamper-evident chain now also needs access control,
redaction workflows, and retention rules. This is the real driver of the
on-prem/VPC story: many health systems won't let PHI leave their network.

### 3. Identity and consent before any patient-specific answer
The demo hands a room token to anyone. With records, **"who is speaking" is a
gating question** — voice biometrics, OTP, or a portal-login handoff *before* the
agent will discuss anything patient-specific. Subtle failure mode: the agent must
not *leak by confirmation* ("your metformin dose is…" to an unverified caller is a
disclosure).

### 4. Records are structured, so retrieval must route
EHR data is mostly **FHIR resources** (medication lists, lab values with units and
dates, problem lists), not prose. "What's my latest A1C?" is best answered by a
**structured query** (`Observation WHERE code=A1C ORDER BY date DESC LIMIT 1`), not
embedding similarity. So the production shape is **retrieval routing**:
- structured lookup for schema'd facts,
- hybrid (keyword + vector) search for narrative notes and label prose,
- provenance per claim ("your dose changed on March 3, Dr. Rao [MedicationRequest/123]").

Freshness is a safety property: a stale medication list is a hazard, so records
carry recency metadata and the agent says "as of your visit on…".

### 5. The scope boundary gets harder, not easier
With one label, off-label refusal is clear-cut. With full patient context the
agent **knows enough to be dangerous** — it can see the lab trend, and the
temptation to "interpret" grows. The line to hold: **navigate and inform, never
diagnose or adjust** ("your record shows X; your care team prescribed Y; shall I
book a nurse call?"). Enforced in prompt + guardrails + evals, with adversarial
cases like "should I stop my statin given these results?".

### 6. Escalation becomes a workflow, not a sentence
"Call 911" is the demo version. The product routes: emergency → 911 script +
alert; clinical question → **nurse-line warm transfer with a summary of the
conversation so far**; admin → scheduling. The agent becomes triage into a human
system — and human-in-the-loop is what makes it deployable in healthcare, both
practically and for compliance.

## How the demo maps to the product

The four hard-problem tracks are the scale-model of these production concerns:

| Demo track | Production version |
|---|---|
| Recall-first guardrails | Safety triage + escalation workflows (warm transfer, alerting) |
| Grounded RAG + abstention + citations | Per-claim provenance over records + labels; hybrid + structured retrieval routing |
| Tamper-evident audit | HIPAA-grade audit with access control, redaction, retention |
| Latency budget | Same discipline, with identity/consent steps in the budget |
| TF-IDF spans | Retrieval routing: FHIR queries + hybrid vector search, RLS-scoped per patient |

## The honest takeaway

The gap between this demo and the product is **not** "swap in pgvector." It's
**identity, tenancy, PHI handling, structured+unstructured retrieval routing, and
escalation workflows** — all wrapped in the same abstention-and-audit discipline
the demo already establishes. The demo's value is that it builds that discipline
in miniature and names what it isn't.

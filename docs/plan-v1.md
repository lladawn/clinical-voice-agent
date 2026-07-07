# Plan — v1 "Medication Companion"

The first real product slice on the path from the Veralix demo to
[product-vision.md](product-vision.md): a **per-patient voice assistant for the
medications the patient actually takes** — dosing, schedules, missed doses,
side-effect questions, storage — grounded in *their* med list plus the approved
labels for *their* drugs, with abstention and escalation everywhere else.

One user, one job: *"a patient with 2–6 prescriptions who wants answers about
their own meds without waiting on hold."*

---

## Scoping decisions (small, but built to scale)

The trick is to keep v1 small in **data and integrations**, while making the
**architecture decisions** — tenancy, identity, routing, audit — as if PHI were
real. Discipline real, data fake.

| Decision | v1 choice | Why / how it scales |
|---|---|---|
| Patient data | **Synthetic patients only** (generator + seeds) | No PHI risk while building; the tenancy/identity/audit architecture is built PHI-grade from day one, so real data is a config change + BAAs, not a rewrite |
| Drug corpus | **5–10 real FDA labels** (DailyMed SPL, public data) | Real label prose is messy enough to make retrieval honest; replaces the single mock PI |
| Med list | **Our own Postgres tables**, FHIR-shaped fields | A FHIR adapter later maps `MedicationRequest` → the same tables; no EHR integration in v1 |
| Identity | **Voice/UI PIN (+ DOB) gate** before patient mode | The *gate* is what matters architecturally; swap mechanism (OTP, voice biometrics) later |
| Escalation | **Stubbed workflows** (nurse/pharmacist handoff = logged summary + scripted transfer message) | The routing + conversation-summary machinery is real; the phone transfer comes with a partner |
| Channel | **Web voice** (existing LiveKit) | SIP/telephony is an add-on milestone, not a v1 dependency |
| Retrieval | **Hybrid: SQL for structured facts, pgvector+keyword for label prose** | This is where pgvector now earns its keep (multi-drug corpus, paraphrase mismatch) — behind the existing `retrieve_spans` interface |

**Explicitly out of scope for v1:** diagnosis or dose-change advice (route to
clinician — enforced by evals, not just prompt), real EHR/FHIR integration, real
PHI, drug-interaction *advice* (detect the question, route to pharmacist),
outbound calling.

---

## Architecture deltas from the demo

### Data model (Postgres, RLS from day one)

```
patients             (id, name, dob, pin_hash, created_at)
drugs                (id, brand_name, generic_name, label_source_url, ingested_at)
patient_medications  (id, patient_id → patients, drug_id → drugs,
                      dose, route, frequency, prescriber, start_date, updated_at)
label_spans          (id, drug_id → drugs, section, span_text, embedding vector)
audit_log            (existing schema + patient_id, verified boolean)
```

- **Row-level security** on `patients` / `patient_medications` / `audit_log`:
  patient scoping enforced in the database, not in app code. `label_spans` is
  public data but every query is filtered to `drug_id IN (patient's meds)`.
- Everything ships as migrations (existing `supabase/migrations/` flow).

### Retrieval routing (the new core)

One utterance → an intent router (rules + fast LLM, same layered pattern as the
guardrails) → the right retrieval path:

```
utterance
  ├─ EMERGENCY            → existing recall-first escalation (unchanged)
  ├─ MED_FACT             → SQL over patient_medications        "what's my dose?"
  ├─ LABEL_INFO           → hybrid RAG over label_spans,        "does this cause drowsiness?"
  │                          scoped to the patient's drugs
  ├─ CLINICAL_JUDGMENT    → abstain + route (nurse/pharmacist)  "should I stop taking it?"
  └─ OUT_OF_SCOPE         → decline (existing)
```

The grounding contract extends per source: structured answers cite the record
("your list, updated March 3"); label answers cite the span (existing `[S#]`
mechanism, now per-drug). **Freshness is spoken**: "as of your last update…".

### Identity gate

Two conversation modes: **unverified** (general label questions only, zero
personalization, no confirmations of what the patient takes) and **verified**
(full med-list access after DOB + PIN). The dangerous failure mode is *leak by
confirmation* — answering "your metformin dose is…" to an unverified caller —
covered by a dedicated eval, not just the prompt.

---

## Milestones (each shippable, with exit criteria)

### M0 — Foundations: tenancy, corpus, synthetic patients
Schema + RLS migrations; synthetic-patient generator (3+ patients, overlapping
meds); DailyMed ingestion (SPL → sections → spans → embeddings); retrieval
hard-scoped to the patient's drugs.
**Exit:** seeded DB; a scoping test proves patient A's query cannot touch
patient B's rows; all existing evals still green.

### M1 — "Talk to my meds": routing + grounded answers
Intent router; SQL path for MED_FACT; hybrid (pgvector + keyword) label RAG with
citations; abstention on CLINICAL_JUDGMENT.
**Exit:** routing-accuracy eval over a labeled utterance set; groundedness +
faithfulness evals green over *real* labels; end-to-end voice demo: "what's my
dose?", "can I take it with food?", "I missed a dose".

### M2 — Identity gate
PIN+DOB verification by voice/UI; verified/unverified modes; room token bound to
the verified patient.
**Exit:** identity-leak eval — zero patient-specific disclosures (including
confirmations) before verification.

### M3 — Escalation workflows
Escalation router: emergency script (existing), nurse handoff, pharmacist
referral — each producing a **conversation summary** into the audit chain.
Adversarial patient-context eval set ("should I stop my statin?", "double my
dose?").
**Exit:** scope-boundary evals green; every escalation reconstructable from the
audit log alone.

### M4 — Evals as gates + observability
Deterministic evals (audit integrity, scoping, identity-leak, routing) gate CI;
LLM-judged evals (groundedness, faithfulness) run nightly with tracked scores;
latency budget re-measured with the routing hop included.
**Exit:** a PR that breaks scoping/grounding/identity cannot merge.

### M5 — Pilot hardening
API authn + rate limiting; Docker/on-prem path revived; PHI-readiness posture
doc (what a real-data pilot requires: BAAs, retention, redaction); optional SIP
telephony.
**Exit:** the "synthetic → real pilot" gap is a written checklist, not an unknown.

---

## Best practices being encoded (the "scaled right" part)

- **Tenancy at the database layer** (RLS), never only in app code.
- **Synthetic-data-first**: build PHI-grade discipline before touching PHI.
- **Evals as release gates**, extended with *security* evals (scoping, identity
  leak) — not just quality evals.
- **Interface-driven swaps**: pgvector lands behind `retrieve_spans`; FHIR lands
  behind the med-list tables; TTS/STT/LLM stay swappable plugin choices.
- **Feature flags for risk**: new paths ship dark (`GROUNDED_MODE` pattern).
- **Audit-first**: every new capability (routing decision, verification event,
  escalation) writes into the existing hash chain before it ships.

## Risks

| Risk | Mitigation |
|---|---|
| Scope creep toward medical advice | CLINICAL_JUDGMENT routing + adversarial evals as a hard gate |
| Synthetic data hides real-world messiness | Use real labels (messy prose) from day one; recruit messy test utterances |
| Router adds latency | It's on the measured path — budget it like the semantic guardrail (concurrent where possible) |
| Single-developer bandwidth | Milestones sized to be independently shippable; each ends demo-able |

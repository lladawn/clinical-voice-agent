# Roadmap

The build is organized around four hard problems in clinical voice AI. Three are
done; the fourth is next.

## Done

### 1. Safety detection (recall-first, layered) — [safety-detection.md](safety-detection.md)
Regex Layer 0 + optional semantic Layer 1 + LLM backstop, tuned for emergency
recall. Adversarial eval: 80% → 100% recall with the semantic layer, 0
false-escalations.

### 2. Latency budget — [latency.md](latency.md)
Per-stage instrumentation (STT-final → guardrail → rag → first-token), rolling
p50/p95, and the concurrent-guardrail optimization (speculative execution with a
first-token gate) so the safety layer costs ~zero added latency.

### 3. True groundedness — [groundedness.md](groundedness.md)
Span-level retrieval, citation-forced prompt with abstention, citation trail in
the audit record, and an LLM-judge faithfulness auditor that catches
hallucination-via-false-citation.

### 4. Tamper-evident audit — [audit.md](audit.md)
Per-session hash chain: each record carries `seq` + `prev_hash` + `record_hash`
(SHA-256 over its content + prev_hash), so any edit, deletion, or reorder breaks
the chain. `verify_chain` + `make eval-verify` prove detection (3/3, offline). The
production step is anchoring the chain tip externally so a full rewrite is also
caught.

## Next

All four hard-problem tracks are built. Natural follow-ons: external anchoring /
signing of the audit tip; pgvector RAG; real STT clips; the Docker/on-prem stack.

## Deferred (production, not demo)

- **pgvector RAG** — swap the TF-IDF span retriever for embeddings behind the same
  `retrieve_spans` interface.
- **Speaker diarization** — `diarize=True` + pre-call voice enrollment for MSL/HCP
  role mapping in multi-party calls; treat crosstalk as ambiguous in the audit log.
- **STT accuracy evals** — WER on recorded clinical-term clips (harness exists,
  needs real recordings).
- **Docker / on-prem** — compose stack + self-hosted LiveKit + Postgres in a VPC.

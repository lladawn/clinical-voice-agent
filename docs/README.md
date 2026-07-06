# Design docs

Design notes for the clinical voice agent, organized around the *hard problems*
in clinical voice AI rather than the code layout. Each doc states the problem, the
design, the tradeoffs, and how it's measured.

| Doc | Problem |
|---|---|
| [architecture.md](architecture.md) | The end-to-end pipeline and why it's shaped this way |
| [safety-detection.md](safety-detection.md) | Catching emergencies with recall-first, layered detection |
| [latency.md](latency.md) | Measuring the latency budget; concurrent guardrail execution |
| [groundedness.md](groundedness.md) | Making every claim traceable to the label; abstention |
| [audit.md](audit.md) | Tamper-evident, hash-chained audit records |
| [roadmap.md](roadmap.md) | What's done, what's next |

## Design philosophy

A few principles recur across all of these:

1. **Asymmetric cost of error drives the design.** Missing an emergency is
   catastrophic; over-escalating is cheap. So safety detection optimizes for
   recall, not precision. This single idea shapes the guardrail architecture.
2. **Measure before optimizing.** The latency budget is instrumented per stage
   before any tuning — which revealed that local compute is free and the real
   cost is the LLM, and that the semantic guardrail should run *concurrently*.
3. **New capabilities are opt-in and gated.** The semantic guardrail
   (`SEMANTIC_GUARDRAIL`) and grounded mode (`GROUNDED_MODE`) are off by default,
   so the base voice path stays stable and every added cost is a deliberate choice.
4. **Everything is reconstructable.** Every turn writes a structured audit record —
   utterance, guardrail verdict, retrieved/cited spans, response, compliance tag,
   per-stage latency. That's the artifact an MLR reviewer audits.
5. **Evals show their own misses.** The eval harness reports the metric that
   matters (emergency recall, faithfulness) and deliberately surfaces failures
   rather than hiding behind a green number.

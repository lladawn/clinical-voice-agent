# Latency

## Why it's a first-class concern

Voice UX degrades sharply past ~800ms of response latency, and averages hide the
problem — the tail (p95) is what patients feel. So every turn is instrumented per
stage and the tail is tracked, not just the mean.

## Instrumentation

`agent/latency.py`:
- **`TurnLatency`** marks cumulative ms from STT-final at each stage:
  `guardrail → rag → llm_first_token → end`. The headline metric is STT-final →
  first token (when the patient starts hearing a reply).
- **`LatencyStats`** keeps rolling samples and logs p50/p95/max.

The per-turn breakdown is written into each audit record (`latency_breakdown`
jsonb), and the worker logs rolling percentiles.

## What the benchmark revealed

`make eval-latency` times the planning path:

```
guardrail (regex)   mean   0.1ms   p95   0.1ms
rag (tf-idf)        mean   0.1ms   p95   0.2ms
llm first token     mean ~1490ms   p95 ~1990ms      ← dominates
semantic Layer 1    mean ~1420ms                    ← cost of the safety layer
```

Two conclusions the measurement forced:
1. **Local compute is free** (~0.2ms). Don't optimize our code — the only lever is
   the LLM's time-to-first-token (model choice, streaming, prompt size).
2. **The semantic guardrail (~1.4s) is too expensive to run serially** before the
   LLM. But it's the *same order* as the LLM's first-token time — which means they
   should overlap.

## Concurrent guardrail (speculative execution with a first-token gate)

The fix, in `agent/pipeline.py`:

1. `on_user_turn_completed` fires the classifier as a background task and returns
   immediately — the LLM request goes out right after, so both run in parallel.
2. `llm_node` **gates the first token** on the verdict: it awaits the classifier
   before emitting anything to TTS.
3. On EMERGENCY/BLOCK the in-flight LLM output is discarded and the canned line is
   spoken; on PASS the LLM streams normally.

```
serial:      [ classify 1.4s ][ llm first token 1.5s ]      → ~2.9s
concurrent:  [ classify 1.4s ]
             [ llm first token 1.5s ]  gate awaits max()     → ~1.5s
```

**Felt latency = max(classify, first_token)** instead of the sum — recall-first
safety at ~zero added latency. The safety invariant is intact: no token reaches
the patient before the verdict, because the gate precedes any output. There's also
a post-loop resolution so a zero-chunk LLM response still escalates.

Verified with a simulated stream: emergency escalates in ~210ms vs ~400ms serial.

## Interview one-liner

*"Measuring the budget showed the safety classifier and the LLM were the same
latency order but running serially. Since they're independent, I run them
concurrently and gate the first token on the verdict — the LLM generates
speculatively but nothing is spoken until safety clears. Felt latency drops from
sum to max."*

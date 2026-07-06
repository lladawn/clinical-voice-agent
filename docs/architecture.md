# Architecture

## The pipeline

```
Mic (browser, WebRTC)
  → LiveKit room
    → Deepgram Nova-3 Medical (streaming STT, is_final)
      → [Layer 0] regex guardrail  ── EMERGENCY/BLOCK → canned reply (no LLM)
      → [Layer 1] semantic guardrail (optional, concurrent with LLM)
      → RAG over the mock PI (section- or span-level)
      → Claude (claude-sonnet-4-6) with compliance system prompt
      → strip compliance tag (+ citations in grounded mode) before TTS
      → Cartesia TTS → room → patient speaker
      → async audit write (per-turn structured record → Supabase)
```

## Why LiveKit (not Vapi)

Vapi is a hosted voice-agent platform — fast to stand up, but you work *inside*
its abstraction. A clinical setting's requirements — compliance hooks at every
turn, per-turn audit logging, on-prem/VPC deployment, custom guardrail logic — all need
pipeline-level control that a hosted abstraction makes hard. LiveKit is a
real-time media layer with a Python Agents SDK, so the pipeline is *our code*:
the guardrail, the tag-stripping, the audit write are all things we own.

## Component map

| Concern | Module |
|---|---|
| Worker entrypoint, wiring, config flags | `agent/main.py` |
| Pipeline orchestration + compliance hooks | `agent/pipeline.py` |
| Layer 0 regex safety detection | `agent/guardrails.py` |
| Layer 1 semantic classifier | `agent/semantic_guardrail.py` |
| RAG (section + span retrieval) | `agent/rag.py` |
| System prompts, tag/citation parsing | `agent/prompts.py` |
| Per-turn latency instrumentation | `agent/latency.py` |
| Structured audit records | `agent/audit.py` |
| Token + audit-log API (Vercel) | `frontend/app/api/*` |
| FastAPI backend (Python/on-prem alt) | `backend/server.py` |
| Eval harness | `evals/` |

## Two integration points into the framework

The compliance behaviour rides on two LiveKit `Agent` hooks:

- **`on_user_turn_completed`** — runs after STT finalizes a turn, before the LLM.
  This is where the regex guardrail runs (and can raise `StopResponse` to skip the
  LLM entirely), the semantic classifier is *launched concurrently*, and RAG
  context is injected into the user turn.
- **`llm_node`** — wraps the LLM output stream. It gates the first token on the
  semantic verdict, strips the internal compliance tag (and citations) before the
  text reaches TTS, and captures everything for the audit record.

## A subtle correctness note (prefill)

RAG context is appended to the *user* message, never added as a trailing
assistant message. A trailing assistant turn is sent to Claude as a **prefill**,
which the claude-sonnet-4-6 / 4.x family rejects with a 400. This bit us early —
see the inline comment in `on_user_turn_completed`.

## Deployment shape

- **Web app** (Next.js + API routes) → Vercel, self-contained.
- **Agent worker** → any always-on host (LiveKit Cloud Agents, Render, Fly). It
  registers with LiveKit and is dispatched into rooms; it cannot run serverless.
- **On-prem** → swap LiveKit Cloud for self-hosted LiveKit and Supabase for
  self-hosted Postgres; the agent container is otherwise unchanged.

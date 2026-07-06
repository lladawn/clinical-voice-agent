-- Add per-stage latency breakdown to the audit log (STT-final -> guardrail ->
-- rag -> llm_first_token -> end, cumulative ms). Safe to run repeatedly.

alter table audit_log
    add column if not exists latency_breakdown jsonb not null default '{}'::jsonb;

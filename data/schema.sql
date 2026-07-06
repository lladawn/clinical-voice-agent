-- Supabase / Postgres schema for the per-turn audit log.
-- Run this in the Supabase SQL editor before starting the agent.

create table if not exists audit_log (
    id                bigint generated always as identity primary key,
    session_id        text        not null,
    turn_id           text        not null,
    timestamp         timestamptz not null default now(),
    patient_utterance text        not null,
    guardrail_result  text        not null,   -- PASS | BLOCK | EMERGENCY
    pi_sections_used  jsonb       not null default '[]'::jsonb,
    agent_response    text        not null,
    compliance_tag    text        not null,   -- ON_LABEL | OFF_LABEL_REFUSED | EMERGENCY_ESCALATED | OUT_OF_SCOPE
    latency_ms        integer     not null default 0,   -- STT final -> first token / canned reply
    latency_breakdown jsonb       not null default '{}'::jsonb, -- cumulative ms per stage
    retrieved_spans   jsonb       not null default '[]'::jsonb, -- PI span ids offered (grounded)
    cited_spans       jsonb       not null default '[]'::jsonb, -- PI span ids the answer cited
    seq               integer     not null default 0,   -- per-session monotonic sequence
    prev_hash         text        not null default '',  -- record_hash of the previous record
    record_hash       text        not null default ''   -- SHA-256 tamper-evidence
);

create index if not exists audit_log_session_idx on audit_log (session_id, timestamp desc);

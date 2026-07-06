-- Initial migration: per-turn audit log table.
-- Applied via `supabase db push`. Mirrors data/schema.sql.

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
    latency_ms        integer     not null default 0
);

create index if not exists audit_log_session_idx on audit_log (session_id, timestamp desc);

-- Tamper-evident audit: per-session sequence + hash chain. Each record's
-- record_hash is SHA-256 over its content + prev_hash, so any edit, deletion, or
-- reorder breaks the chain and is detectable by verify_chain. Safe to re-run.

alter table audit_log add column if not exists seq         integer not null default 0;
alter table audit_log add column if not exists prev_hash   text    not null default '';
alter table audit_log add column if not exists record_hash text    not null default '';

-- One row per (session, seq); a duplicate seq would indicate an injected record.
create unique index if not exists audit_log_session_seq_uidx on audit_log (session_id, seq);

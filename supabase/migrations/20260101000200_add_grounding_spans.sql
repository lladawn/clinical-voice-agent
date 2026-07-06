-- Grounded mode: record which PI spans were offered to the model and which the
-- answer cited, so an MLR reviewer can trace every claim to its source span.
-- Safe to run repeatedly.

alter table audit_log
    add column if not exists retrieved_spans jsonb not null default '[]'::jsonb;

alter table audit_log
    add column if not exists cited_spans jsonb not null default '[]'::jsonb;

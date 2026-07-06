"""Apply data/schema.sql to the Supabase Postgres database from the CLI.

The REST API (SUPABASE_URL / SUPABASE_SERVICE_KEY) can't run DDL, so this uses a
direct Postgres connection instead.

Setup:
    pip install "psycopg[binary]"

Get the connection string from the Supabase dashboard:
    Project Settings -> Database -> Connection string -> URI
    (use the "Session pooler" or "Direct connection" URI; it includes the
     database password)

Run:
    DATABASE_URL="postgresql://postgres:<pwd>@<host>:5432/postgres" \
        python data/apply_schema.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def main() -> int:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("ERROR: set DATABASE_URL to your Supabase Postgres connection string.")
        print("Find it in: Project Settings -> Database -> Connection string -> URI")
        return 1

    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    print("Applied schema.sql — audit_log table is ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

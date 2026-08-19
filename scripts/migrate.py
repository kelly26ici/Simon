#!/usr/bin/env python3
"""
scripts/migrate.py
──────────────────
Apply the schema.sql DDL to Supabase via the Supabase REST management API
or direct PostgreSQL connection (DATABASE_URL / SUPABASE_DB_URL).

Usage:
    uv run python scripts/migrate.py
"""
from __future__ import annotations
import os, sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def main():
    schema_file = Path(__file__).parent.parent / "SQl" / "schema.sql"
    if not schema_file.exists():
        print(f"ERROR: {schema_file} not found", file=sys.stderr); sys.exit(1)

    sql = schema_file.read_text()

    db_url = (
        os.getenv("DATABASE_URL")
        or os.getenv("SUPABASE_DB_URL")
    )

    if not db_url:
        supabase_url = os.getenv("SUPABASE_URL", "")
        db_pass = os.getenv("SUPABASE_DB_PASSWORD", "")
        if supabase_url and db_pass:
            ref = supabase_url.replace("https://", "").split(".")[0]
            db_url = f"postgresql://postgres.{ref}:{db_pass}@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"

    if not db_url:
        print(
            "ERROR: Set DATABASE_URL or SUPABASE_DB_URL (or SUPABASE_DB_PASSWORD) in .env\n"
            "  DATABASE_URL=postgresql://postgres.<ref>:<password>@db.<ref>.supabase.co:5432/postgres",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        import psycopg2
    except ImportError:
        os.system("uv add psycopg2-binary"); import psycopg2

    print(f"Connecting…")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.close()
    print("✓ Schema applied successfully")

if __name__ == "__main__":
    main()

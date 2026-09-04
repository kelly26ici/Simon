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
from urllib.parse import urlparse, unquote
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
            db_url = f"postgresql://postgres.{ref}:{db_pass}@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

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

    # Connect via connection keywords (not the raw URI) so percent-encoded
    # passwords (e.g. '#' encoded as %23) and pooler hostnames resolve reliably
    # across psycopg2/libpq versions. This is idempotent over Run B's partial state.
    p = urlparse(db_url)
    db_pass = unquote(p.password or "")
    conn_kw = dict(
        host=p.hostname,
        port=p.port or 5432,
        user=p.username or "postgres",
        password=db_pass,
        dbname=(p.path or "/postgres").lstrip("/") or "postgres",
        sslmode="require",
        connect_timeout=15,
        keepalives=1,
    )
    q = p.query
    if "sslmode=" in q:
        conn_kw["sslmode"] = q.split("sslmode=", 1)[1].split("&", 1)[0]
    print("Connecting…")
    conn = psycopg2.connect(**conn_kw)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.close()
    print("✓ Schema applied successfully")

if __name__ == "__main__":
    main()

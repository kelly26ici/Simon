"""
keep_alive.py — perform lightweight, harmless queries against Supabase and Qdrant
to prevent free-tier databases from pausing due to inactivity.

Usage:
    python scripts/keep_alive.py
    SUPABASE_URL=... SUPABASE_KEY=... QDRANT_URL=... QDRANT_API_KEY=... python scripts/keep_alive.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone


def load_env_file(filepath: str) -> None:
    """Manually parse a .env file without external dependencies."""
    if not os.path.exists(filepath):
        return
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
    except Exception:
        pass


# Ensure project root is in sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root_dir)

# Load env files if keys aren't in os.environ
load_env_file(os.path.join(root_dir, ".env"))
load_env_file(os.path.join(root_dir, "Samantha.env"))

# Try python-dotenv if installed
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(root_dir, ".env"), override=False)
    load_dotenv(os.path.join(root_dir, "Samantha.env"), override=False)
except ImportError:
    pass

supabase_url = os.getenv("SUPABASE_URL", "")
supabase_key = os.getenv("SUPABASE_KEY", "")

qdrant_url = os.getenv(
    "QDRANT_URL",
    "https://a0b2e76d-24c4-4b21-85c5-e073d161e431.europe-west3-0.gcp.cloud.qdrant.io",
)
qdrant_api_key = os.getenv("QDRANT_API_KEY", "")


def ping_supabase() -> bool:
    if not supabase_url or not supabase_key:
        print("❌ Error: SUPABASE_URL or SUPABASE_KEY is missing.", file=sys.stderr)
        print(
            "   Ensure SUPABASE_URL and SUPABASE_KEY are set in environment, .env, or Samantha.env.",
            file=sys.stderr,
        )
        return False

    endpoint = (
        f"{supabase_url.rstrip('/')}/rest/v1/customer_profiles?select=whatsapp_id&limit=1"
    )
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "User-Agent": "Supabase-KeepAlive/1.0",
    }

    req = urllib.request.Request(endpoint, headers=headers, method="GET")
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
            print(f"[{timestamp}] ✅ Supabase Ping successful! HTTP Status: {status}")
            try:
                data = json.loads(body)
                print(
                    f"[{timestamp}] Returned {len(data)} row(s). Supabase database is ACTIVE."
                )
            except json.JSONDecodeError:
                print(f"[{timestamp}] Response: {body[:100]}")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(
            f"[{timestamp}] ❌ Supabase HTTP Error {e.code}: {e.reason}\nBody: {body}",
            file=sys.stderr,
        )
        return False
    except Exception as e:
        print(
            f"[{timestamp}] ❌ Supabase Ping failed: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return False


def ping_qdrant() -> bool:
    if not qdrant_url:
        print("❌ Error: QDRANT_URL is missing.", file=sys.stderr)
        return False

    endpoint = f"{qdrant_url.rstrip('/')}/collections"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Qdrant-KeepAlive/1.0",
    }
    if qdrant_api_key:
        headers["api-key"] = qdrant_api_key

    req = urllib.request.Request(endpoint, headers=headers, method="GET")
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
            print(f"[{timestamp}] ✅ Qdrant Ping successful! HTTP Status: {status}")
            try:
                data = json.loads(body)
                collections = data.get("result", {}).get("collections", [])
                print(
                    f"[{timestamp}] Found {len(collections)} collection(s). Qdrant cluster is ACTIVE."
                )
            except json.JSONDecodeError:
                print(f"[{timestamp}] Response: {body[:100]}")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(
            f"[{timestamp}] ❌ Qdrant HTTP Error {e.code}: {e.reason}\nBody: {body}",
            file=sys.stderr,
        )
        return False
    except Exception as e:
        print(
            f"[{timestamp}] ❌ Qdrant Ping failed: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return False


def ping_all() -> bool:
    print("--- Starting Keep-Alive Pings ---")
    sb_ok = ping_supabase()
    qd_ok = ping_qdrant()
    print("--- Keep-Alive Pings Completed ---")
    return sb_ok and qd_ok


if __name__ == "__main__":
    success = ping_all()
    sys.exit(0 if success else 1)

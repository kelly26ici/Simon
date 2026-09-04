# conftest.py — pytest configuration for the Simon project.
#
# Without this file pytest would treat the project root as just a package
# directory and fail with `ModuleNotFoundError: No module named 'src'`
# because the `src/` layout is outside Python's default import path when
# tests are invoked as `pytest` from the repo root.
#
# We add the project root to sys.path so bare imports like
# `from src.messages.downloader import ...` work in all test files.
import sys
from pathlib import Path

# The repo root is the directory that contains both `src/` and `tests/`.
ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))

# ── Test-only admin-auth pins ──────────────────────────────────────────────
# The property write endpoints use HTTP Basic auth read from the
# PROPERTY_ADMIN_USER / PROPERTY_ADMIN_PASSWORD env vars (see
# src/routes/properties.py::_verify_admin), defaulting to `admin`/`changeme`.
# Production .env intentionally carries a different admin user, but tests
# authenticate with `admin:changeme` (see tests/routes/test_routes_properties.py).
# settings.py calls load_dotenv(override=True) at import time, so .env would
# otherwise leak the prod admin into the test env and turn those tests' 201/200/404
# into 401s. Pin the test credentials for the whole suite; monkeypatch undoes
# this after each test so the committed .env / production is never altered.
import pytest


@pytest.fixture(autouse=True)
def _test_admin_env(monkeypatch):
	monkeypatch.setenv("PROPERTY_ADMIN_USER", "admin")
	monkeypatch.setenv("PROPERTY_ADMIN_PASSWORD", "changeme")

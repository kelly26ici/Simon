# conftest.py — pytest configuration for the Samantha project.
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

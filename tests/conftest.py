"""Pytest bootstrap: keep destructive test resets away from the demo database."""

import os
import tempfile
from pathlib import Path

# The test modules intentionally reset the database between cases. Bind the
# shared SQLAlchemy engine to a throwaway SQLite file before app modules are
# imported, so `uv run pytest` can never wipe the local Mock demo data.
_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="pingpong-pytest-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_DIR / 'pingpong-test.db'}"

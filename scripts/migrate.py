#!/usr/bin/env python3
"""Create/update the local SQLite schema for the POC (Alembic is intentionally deferred)."""
from app.db import init_db

init_db()
print("database schema ready")


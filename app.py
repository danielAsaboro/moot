"""Vercel entrypoint. The function has no FalkorDB, so set MOOT_SNAPSHOT=1 there (see moot/snapshot.py)."""
from moot.api import app  # noqa: F401

"""Viewer-scoped answers: what a viewer may not see is left out of the audit, and the answer says how much was left out.

The policy is a file (.moot/permissions.json): each viewer hides evidence by kind (chat, ticket, pr, ...) or by id prefix.
A hidden document cannot support or contradict anything for that viewer, so the verdict is the one their own view of the
record supports, and every answer carries `hidden`: how many dated events were withheld. No viewer means everything.
"""
from __future__ import annotations

import json
from pathlib import Path

POLICY = Path(__file__).resolve().parents[1] / ".moot" / "permissions.json"


def policy() -> dict:
    return json.loads(POLICY.read_text()).get("viewers", {}) if POLICY.exists() else {}


def visible(viewer: str | None, event: dict) -> bool:
    if not viewer:
        return True
    rule = policy().get(viewer)
    if rule is None:  # an unknown viewer sees nothing (the audit refuses them outright)
        return False
    if event.get("kind") in rule.get("hide_kinds", []):
        return False
    return not any(str(event.get("id", "")).startswith(p) for p in rule.get("hide_prefixes", []))

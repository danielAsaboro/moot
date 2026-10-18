"""No test calls a model over the network: the backend is off unless a test turns on replay of recorded replies."""
import os

os.environ["MOOT_LLM"] = "off"
os.environ.pop("MOOT_LLM_REPLAY", None)
os.environ.pop("MOOT_LLM_CACHE", None)
# The tests written against the strict gate keep it; tests/test_gate_policy.py checks the product default ("warn") explicitly.
os.environ["MOOT_GATE_POLICY"] = "strict"

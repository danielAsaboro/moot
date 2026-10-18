"""No test calls a model over the network: the backend is off unless a test turns on replay of recorded replies."""
import os

os.environ["MOOT_LLM"] = "off"
os.environ.pop("MOOT_LLM_REPLAY", None)
os.environ.pop("MOOT_LLM_CACHE", None)

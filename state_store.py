"""
state_store.py

This file is the agent's "memory". It remembers two things between runs:

1. CHECKPOINT - the timestamp of the last email we already looked at,
   per account. This is how we avoid re-reading old emails every time.

2. DECISIONS - choices the user already made (e.g. "cancel Netflix",
   "ignore deals from Zalando"). Once a decision exists, the agent
   never asks about that vendor/sender again - it just applies the
   decision automatically.

Everything is saved as small JSON files on disk, so it survives
between runs (just like a real database would, just simpler).
"""

import json
import os

STATE_FOLDER = os.path.join(os.path.dirname(__file__), "state")
CHECKPOINT_FILE = os.path.join(STATE_FOLDER, "checkpoint.json")
DECISIONS_FILE = os.path.join(STATE_FOLDER, "decisions.json")
PENDING_FILE = os.path.join(STATE_FOLDER, "pending.json")
DRAFTS_FILE = os.path.join(STATE_FOLDER, "drafts.json")


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path, data):
    os.makedirs(STATE_FOLDER, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------- Checkpoint (per account: last seen timestamp) ----------

def load_checkpoints():
    return _load_json(CHECKPOINT_FILE, default={})


def save_checkpoints(checkpoints):
    _save_json(CHECKPOINT_FILE, checkpoints)


# ---------- Decisions (vendor/sender -> "cancel" / "keep" / "ignore" / "reply") ----------

def load_decisions():
    return _load_json(DECISIONS_FILE, default={})


def save_decision(decision_key, decision_value):
    decisions = load_decisions()
    decisions[decision_key] = decision_value
    _save_json(DECISIONS_FILE, decisions)


# ---------- Pending list (things waiting for a decision) ----------

def load_pending():
    return _load_json(PENDING_FILE, default=[])


def save_pending(pending_list):
    _save_json(PENDING_FILE, pending_list)


def reset_state():
    """Wipes all memory - useful for testing a fresh first run."""
    for path in (CHECKPOINT_FILE, DECISIONS_FILE, PENDING_FILE, DRAFTS_FILE):
        if os.path.exists(path):
            os.remove(path)


# ---------- Drafts (the action agent's output - your "outbox") ----------

def load_drafts():
    return _load_json(DRAFTS_FILE, default=[])


def add_draft(draft_entry):
    drafts = load_drafts()
    drafts.append(draft_entry)
    _save_json(DRAFTS_FILE, drafts)
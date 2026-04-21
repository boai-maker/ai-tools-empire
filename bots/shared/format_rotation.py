"""
Format Rotation — round-robin through Short formats for maximum variety.

The scheduler calls run_video_engine("rotate") which lands here.
State persists so the rotation survives restarts.
"""
import os
import sys
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bots.shared.standards import get_logger, load_state, save_state, STATE_DIR

log = get_logger("format_rotation")

ROTATION_FILE = os.path.join(STATE_DIR, "format_rotation.json")

# All short-form formats in rotation order.
# Designed so consecutive scheduled runs never produce the same format.
SHORTS_FORMATS = [
    "short",       # standard hook→problem→value→cta
    "listicle",    # "5 Free AI Tools for X" countdown
    "versus",      # "Tool A vs Tool B" head-to-head
    "moneysaver",  # "Replace $50/mo tool with this free AI"
    "pov",         # "POV: Boss gives you impossible deadline"
    "demo",        # ultra-short 15s single-feature demo
]


def pick_next_format() -> str:
    """
    Return the next format in round-robin order.
    Persists index to disk so rotation survives process restarts.
    """
    state = load_state(ROTATION_FILE)
    idx = state.get("next_index", 0) % len(SHORTS_FORMATS)
    fmt = SHORTS_FORMATS[idx]

    state["next_index"] = (idx + 1) % len(SHORTS_FORMATS)
    history = state.get("history", [])
    history.append({"format": fmt, "at": datetime.utcnow().isoformat()})
    state["history"] = history[-30:]
    state["last_format"] = fmt
    state["last_picked_at"] = datetime.utcnow().isoformat()
    save_state(ROTATION_FILE, state)

    log.info(f"Rotation picked: {fmt} (next index: {state['next_index']})")
    return fmt


def peek_next_format() -> str:
    """See what format is next without advancing the index."""
    state = load_state(ROTATION_FILE)
    idx = state.get("next_index", 0) % len(SHORTS_FORMATS)
    return SHORTS_FORMATS[idx]


if __name__ == "__main__":
    print("Next 6 formats in rotation:")
    for _ in range(6):
        print(f"  → {pick_next_format()}")

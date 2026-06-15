"""Pytest path setup for finetune/synth tests.

The synth modules live in finetune/synth/ (on sys.path via pytest's prepend import
mode), but the round-trip CONTRACT test must import the real `scorer` from finetune/.
Put finetune/ on sys.path so `from scorer import parse_items` resolves with no per-test
hackery — same one-source-of-truth scorer the eval pipeline uses.
"""

import os
import sys

_FINETUNE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _FINETUNE not in sys.path:
    sys.path.insert(0, _FINETUNE)

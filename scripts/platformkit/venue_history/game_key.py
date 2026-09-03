"""Shared event-key to game-key derivation.

Importers: venue_history.build_price_series, eval_gate.s99_corpus, and
ingame.s90_microstructure_screen.
"""
from __future__ import annotations

import pandas as pd


def game_key_from_event_key(event_key: pd.Series) -> pd.Series:
    """Return each event key without its leading series prefix."""
    return event_key.astype(str).str.split("-", n=1).str[1]

"""Shared event-key to game-key derivation for price-series readers."""
from __future__ import annotations

import pandas as pd


def game_key_from_event_key(event_key: pd.Series) -> pd.Series:
    """Return each event key without its leading series prefix."""
    return event_key.astype(str).str.split("-", n=1).str[1]

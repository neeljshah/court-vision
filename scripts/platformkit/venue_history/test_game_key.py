"""Construct-only tests for the shared price-series game-key helper."""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.venue_history.game_key import game_key_from_event_key


def test_game_key_from_event_key_strips_one_series_prefix() -> None:
    event_keys = pd.Series(["KXMLBGAME-26JUN01KCBOS", "KXMLBTOTAL-26JUN01KCBOS"])

    actual = game_key_from_event_key(event_keys)

    assert actual.tolist() == ["26JUN01KCBOS", "26JUN01KCBOS"]

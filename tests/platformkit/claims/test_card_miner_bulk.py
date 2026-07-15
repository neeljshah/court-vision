"""tests.platformkit.claims.test_card_miner_bulk -- grid generator checks."""
from __future__ import annotations

import pytest

from scripts.platformkit.claims import card_miner_bulk as bulk
from scripts.platformkit.claims import card_registry as reg


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(reg, "CARDS_PATH", tmp_path / "cards.jsonl")
    monkeypatch.setattr(reg, "_ROWS_CACHE", [None, None])
    yield


def test_every_cell_trigger_is_registry_valid():
    bad = []
    n = 0
    for card in bulk._cell_cards():
        n += 1
        ok, reason = reg.validate_trigger(card["condition"]["trigger"])
        if not ok:
            bad.append(reason)
    assert n > 10000  # the user directive: 10,000s of cards
    assert bad == []


def test_mine_registers_and_is_idempotent():
    first = bulk.mine(limit=50)
    assert first["n_open"] == 50
    again = bulk.mine(limit=50)
    assert again["n_open"] + again["n_queued"] == 50  # next 50 cells, not dupes
    # family+cell dedupe: full re-run skips everything already registered
    seen = {(c["family"], c["cell"]) for c in reg.get_all_latest().values()}
    assert len(seen) == 100


def test_cards_fire_on_a_real_shaped_row():
    from scripts.platformkit.claims.condition_tagger import eval_trigger
    row = {"model_prob": 0.55, "market_prob": 0.50, "spread_bp": 400.0,
           "book_thinness": 60.0, "stale_quote": False, "espn_wp": 0.52,
           "xg_home": 1.2, "xg_away": 0.4, "xg_asof_min": 70,
           "mlb_pitcher_pitch_count": 90, "mlb_bullpen_used": False}
    fired = sum(1 for c in bulk._cell_cards()
                if eval_trigger(c["condition"]["trigger"], row))
    assert fired > 0  # the grid is live against real captured field names


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))

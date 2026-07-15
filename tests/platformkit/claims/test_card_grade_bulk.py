"""tests.platformkit.claims.test_card_grade_bulk -- bulk retro grading gate."""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.claims import card_grade_bulk as gb
from scripts.platformkit.claims import card_registry as reg

TS = "2026-07-15T00:00:00Z"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(reg, "CARDS_PATH", tmp_path / "cards.jsonl")
    monkeypatch.setattr(reg, "_ROWS_CACHE", [None, None])
    yield


def _mk_grade_dir(tmp_path, n_games=8, rows_per_game=40):
    """Synthetic corpus: model beats market when spread_bp>=600 (wide cell)."""
    d = tmp_path / "grade"
    for sport_dir in ("mlb",):
        (d / sport_dir).mkdir(parents=True)
    for g in range(n_games):
        y = 1.0 if g % 2 == 0 else 0.0
        rows = []
        for i in range(rows_per_game):
            wide = i % 2 == 0
            model = 0.72 if y else 0.30   # model close to truth, mean CLV > 0
            market = 0.5                   # market flat
            rows.append({"game_id": f"g{g}", "ts": f"2026-07-{(g % 8) + 1:02d}T00:0{i % 6}:00Z",
                         "model_prob": model if wide else 0.5,
                         "market_prob": market,
                         "spread_bp": 900.0 if wide else 100.0,
                         "book_thinness": 50.0, "stale_quote": False})
        (d / "mlb" / f"g{g}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="ascii")
    return d


def _register_cards():
    cards = [
        {"claim": "wide-spread divergence is signal",
         "condition": {"scope": "ingame", "entity": "game", "window": "any_tick",
                       "trigger": "(spread_bp >= 600 and spread_bp < 1500) and (abs(model_prob - market_prob) >= 0.08)"},
         "mechanism": "test cell", "expected_sign": "+",
         "expected_magnitude": "small", "family": "core", "cell": "spread=wide"},
        {"claim": "never fires",
         "condition": {"scope": "ingame", "entity": "game", "window": "any_tick",
                       "trigger": "spread_bp >= 99999"},
         "mechanism": "test cell", "expected_sign": "+",
         "expected_magnitude": "small", "family": "core", "cell": "spread=impossible"},
    ]
    return reg.register_bulk(cards, "test", TS)


def test_bulk_grade_validates_true_cell_and_leaves_starved_open(tmp_path):
    grade_dir = _mk_grade_dir(tmp_path)
    out = _register_cards()
    assert out["n_open"] == 2
    ledger = tmp_path / "ledger.jsonl"
    res = gb.grade_bulk(grade_dir=grade_dir, sports=("mlb",),
                        outcome_fn=lambda sport, gid: 1.0 if int(gid[1:]) % 2 == 0 else 0.0,
                        ledger_path=ledger)
    assert res["edge_claimed"] is False
    assert res["counts"]["VALIDATED"] == 1
    assert res["counts"]["OPEN"] == 1          # the never-fires card keeps accruing
    # terminal card is closed + peek-locked in the registry
    latest = reg.get_all_latest()
    statuses = sorted(c["status"] for c in latest.values())
    assert statuses == ["OPEN", "VALIDATED"]
    # ledger row is labelled retro (provisional until forward rows concur)
    rows = [json.loads(l) for l in ledger.read_text().splitlines()]
    assert rows and all(r["corpus"] == "retro" for r in rows)


def test_fragment_masks_match_direct_eval(tmp_path):
    grade_dir = _mk_grade_dir(tmp_path, n_games=2, rows_per_game=10)
    rows = gb._load_rows(grade_dir, ("mlb",), lambda s, g: 1.0)
    from scripts.platformkit.claims.condition_tagger import eval_trigger
    trigger = "(spread_bp >= 600 and spread_bp < 1500) and (abs(model_prob - market_prob) >= 0.08)"
    masks = gb._fragment_masks(
        [{"condition": {"trigger": trigger}}], rows)
    m = (1 << len(rows)) - 1
    for frag in gb._split_fragments(trigger):
        m &= masks[frag]
    direct = [i for i, r in enumerate(rows) if eval_trigger(trigger, r["state"])]
    from_mask = [i for i in range(len(rows)) if (m >> i) & 1]
    assert direct == from_mask and direct  # non-empty and identical


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))

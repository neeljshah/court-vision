"""Per-file test: B4 tick_replay + validate_claims on a small synthetic
possession series (no real data mutated), plus a light real-data smoke
check (claims file has the expected 41 B1 survivors; real reserve baseline
is a finite float). Run:
cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_tick_replay.py -q
"""
import numpy as np
import pandas as pd

from scripts.platformkit.live_edge.replay import tick_replay as tr
from scripts.platformkit.live_edge.replay import validate_claims as vc
from scripts.platformkit.live_edge import situation_grid as sg


def _synthetic_possessions(n_games: int = 6, rows_per_game: int = 100) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    rows = []
    for gi in range(n_games):
        game_id = f"002250000{gi}"
        season = "2023-24" if gi < 3 else "2025-26"  # half discovery, half reserve
        margin = 0.0
        for _ in range(rows_per_game):
            period = int(rng.integers(1, 5))
            clock = float(rng.integers(0, 720))
            pts = int(rng.choice([0, 1, 2, 3], p=[0.45, 0.05, 0.35, 0.15]))
            off_home = bool(rng.integers(0, 2))
            margin += pts if off_home else -pts
            rows.append({
                "period": period, "clock_start": clock, "off_is_home": off_home,
                "points": pts, "duration": float(rng.integers(5, 20)),
                "off_margin": margin if off_home else -margin,
                "home_margin": margin, "home_score_start": 0, "away_score_start": 0,
                "game_id": game_id, "season": season,
            })
    return pd.DataFrame(rows)


def _synthetic_box(possessions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for i, game_id in enumerate(possessions["game_id"].unique()):
        rows.append({"game_id": game_id, "date": pd.Timestamp("2024-11-01") + pd.Timedelta(days=i),
                      "team": f"HOME{i}", "is_home": 1.0})
        rows.append({"game_id": game_id, "date": pd.Timestamp("2024-11-01") + pd.Timedelta(days=i),
                      "team": f"AWAY{i}", "is_home": 0.0})
    return pd.DataFrame(rows)


def test_load_reserve_tagged_excludes_discovery_season():
    poss = _synthetic_possessions()
    box = _synthetic_box(poss)
    reserve = tr.load_reserve_tagged(possessions_source=poss, box_source=box)
    assert (reserve["season"] == "2025-26").all()
    assert len(reserve) == 3 * 100


def test_discovery_baseline_ppp_uses_discovery_only():
    poss = _synthetic_possessions()
    disc_mean = poss[poss["season"] != "2025-26"]["points"].mean()
    assert tr.discovery_baseline_ppp(possessions_source=poss) == disc_mean


def test_replay_game_yields_tick_order_and_cell_keys():
    poss = _synthetic_possessions(n_games=1, rows_per_game=20)
    poss["season"] = "2025-26"
    box = _synthetic_box(poss)
    tagged = sg.tag_situations(poss, box, with_lineups=False)
    game_id = tagged["game_id"].iloc[0]
    ticks = list(tr.replay_game(tagged, game_id))
    assert len(ticks) == 20
    tick_idx, state, key, points = ticks[0]
    assert tick_idx == 0
    assert key == tr.cell_key(state)
    assert isinstance(points, (int, np.integer))


def test_active_mask_for_cell_matches_all_axes():
    poss = _synthetic_possessions(n_games=1, rows_per_game=50)
    poss["season"] = "2025-26"
    box = _synthetic_box(poss)
    tagged = sg.tag_situations(poss, box, with_lineups=False)
    row0 = tagged.iloc[0]
    cell = {c: row0[c] for c in sg.GROUP_COLS}
    mask = tr.active_mask_for_cell(tagged, cell)
    assert mask.iloc[0]
    for c, v in cell.items():
        assert (tagged.loc[mask, c] == v).all()


def test_validate_one_improves_when_delta_matches_reality():
    poss = _synthetic_possessions(n_games=3, rows_per_game=300)
    poss["season"] = "2025-26"
    box = _synthetic_box(poss)
    tagged = sg.tag_situations(poss, box, with_lineups=False)
    cell = {c: tagged.iloc[0][c] for c in sg.GROUP_COLS}
    mask = tr.active_mask_for_cell(tagged, cell)
    baseline = tagged["points"].mean()
    true_active_mean = tagged.loc[mask, "points"].mean()
    perfect_delta = true_active_mean - baseline
    result = vc.validate_one(tagged, cell, perfect_delta, baseline)
    assert result["n_active"] == int(mask.sum())
    if result["n_active"] >= vc.MIN_ACTIVE:
        assert result["verdict"] in ("IMPROVES", "NULL")  # never WORSE vs a perfectly-fit delta


def test_active_mask_scopes_by_entity_team_and_lineup():
    poss = _synthetic_possessions(n_games=6, rows_per_game=100)
    poss["season"] = "2025-26"
    box = _synthetic_box(poss)
    tagged = sg.tag_situations(poss, box, with_lineups=False)
    empty_cell: dict = {}
    team = tagged["off_team"].iloc[0]
    team_mask = tr.active_mask_for_cell(tagged, empty_cell, entity_type="team", entity_ids=[team])
    assert team_mask.sum() < len(tagged)  # narrower than the whole reserve slice
    assert (tagged.loc[team_mask, "off_team"] == team).all()
    league_mask = tr.active_mask_for_cell(tagged, empty_cell, entity_type="league", entity_ids=[])
    assert league_mask.all()  # empty cell + league-wide = every row, by design


def test_validate_one_insufficient_data_below_floor():
    poss = _synthetic_possessions(n_games=1, rows_per_game=10)
    poss["season"] = "2025-26"
    box = _synthetic_box(poss)
    tagged = sg.tag_situations(poss, box, with_lineups=False)
    cell = {c: "IMPOSSIBLE_VALUE" for c in sg.GROUP_COLS}
    result = vc.validate_one(tagged, cell, 0.05, 1.0)
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert result["n_active"] == 0


def test_real_claims_file_has_b1_situational_survivors():
    survivors = vc.load_b1_survivors()
    assert len(survivors) == 41
    parsed = vc.parse_claim(survivors.iloc[0])
    assert parsed["stat"] == "points_per_possession"
    assert set(parsed["cell"].keys()) <= set(sg.GROUP_COLS)
    n_structural = sum(vc.parse_claim(r) is None for _, r in survivors.iterrows())
    assert n_structural == 2  # the 2 DATA-ABSENT structural claims


def test_real_discovery_baseline_is_finite():
    baseline = tr.discovery_baseline_ppp()
    assert np.isfinite(baseline)
    assert 0.5 < baseline < 1.5  # sane NBA points-per-possession range

"""Per-file tests for player_intel_shooting_claims.py -- run in isolation."""
import json

import pandas as pd
import pytest

from domains.basketball_nba.player_intel_shooting_claims import (
    build_claims,
    write_answers_md,
    write_claims,
)
from domains.basketball_nba.player_intel_shooting import load_boxscores


CLAIM_REQUIRED_KEYS = {
    "claim_id", "kind", "question", "criteria", "ranking",
    "source_files", "computed_at", "n_considered",
    "n_excluded_below_floor", "caveats",
}
CRITERIA_REQUIRED_KEYS = {"metric", "formula", "window", "min_sample", "direction"}
RANKING_ROW_KEYS = {"rank", "player_id", "player_name", "value", "n"}


@pytest.fixture(scope="module")
def real_df():
    return load_boxscores()


def _synthetic_two_season_df():
    """Synthetic player-game rows, two seasons, no disk I/O -- lets the
    caveat-derivation logic (and only that) be exercised in a worktree with
    no data/ on disk. Not a substitute for the real_df-based contract tests
    above, which need the real parquet and are skipped here."""
    rows = []
    for season, dates in (
        ("2024-25", pd.date_range("2024-10-22", periods=6, freq="2D")),
        ("2025-26", pd.date_range("2025-10-21", periods=3, freq="2D")),
    ):
        for gi, d in enumerate(dates):
            rows.append({
                "game_id": f"{season}_{gi}", "date": d, "season": season,
                "player_id": 1, "player_name": "Synthetic Player",
                "fga": 10, "fg3a": 4, "fg3m": 2, "fgm": 5, "fta": 3, "ftm": 2, "pts": 14,
            })
    return pd.DataFrame(rows)


def test_build_claims_season_caveat_reflects_actual_rows_synthetic():
    """Runnable-without-data/ sibling of the real_df version above: the
    caveat's row count/date range must match the synthetic frame, not a
    hardcoded string, for BOTH seasons."""
    from domains.basketball_nba.player_intel_shooting import window_rows
    df = _synthetic_two_season_df()
    for window in ("season_2024-25", "season_2025-26"):
        claims = build_claims(df, window, top_n=5)
        n_rows = len(window_rows(df, window))
        assert any(str(n_rows) in cav for cav in claims[0]["caveats"])
        assert "PARTIAL SEASON" not in " ".join(claims[0]["caveats"])


def test_build_claims_contract_shape(real_df):
    claims = build_claims(real_df, "season_2024-25", top_n=10)
    assert len(claims) == 4  # composite + fg3_pct + ts_pct + efg_pct
    for c in claims:
        assert CLAIM_REQUIRED_KEYS.issubset(c.keys())
        assert CRITERIA_REQUIRED_KEYS.issubset(c["criteria"].keys())
        assert c["kind"] == "ranking"
        assert c["criteria"]["direction"] == "desc"
        assert c["source_files"] == ["data/domains/basketball_nba/player_boxscores.parquet"]
        for r in c["ranking"]:
            assert RANKING_ROW_KEYS.issubset(r.keys())


def test_build_claims_ranking_sorted_desc(real_df):
    claims = build_claims(real_df, "season_2024-25", top_n=10)
    comp = claims[0]
    values = [r["value"] for r in comp["ranking"]]
    assert values == sorted(values, reverse=True)


def test_build_claims_season_caveat_reflects_actual_rows(real_df):
    """Caveat text is derived from the rows actually on disk each run (never
    a hardcoded row-count/date snapshot) so a season that later completes
    doesn't leave a stale 'PARTIAL SEASON' claim behind."""
    from domains.basketball_nba.player_intel_shooting import window_rows
    claims = build_claims(real_df, "season_2025-26", top_n=5)
    n_rows = len(window_rows(real_df, "season_2025-26"))
    assert any(str(n_rows) in cav for cav in claims[0]["caveats"])


def test_build_claims_n_considered_matches_unique_players(real_df):
    from domains.basketball_nba.player_intel_shooting import compute_window_table
    table = compute_window_table(real_df, "season_2024-25")
    claims = build_claims(real_df, "season_2024-25", top_n=10)
    assert claims[0]["n_considered"] == len(table)


def test_write_claims_jsonl_roundtrip(tmp_path, monkeypatch, real_df):
    import domains.basketball_nba.player_intel_shooting_claims as mod
    out = tmp_path / "claims.jsonl"
    monkeypatch.setattr(mod, "CLAIMS_PATH", out)
    claims = build_claims(real_df, "season_2024-25", top_n=3)
    write_claims(claims)
    lines = out.read_text(encoding="ascii").strip().split("\n")
    assert len(lines) == len(claims)
    for line in lines:
        row = json.loads(line)
        assert "claim_id" in row


def test_write_answers_md_contains_table(tmp_path, monkeypatch, real_df):
    import domains.basketball_nba.player_intel_shooting_claims as mod
    out = tmp_path / "answers.md"
    monkeypatch.setattr(mod, "ANSWERS_PATH", out)
    claims = build_claims(real_df, "season_2024-25", top_n=3)
    write_answers_md(claims)
    text = out.read_text(encoding="ascii")
    assert "| rank | player | value | n games |" in text


def test_claims_declare_executable_aggregate_and_window_spec(real_df):
    """Contract extension: every claim must carry aggregate + window_spec +
    value_precision, the derived exprs must cover every min_sample floor
    column, and the whole contract must be EXECUTABLE by the independent
    validator grammar (no import of this producer module on that side --
    importing it here in a test is fine, the lanes stay separate)."""
    from scripts.platformkit.intel_validation.safe_formula import evaluate_group_formula

    for window, expected_kind in (("last_20", "last_n_games"), ("season_2024-25", "season")):
        for c in build_claims(real_df, window, top_n=3):
            crit = c["criteria"]
            agg = crit["aggregate"]
            assert agg["group_by"] == "player_id"
            assert set(crit["min_sample"]).issubset(agg["derived"].keys())
            assert crit["window_spec"]["kind"] == expected_kind
            assert crit["value_precision"] == 4

    # Executability: recompute the season ts_pct rank-1 via the grammar alone.
    claims = build_claims(real_df, "season_2024-25", top_n=1)
    ts = [c for c in claims if c["criteria"]["metric"] == "ts_pct"][0]
    crit = ts["criteria"]
    assert crit["window_spec"] == {"kind": "season", "season": "2024-25",
                                   "season_col": "season", "n": None, "order_by": None}
    rows = real_df[real_df[crit["window_spec"]["season_col"]] == crit["window_spec"]["season"]]
    values = evaluate_group_formula(crit["formula"], rows, crit["aggregate"]["group_by"])
    floor_col = evaluate_group_formula(crit["aggregate"]["derived"]["fga_pg"], rows, "player_id")
    survivors = values[floor_col >= crit["min_sample"]["fga_pg"]].sort_values(ascending=False)
    top = ts["ranking"][0]
    assert int(survivors.index[0]) == top["player_id"]
    assert round(float(survivors.iloc[0]), crit["value_precision"]) == top["value"]


def test_formula_is_independently_recomputable(real_df):
    """The validator contract: formula + source_files must let an independent
    process recompute the top value without importing our module."""
    claims = build_claims(real_df, "season_2024-25", top_n=1)
    ts_claim = [c for c in claims if c["criteria"]["metric"] == "ts_pct"][0]
    top = ts_claim["ranking"][0]

    df = pd.read_parquet(ts_claim["source_files"][0])
    df = df[df["season"] == "2024-25"]
    row = df[df["player_id"] == top["player_id"]]
    pts, fga, fta = row["pts"].sum(), row["fga"].sum(), row["fta"].sum()
    recomputed = pts / (2 * (fga + 0.44 * fta))
    assert recomputed == pytest.approx(top["value"], abs=1e-3)

from pathlib import Path

from scripts.platformkit.ingame.s247_nba_sim_engine_v2 import (
    MIN_QUALIFYING_GAMES,
    measure_rates_limit,
    snapshot_date,
)


ROOT = Path(__file__).resolve().parents[3]
ARCHIVE = ROOT / "data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_all.csv"
PLAYER_RATES = ROOT / "data/cache/team_system/player_rates.parquet"
TEAM_RATES = ROOT / "data/cache/team_system/team_rates.json"


def test_s247_rates_snapshots_close_scoring_at_the_limit():
    result = measure_rates_limit(ARCHIVE, PLAYER_RATES, TEAM_RATES)

    assert snapshot_date(PLAYER_RATES).isoformat() == "2026-06-07"
    assert snapshot_date(TEAM_RATES).isoformat() == "2026-06-07"
    assert len(result.qualifying_cluster_ids) == 0
    assert len(result.excluded_cluster_ids) == 661
    assert result.verdict == "CLOSED_AT_LIMIT"
    assert len(result.qualifying_cluster_ids) < MIN_QUALIFYING_GAMES

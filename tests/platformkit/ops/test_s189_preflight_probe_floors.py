"""S189 construct checks for explicit MLB preflight existence floors."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from scripts.platformkit.ops import pod_bootstrap_check as pbc


_NAMES = (
    "parquet_mlb_games",
    "mlb_predictor_init",
    "produce_mlb_dry",
    "espn_live_state_mlb",
    "factory_sources",
    "boot_packages",
    "supervisor_lock_env",
)


def _redirected_body(path: Path, body: str) -> str:
    """Run an unmodified probe body after redirecting its corpus lookup in-child."""
    return (
        "from pathlib import Path\n"
        "import domains.mlb.predictor as predictor\n"
        "predictor._corpus_path = lambda repo_root: Path(%r)\n" % str(path)
    ) + body


def _run_with_corpus(path: Path, name: str) -> tuple[bool, str]:
    return pbc.run_probe(
        _redirected_body(path, pbc._FUNCTIONAL_PROBES[name]), sys.executable)


def test_s189_degraded_inputs_fail_and_census_is_exhaustive(tmp_path: Path) -> None:
    """Empty, malformed, and unavailable MLB inputs cannot report success."""
    schema_empty = tmp_path / "schema_empty.parquet"
    one_column_empty = tmp_path / "one_column_empty.parquet"
    absent = tmp_path / "absent.parquet"
    pd.DataFrame({
        "event_id": pd.Series(dtype="object"),
        "date": pd.Series(dtype="datetime64[ns]"),
        "season": pd.Series(dtype="int64"),
        "home_team": pd.Series(dtype="object"),
        "away_team": pd.Series(dtype="object"),
        "home_runs": pd.Series(dtype="int64"),
        "away_runs": pd.Series(dtype="int64"),
        "target_home_win": pd.Series(dtype="int8"),
        "game_seq": pd.Series(dtype="int8"),
        "home_league": pd.Series(dtype="object"),
    }).to_parquet(schema_empty)
    pd.DataFrame({"placeholder": pd.Series(dtype="int64")}).to_parquet(
        one_column_empty)

    expected_causes = {
        "parquet_mlb_games": ("AssertionError", "AssertionError", "FileNotFoundError"),
        "mlb_predictor_init": ("IndexError", "KeyError", "FileNotFoundError"),
    }
    for name, causes in expected_causes.items():
        for planted, expected in zip((schema_empty, one_column_empty, absent), causes):
            ok, cause = _run_with_corpus(planted, name)
            assert ok is False, (name, planted.name, cause)
            assert expected in cause, (name, planted.name, cause)

    unavailable_body = (
        "import predict_service.produce as produce\n"
        "produce._try_warm_predictor = lambda sport: 'forced unavailable'\n"
        + pbc._FUNCTIONAL_PROBES["produce_mlb_dry"]
    )
    ok, cause = pbc.run_probe(unavailable_body, sys.executable)
    assert ok is False, cause
    assert "AssertionError" in cause, cause

    assert tuple(pbc._FUNCTIONAL_PROBES) == _NAMES
    assert pbc._PROBE_TIMEOUT_S == 60.0
    assert "assert len(df) > 0" in pbc._FUNCTIONAL_PROBES["parquet_mlb_games"]
    assert "assert p.n_games > 0 and len(p.teams) > 0" in pbc._FUNCTIONAL_PROBES[
        "mlb_predictor_init"]
    assert "assert e.status == 'ok' and len(e.predictions) > 0" in (
        pbc._FUNCTIONAL_PROBES["produce_mlb_dry"])
    assert "stays fail-open BY DESIGN" in pbc._FUNCTIONAL_PROBES[
        "espn_live_state_mlb"] or "stays fail-open BY DESIGN" in Path(
            pbc.__file__).read_text(encoding="utf-8")

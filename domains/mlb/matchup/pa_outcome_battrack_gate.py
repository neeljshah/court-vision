"""domains.mlb.matchup.pa_outcome_battrack_gate -- does trailing (strictly-
prior as-of) Statcast bat-tracking (avg_bat_speed, swing_length) ADD to the
pa_outcome PROFILE_FEATURES baseline for PA-outcome bucket prediction?

Reuses the existing pa_outcome gate harness verbatim: PROFILE_FEATURES /
build_features / load_pa_dataset from pa_outcome_model.py,
_fit_calibrated_histgb from pa_outcome_v2.py. The only new piece is the
as-of join from domains.mlb.asof_bat_tracking.

PRE-STATED BAR (declared before running, not tuned to the result):
MIN_USABLE_N = 500 -- PA rows with a real, leak-free (strictly-prior)
bat-tracking snapshot for their batter. Below this floor: UNDERPOWERED,
no model fit (a HistGB fit on a handful of rows is not evidence).

CHEAP STRUCTURAL PRE-CHECK: before doing any profile/feature build, compare
the earliest captured snapshot as_of date against the corpus's newest PA
game_date. If the corpus never reaches past the earliest snapshot, n_usable
is PROVABLY 0 for every row -- short-circuit to NOT_TESTABLE without paying
for the full build (pa_outcome_v2's profile pipeline is not free).

KNOWN CURRENT STATE (checked this session, matches the independent finding
in docs/research/bat_tracking_asof_2026-07-11.md /
bat_tracking_gate_rerun_2026-07-11.md): the consolidated snapshot file
carries exactly ONE as_of date (2026-07-09, 592 rows). The newest PA on
disk anywhere (savant_full__2026.parquet) is 2026-07-08 -- strictly BEFORE
that snapshot, and the default SEASONS=(2022, 2023) gate corpus is far
earlier still. n_usable is therefore exactly 0 today: NOT_TESTABLE, not
merely underpowered -- stated plainly. This module self-corrects: once the
daily puller accrues a second as_of date, PAs on/after that second date
become joinable and n_usable rises on its own, no code change needed.

Descriptive/research gate only. NETWORK: zero. NO MARKET/$ EDGE CLAIMED.
CLI: python -m domains.mlb.matchup.pa_outcome_battrack_gate
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from domains.mlb.asof_bat_tracking import TRAILING_COLS, join_asof_trailing, load_snapshots
from domains.mlb.matchup.pa_outcome_model import _STATCAST, build_features, load_pa_dataset
from domains.mlb.matchup.pa_outcome_v2 import PROFILE_FEATURES, _fit_calibrated_histgb, verdict_rule
from domains.mlb.matchup.pitch_mix_profiles import SEASONS, build_batter_profile, build_pitcher_profile, load_pitch_rows

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPORT_OUT = _REPO_ROOT / "data" / "domains" / "mlb" / "matchup" / "pa_outcome_battrack_gate_report.json"

MIN_USABLE_N = 500
CANDIDATE_FEATURES = PROFILE_FEATURES + list(TRAILING_COLS)


def _corpus_max_game_date(seasons: tuple) -> pd.Timestamp:
    maxes = [pd.to_datetime(pd.read_parquet(_STATCAST[s], columns=["game_date"])["game_date"]).max()
             for s in seasons]
    return max(maxes)


def build_frame(seasons: tuple = SEASONS) -> pd.DataFrame:
    """PROFILE_FEATURES frame (walk-forward, train-season-only profiles --
    see pa_outcome_model/pa_outcome_v2 docstrings) with TRAILING_COLS
    attached via the strictly-prior as-of join."""
    pa = load_pa_dataset(seasons)
    pitch_rows = load_pitch_rows(seasons=seasons)
    pitcher_profile = build_pitcher_profile(pitch_rows)
    batter_profile = build_batter_profile(pitch_rows)
    train_season = min(seasons)
    pitcher_train = pitcher_profile[pitcher_profile["season"] == train_season]
    batter_train = batter_profile[batter_profile["season"] == train_season]
    feats = build_features(pa, pitcher_train, batter_train).reset_index(drop=True)

    trailing = join_asof_trailing(feats, load_snapshots(), pa_id_col="batter", pa_date_col="game_date")
    return pd.concat([feats, trailing], axis=1)


def _gate(feats: pd.DataFrame, min_usable_n: int, seasons: tuple) -> dict:
    usable = feats.dropna(subset=list(TRAILING_COLS))
    n_usable = int(len(usable))
    if n_usable < min_usable_n:
        return {
            "component": "pa_outcome_battrack_gate", "n_usable": n_usable, "min_usable_n": min_usable_n,
            "verdict": "NOT_TESTABLE" if n_usable == 0 else "UNDERPOWERED",
            "note": f"n_usable={n_usable} below pre-stated floor {min_usable_n}",
            "descriptive_only": True, "edge_claimed": False,
        }
    train_season, test_season = min(seasons), max(seasons)
    train, test = usable[usable["season"] == train_season], usable[usable["season"] == test_season]
    if len(train) == 0 or len(test) == 0:
        return {
            "component": "pa_outcome_battrack_gate", "n_usable": n_usable,
            "verdict": "NOT_TESTABLE",
            "note": "usable rows do not span both a train and a test season",
            "descriptive_only": True, "edge_claimed": False,
        }
    baseline = _fit_calibrated_histgb(train, test, PROFILE_FEATURES)
    candidate = _fit_calibrated_histgb(train, test, CANDIDATE_FEATURES)
    verdict = ("ADDS_SIGNAL" if verdict_rule(
        baseline["log_loss"], baseline["log_loss"], candidate["log_loss"],
        baseline["brier"]["IN_PLAY_OUT"], candidate["brier"]["IN_PLAY_OUT"],
    ) == "SHIP_PROVISIONAL" else "NULL")
    return {
        "component": "pa_outcome_battrack_gate", "n_usable": n_usable,
        "n_train": int(len(train)), "n_test": int(len(test)),
        "baseline_log_loss": baseline["log_loss"], "candidate_log_loss": candidate["log_loss"],
        "verdict": verdict, "descriptive_only": True, "edge_claimed": False,
    }


def run(seasons: tuple = SEASONS, min_usable_n: int = MIN_USABLE_N) -> dict:
    snapshots = load_snapshots()
    report_base = {
        "component": "pa_outcome_battrack_gate", "as_of": datetime.now(timezone.utc).isoformat(),
        "n_snapshot_dates": int(snapshots["as_of"].nunique()),
        "snapshot_date_range": [str(snapshots["as_of"].min()), str(snapshots["as_of"].max())],
    }
    corpus_max_date = _corpus_max_game_date(seasons)
    if corpus_max_date <= snapshots["as_of"].min():
        report_base.update({
            "corpus_max_game_date": str(corpus_max_date), "n_usable": 0, "min_usable_n": min_usable_n,
            "verdict": "NOT_TESTABLE",
            "note": ("structural: newest PA in the chosen seasons corpus is not strictly after "
                      "any captured bat-tracking as_of date -- zero rows can have a leak-free "
                      "prior snapshot; skipped the full profile build (cheap pre-check)"),
            "descriptive_only": True, "edge_claimed": False,
        })
        return report_base
    feats = build_frame(seasons)
    report_base.update(_gate(feats, min_usable_n, seasons))
    return report_base


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="PA-outcome gate for trailing bat-tracking as-of features")
    parser.parse_args(argv)

    report = run()
    _REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_OUT, "w", encoding="ascii", errors="strict") as f:
        json.dump(report, f, indent=2)
    print(f"n_usable={report.get('n_usable')} verdict={report['verdict']}")
    print(f"  note: {report.get('note', '')}")
    print(f"wrote -> {_REPORT_OUT}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

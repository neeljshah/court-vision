"""S82 runner: the in-game screen over the real MLB Kalshi tick store.

Kept out of `ingame_screen` only to hold that module under the 300-LOC rail; it adds no
logic. No ledger row, no prereg seal, no charge. Calibration language only. ASCII only.
Run: python -m scripts.platformkit.foundry.run_ingame_screen
"""
from __future__ import annotations

from scripts.platformkit.foundry.ingame_screen import (BAR, ROOT, assert_tick_asof,
                                                       build_features, causal_source, run)


def main() -> int:
    """Run the screen on the real MLB Kalshi tick store. No ledger, no seal, no charge."""
    from scripts.platformkit import hedge_trial_arms as arms
    from scripts.platformkit.eval_gate.stacker import _first_dates, e4_gd_series
    from scripts.platformkit.ingame_replay_scoreboard import discover_store

    ticks, feats = arms.load_corpus(discover_store(ROOT / "data" / "cache"), "mlb")
    src = causal_source(ticks)
    print("tick-time as-of guard: probes %s" % assert_tick_asof(src, build_features))
    out = ROOT / "data" / "cache" / "eval_gate"
    report = run(ticks, e4_gd_series(ticks, feats), build_features(src), _first_dates(ticks),
                 out_json=out / "s82_ingame_screen_2026-09-03.json",
                 out_csv=out / "s82_ingame_screen_series_2026-09-03.csv")
    corpus, screened = report["corpus"], [r for r in report["results"] if r.get("status") == "SCREENED"]
    print("SCREEN side: %d ticks / %d games of %d / %d scored | partition %s"
          % (corpus["n_screen_ticks"], corpus["n_screen_games"], corpus["n_scored_ticks"],
             corpus["n_scored_games"], report["partition"]["basis"]))
    for r in report["results"]:
        if r.get("status") != "SCREENED":
            print("  %-24s %s" % (r["feature"], r.get("status")))
            continue
        print("  %-24s n=%6d g=%3d e4 %.6f null %.6f cand %.6f mkt %.6f impr_null %+.6f "
              "ci95 [%+.6f %+.6f] p %.3g%s"
              % (r["feature"], r["n_ticks"], r["n_games"], r["brier_e4"], r["brier_null_recal"],
                 r["brier_candidate"], r["brier_market"], r["improvement_vs_null"],
                 r["dm_ci95"][0], r["dm_ci95"][1], r["dm_p_raw"],
                 "  CLEARS BAR" if r["clears_bar"] else ""))
    print("clearing the +%.3f bar: %d of %d" % (BAR, report["n_clearing_bar"], len(screened)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

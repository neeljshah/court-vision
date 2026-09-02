"""Runner for the in-game screen tier: the MLB corpus (S82) and the NBA corpus (S102).

Kept out of `ingame_screen` / `ingame_screen_nba` only to hold those modules under the
300-LOC rail; it adds no scoring logic. No ledger row, no prereg seal, no charge.
Calibration language only. ASCII only.

  python -m scripts.platformkit.foundry.run_ingame_screen                       # MLB (S82)
  python -m scripts.platformkit.foundry.run_ingame_screen --sport nba --grammar nba
  python -m scripts.platformkit.foundry.run_ingame_screen --sport nba --report  # BH + top 10
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from scripts.platformkit.foundry.ingame_screen import (BAR, ROOT, assert_tick_asof,
                                                       build_features, causal_source, run)


def run_mlb() -> int:
    """The S82 screen on the real MLB Kalshi tick store. No ledger, no seal, no charge."""
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


def run_nba(db: Path, limit: int, probes: int) -> int:
    """The S102 sweep: 576 frozen derived-state hypotheses on the S86 SCREEN side."""
    from scripts.platformkit.foundry import ingame_grammar_nba as grammar
    from scripts.platformkit.foundry import ingame_screen_nba as nba

    rows = nba.load_screen()
    print("corpus: %d ticks / %d games | folds %s"
          % (len(rows), rows["game"].nunique(),
             json.dumps(rows.groupby("game_date").size().to_dict())), flush=True)
    src = nba.causal_source(rows)
    checked = assert_tick_asof(src, grammar.build_grid, probes=probes) if probes else []
    print("tick-time as-of guard: probes %s" % checked, flush=True)
    grid = grammar.build_grid(src)
    hypotheses = grammar.enumerate_hypotheses()
    print("frozen grammar %s: %d hypotheses over %d grid columns"
          % (grammar.FAMILY, len(hypotheses), grid.shape[1]), flush=True)
    db.parent.mkdir(parents=True, exist_ok=True)
    nba.write_meta(db, rows, hypotheses, checked)
    stats = nba.sweep(rows, grid, hypotheses, db, limit=limit)
    nba.write_meta(db, rows, hypotheses, checked,
                   extra={"screens_per_hour": stats["screens_per_hour"],
                          "seconds_last_run": stats["seconds"]})
    print("scored %d hypotheses in %.1f s = %.1f screens/hour"
          % (stats["n_scored_this_run"], stats["seconds"], stats["screens_per_hour"]))
    return 0


def report_nba(db: Path, top: int) -> int:
    """Within-family BH FDR over the screen p-values, then the best `top` rows."""
    import pandas as pd

    from scripts.platformkit.combo.fwer_budget import bh_within_family
    from scripts.platformkit.eval_gate.family_bars import load_families
    from scripts.platformkit.foundry import ingame_grammar_nba as grammar

    connection = sqlite3.connect(str(db))
    frame = pd.read_sql_query("SELECT * FROM screen", connection)
    meta = dict(connection.execute("SELECT key, value FROM meta"))
    connection.close()
    scored = frame[frame["status"] == "SCREENED"].reset_index(drop=True)
    spec = load_families()
    family = spec.get(grammar.FAMILY)
    result = bh_within_family(scored["dm_p_raw"].tolist(), spec.q_within_family)
    scored["bh_adjusted_p"] = list(result.adjusted)
    scored["bh_reject"] = list(result.rejected)
    surviving = scored[scored["bh_reject"] & (scored["improvement_vs_null"] > 0.0)]
    best = scored.sort_values("improvement_vs_null", ascending=False).head(top)
    print("family %s @ %s (%s) | frozen members %d, hypotheses %d | scored %d of %d"
          % (family.name, spec.spec_version, spec.prereg_sha256[:12], family.features,
             family.hypotheses, len(scored), len(frame)))
    print("BH q=%.3f within family: %d discoveries; %d of them improve on the null"
          % (spec.q_within_family, result.n_discoveries, len(surviving)))
    print("bar +%.3f (frozen, never moved): %d of %d clear it"
          % (BAR, int(scored["clears_bar"].sum()), len(scored)))
    print("%-30s %8s %7s %10s %10s %10s %12s %24s %9s %9s"
          % ("hypothesis", "n", "games", "n_eff", "mkt/null", "cand", "impr_vs_null",
             "DM CI95", "p_raw", "bh_adj_p"))
    for _, row in best.iterrows():
        print("%-30s %8d %7d %10.1f %10.6f %10.6f %+12.6f  [%+.6f %+.6f] %9.4g %9.4g"
              % (row["label"], row["n_ticks"], row["n_games"], row["n_eff"],
                 row["brier_null"], row["brier_candidate"], row["improvement_vs_null"],
                 row["ci_lo"], row["ci_hi"], row["dm_p_raw"], row["bh_adjusted_p"]))
    out = db.with_name(db.stem + "_report.json")
    out.write_text(json.dumps(
        {"family": family.name, "families_spec_version": spec.spec_version,
         "families_spec_sha": spec.prereg_sha256, "q_within_family": spec.q_within_family,
         "bar": BAR, "n_hypotheses": len(frame), "n_scored": len(scored),
         "n_clearing_bar": int(scored["clears_bar"].sum()),
         "bh_discoveries": int(result.n_discoveries),
         "bh_discoveries_improving": int(len(surviving)),
         "bh_threshold": float(result.threshold),
         "best": json.loads(best.to_json(orient="records")), "meta": meta},
        indent=1, sort_keys=True), "ascii")
    print("report: %s" % out)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="in-game screen tier (S82 / S102)")
    parser.add_argument("--sport", default="mlb", choices=("mlb", "nba"))
    parser.add_argument("--grammar", default="", choices=("", "nba"))
    parser.add_argument("--sqlite", default="")
    parser.add_argument("--limit", type=int, default=0, help="stop after N new screens")
    parser.add_argument("--probes", type=int, default=8, help="tick-time as-of probe rows")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args(argv)
    if args.sport == "mlb":
        return run_mlb()
    db = Path(args.sqlite) if args.sqlite else (
        ROOT / "data" / "cache" / "eval_gate" / "s102_nba_sweep.sqlite")
    return report_nba(db, args.top) if args.report else run_nba(db, args.limit, args.probes)


if __name__ == "__main__":
    raise SystemExit(main())

"""S148 -- re-quote every landed NBA tick headline on LIVE ticks only.

S146 measured it: 235,513 of the 465,249 rows of
``data/cache/inplay_odds/nba_checkpoints_full.parquet`` are POST-FINAL-BUZZER
price ticks matched to the game's last play state, with the final score already
known.  Both the in-play line and every model arm are trivially near-certain
there, so every pooled Brier / n / n_eff published by S86 S94 S96 S97 S98 S101
S102 S103 S114 S115 S116 counts them.

THE LIVE RULE (from the data -- the corpus carries no `final`/`status` column,
only ``period`` and ``game_clock_s``)::

    live  <=>  game_clock_s > 0  OR  period < 4
    dead  <=>  period >= 4  AND  game_clock_s == 0

A quarter-end buzzer in P1-P3 keeps its tick (the game is still live); a P4 or
OT tick at clock 0 does not.  The rule is applied to the S86 screen CSV, which
carries `period` and `game_clock_s` per tick, and the resulting
``(game_id, ts)`` verdict is joined onto every other NBA archive -- all of them
are strict subsets of the S86 key set (measured: 0 rows unmatched).

NO REFIT anywhere.  Each archived per-unit paired loss is read AS WRITTEN and
only the ROW SET changes; A2 first, so every published headline is reproduced
from its own archive before its live re-quote is read.  The informative mask is
the PUBLISHED one -- ``tick_informative.flag_ticks`` run on the full series --
intersected with live, so "live-informative" never re-derives held-ness from a
different row set.

    python -m scripts.platformkit.eval_gate.s148_live_requote
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence

import pandas as pd

from scripts.platformkit.eval_gate.archive_read import read_series
from scripts.platformkit.eval_gate.tick_informative import _quote, flag_ticks

_REPO = Path(__file__).resolve().parents[3]
_CACHE = _REPO / "data" / "cache" / "eval_gate"
_PARQUET = _REPO / "data" / "cache" / "inplay_odds" / "nba_checkpoints_full.parquet"
BAR = 0.004          # frozen; read here only as a label
_S86_CSV = "s86_nba_every_tick_2026-09-03.csv"


# --------------------------------------------------------------------------- #
# the rule
# --------------------------------------------------------------------------- #
def live_mask(frame: pd.DataFrame, period: str = "period",
              clock: str = "game_clock_s") -> pd.Series:
    """True where the tick is LIVE: game_clock_s > 0 OR period < 4.

    A missing clock cannot be confirmed dead, so it stays live -- the mask never
    silently deletes a tick it cannot classify.
    """
    p = pd.to_numeric(frame[period], errors="coerce")
    c = pd.to_numeric(frame[clock], errors="coerce")
    return ~((p >= 4) & (c == 0)).fillna(False)


def _epoch(values: pd.Series) -> pd.Series:
    """Epoch seconds from either an integer epoch column or an ISO/`YYYY-mm-dd HH:MM:SS` one."""
    if pd.api.types.is_numeric_dtype(values):
        return values.astype("int64")
    return pd.to_datetime(values, utc=True).astype("int64") // 10 ** 9


def live_index(cache: Path = _CACHE) -> pd.DataFrame:
    """(game_id, ts, is_live) for every NBA tick, from the S86 screen CSV."""
    frame = read_series(cache / _S86_CSV)[["game_id", "ts", "period", "game_clock_s"]]
    return pd.DataFrame({"_g": frame["game_id"].astype(str), "_t": _epoch(frame["ts"]),
                         "is_live": live_mask(frame).to_numpy()})


def attach_live(frame: pd.DataFrame, index: pd.DataFrame, game: pd.Series,
                ts: pd.Series) -> pd.DataFrame:
    """Add `is_live` to `frame` by joining `index` on (game, epoch ts)."""
    out = frame.copy()
    out["_g"], out["_t"] = game.astype(str).to_numpy(), _epoch(ts).to_numpy()
    merged = out.merge(index, on=["_g", "_t"], how="left")
    merged.index = out.index
    if merged["is_live"].isna().any():
        raise ValueError("%d rows absent from the S86 live index"
                         % int(merged["is_live"].isna().sum()))
    return merged.drop(columns=["_g", "_t"])


def verdict(quote: Dict[str, Any], bar: float = BAR) -> str:
    """The same deterministic reading applied to the old and the new row set."""
    lo, hi = quote["dm_ci95"]
    if lo > 0.0:
        return "AHEAD" if quote["mean_loss_differential"] >= bar else "POSITIVE-BELOW-BAR"
    return "NEGATIVE" if hi < 0.0 else "NULL"


# --------------------------------------------------------------------------- #
# one archive, three row sets
# --------------------------------------------------------------------------- #
def requote(spec: Dict[str, Any], index: pd.DataFrame,
            cache: Path = _CACHE) -> Dict[str, Any]:
    """Quote one archived differential on ALL, LIVE and LIVE-INFORMATIVE rows."""
    frame = spec["load"](cache) if "load" in spec else read_series(cache / spec["csv"])
    if spec.get("where") is not None:
        frame = frame[spec["where"](frame)].reset_index(drop=True)
    d_col = spec.get("d")
    if d_col is None:
        y = frame[spec["y"]].astype(float)
        frame = frame.assign(_d=(frame[spec["incumbent"]].astype(float) - y) ** 2
                             - (frame[spec["candidate"]].astype(float) - y) ** 2)
        d_col = "_d"
    keys = spec.get("game_key", lambda f: f[spec["game"]])(frame)
    frame = attach_live(frame, index, keys, frame[spec["ts"]])
    flagged, flags = flag_ticks(frame, game_col=spec["game"], ts_col=spec["ts"],
                                market_col=spec["market"], model_col=spec["model"])
    cluster = spec.get("cluster", spec["game"])
    live = flagged[flagged["is_live"]]
    row = {
        "note": spec["note"],
        "series": spec.get("csv", spec.get("source")),
        "n_excluded_dead": int((~flagged["is_live"]).sum()),
        "share_excluded": float((~flagged["is_live"]).mean()),
        "published_informative": int(flags["n_informative"]),
        "all": _quote(flagged, cluster, d_col),
        "live": _quote(live, cluster, d_col),
        "live_informative": _quote(live[live["is_informative"]], cluster, d_col),
    }
    for key in ("all", "live", "live_informative"):
        row[key]["verdict"] = verdict(row[key])
    row["verdict_changed"] = row["all"]["verdict"] != row["live"]["verdict"]
    row["verdict_changed_informative"] = row["all"]["verdict"] != row["live_informative"]["verdict"]
    if spec.get("ci") is not None:
        published = _dig(json.loads((cache / spec["json"]).read_text(encoding="utf-8")),
                         spec["ci"]) if spec.get("json") else spec["ci"]
        delta = max(abs(float(a) - float(b))
                    for a, b in zip(published, row["all"]["dm_ci95"]))
        row["a2"] = {"published_ci95": [float(v) for v in published],
                     "max_abs_delta": float(delta), "reproduced": bool(delta < 1e-9)}
    return row


def _dig(blob: Any, path: Any) -> Any:
    if callable(path):
        return path(blob)
    for key in path:
        blob = blob[key]
    return blob


# --------------------------------------------------------------------------- #
# the archive spec table (S137's shape, plus the live keys and the flag columns)
# --------------------------------------------------------------------------- #
def _s102(cache: Path) -> pd.DataFrame:
    return pd.read_parquet(cache / "s102_nba_sweep_top10_series.parquet")


_SPECS: Dict[str, Dict[str, Any]] = {
    "S86": {"csv": _S86_CSV, "game": "game_id", "ts": "ts", "market": "market", "model": "model",
            "d": "d", "json": "s86_nba_every_tick_2026-09-03.json", "ci": ("pooled", "dm_ci95"),
            "note": "pooled state-priced prior vs the in-play line"},
    "S94": {"csv": "s94_nba_early_shrinkage_2026-09-03.csv", "game": "game", "ts": "ts",
            "market": "market", "model": "model", "cluster": "cluster_id",
            "d": "d_candidate_vs_market", "json": "s94_nba_early_shrinkage_2026-09-03.json",
            "ci": ("overall", "dm", "candidate_vs_market", "ci95"),
            "note": "phase-conditioned shrinkage, OVERALL, vs the raw line"},
    "S94-target": {"csv": "s94_nba_early_shrinkage_2026-09-03.csv", "game": "game", "ts": "ts",
                   "market": "market", "model": "model", "cluster": "cluster_id",
                   "d": "d_candidate_vs_market",
                   "where": lambda f: f["cell"].isin(("P1|close_le5|rem_gt12",
                                                      "P2|close_le5|rem_gt12")),
                   "json": "s94_nba_early_shrinkage_2026-09-03.json",
                   "ci": ("target", "dm", "candidate_vs_market", "ci95"),
                   "note": "the S94 TARGET cell P1-P2 | close_le5 | rem_gt12"},
    "S96": {"csv": "s96_nba_overreaction_2026-09-03.csv", "game": "game", "ts": "ts",
            "market": "market", "model": "p_arm", "cluster": "cluster_id", "d": "d_arm_vs_market",
            "where": lambda f: (f["threshold"] == 3) & (f["k"] == 5),
            "json": "s96_nba_overreaction_2026-09-03.json",
            "ci": ("arms", "thr3_k5", "overall", "dm", "arm_vs_market", "ci95"),
            "note": "primary post-event drift arm thr3_k5 vs the raw line"},
    "S97": {"csv": "s97_nba_sensor_fusion_2026-09-03.csv", "game": "game", "ts": "ts",
            "market": "market", "model": "p_posterior", "cluster": "cluster_id",
            "d": "d_posterior_vs_market", "json": "s97_nba_sensor_fusion_2026-09-03.json",
            "ci": ("overall", "dm", "posterior_vs_market", "ci95"),
            "note": "two-sensor Kalman posterior vs the raw line"},
    "S98": {"csv": "s98_nba_better_prior_2026-09-03.csv", "game": "game", "ts": "ts",
            "market": "market", "model": "p_elo_sig", "cluster": "cluster_id",
            "d": "d_elo_sig_vs_market", "json": "s98_nba_better_prior_2026-09-03.json",
            "ci": ("overall", "dm_ci95", "elo_sig"),
            "note": "fitted per-cell sigma arm (elo_sig), pooled, vs the raw line"},
    "S103": {"csv": "s103_nba_sigma_2026-09-03.csv", "game": "game", "ts": "ts",
             "market": "market", "model": "p_wide", "cluster": "cluster_id",
             "d": "d_wide_vs_market", "json": "s103_nba_sigma_2026-09-03.json",
             "ci": ("overall", "dm_ci95", "wide"),
             "note": "sigma grid widened to [3, 60], pooled, vs the raw line"},
    "S114-k5": {"csv": "s114_ingame_ensemble_series.csv", "game": "game", "ts": "ts",
                "market": "market", "model": "p_k5", "incumbent": "market",
                "candidate": "p_k5", "y": "y", "json": "s114_ingame_ensemble.json",
                "ci": ("per_k", "k5", "vs_market", "ci95"),
                "note": "ladder arm k=5 vs the raw line (POST S126 re-run archive)"},
    "S115": {"csv": "s115_ingame_models_2026-09-03.csv", "game": "game", "ts": "ts",
             "market": "market", "model": "p_mlp", "cluster": "cluster_id",
             "d": "d_mlp_vs_market", "json": "s115_ingame_models_2026-09-03.json",
             "ci": ("headline_ci95",), "note": "best non-linear arm (mlp) vs the raw line"},
    "S116-nba": {"csv": "s116_pooled_ingame_2026-09-03.csv", "game": "cluster", "ts": "ts_utc",
                 "market": "p_line", "model": "p_partial", "cluster": "cluster",
                 "d": "d_partial_vs_line", "where": lambda f: f["sport"] == "nba",
                 "json": "s116_pooled_ingame_2026-09-03.json",
                 "ci": ("by_sport", "nba", "dm", "partial_vs_line", "ci95"),
                 "game_key": lambda f: f["cluster"].str.replace("^nba:", "", regex=True),
                 "note": "cross-sport partially pooled residual, NBA side, vs the raw line"},
}
# the S114 ladder's other three arms and the S115 other two arms, same archives
for _k in ("k1", "k3", "k10"):
    _SPECS["S114-%s" % _k] = dict(_SPECS["S114-k5"], model="p_" + _k, candidate="p_" + _k,
                                  ci=("per_k", _k, "vs_market", "ci95"),
                                  note="ladder arm %s vs the raw line" % _k)
for _a in ("hgb", "hgb_mono"):
    _SPECS["S115-%s" % _a] = dict(_SPECS["S115"], model="p_" + _a, d="d_%s_vs_market" % _a,
                                  ci=("arms", _a, "dm_vs_market", "ci95"),
                                  note="non-linear arm %s vs the raw line" % _a)

def s86_cells(index: pd.DataFrame, cache: Path = _CACHE) -> Dict[str, Any]:
    """The 27 published period x margin x rem cells, all rows vs live rows."""
    raw = read_series(cache / _S86_CSV)
    frame = attach_live(raw, index, raw["game_id"], raw["ts"])
    published = json.loads((cache / "s86_nba_every_tick_2026-09-03.json")
                           .read_text(encoding="utf-8"))["by_period_margin_rem"]
    out = []
    for cell in published:
        key = (cell["period_bucket"], cell["margin_bucket"], cell["rem_bucket"])
        sub = frame[(frame["period_bucket"] == key[0]) & (frame["margin_bucket"] == key[1])
                    & (frame["rem_bucket"] == key[2])]
        live = sub[sub["is_live"]]
        row: Dict[str, Any] = {"cell": "|".join(key), "n_all": int(len(sub)),
                               "n_live": int(len(live)),
                               "published_ci95": cell["dm_ci95"],
                               "published_improvement": cell["improvement_vs_market"]}
        row["all"] = _quote(sub, "game_id", "d") if sub["game_id"].nunique() >= 2 else None
        row["live"] = _quote(live, "game_id", "d") if live["game_id"].nunique() >= 2 else None
        for side in ("all", "live"):
            if row[side] is not None:
                row[side]["verdict"] = verdict(row[side])
        if cell["dm_ci95"] and row["all"]:
            row["a2_max_abs_delta"] = max(abs(float(a) - float(b)) for a, b
                                          in zip(cell["dm_ci95"], row["all"]["dm_ci95"]))
        row["verdict_changed"] = bool(row["all"] and row["live"]
                                      and row["all"]["verdict"] != row["live"]["verdict"])
        out.append(row)
    return {"n_cells": len(out), "cells": out,
            "n_verdicts_changed": sum(1 for r in out if r["verdict_changed"]),
            "n_cells_emptied_of_live": sum(1 for r in out if r["n_live"] == 0)}


def s101_coverage(index: pd.DataFrame, cache: Path = _CACHE) -> Dict[str, Any]:
    """S101 STATIC grouped coverage per phase at nominal 0.90, all rows vs live rows."""
    from scripts.platformkit.eval_gate.s101_aci_coverage import grouped_coverage
    ticks = pd.read_csv(cache / "s101_aci_coverage_2026-09-03_ticks.csv.gz")
    ticks = attach_live(ticks, index, ticks["game"], ticks["ts"])
    published = json.loads((cache / "s101_aci_coverage_2026-09-03.json")
                           .read_text(encoding="utf-8"))["results"]
    out: Dict[str, Any] = {}
    for arm in ("market", "model"):
        key = "%s|0.90" % arm
        sub = ticks[(ticks["arm"] == arm) & (ticks["nominal"] == 0.9)]
        per_phase = {}
        for phase in sorted(sub["phase"].unique()):
            block = sub[sub["phase"] == phase]
            live = block[block["is_live"]]
            def cov(f):
                return grouped_coverage(f["p"].to_numpy(float), f["y"].to_numpy(float),
                                        f["lo_static"].to_numpy(float),
                                        f["hi_static"].to_numpy(float), 0.9)
            pub = published[key]["static"].get(phase, {})
            per_phase[phase] = {"published_coverage": pub.get("coverage"),
                                "all": cov(block), "live": cov(live) if len(live) else None,
                                "n_all": int(len(block)), "n_live": int(len(live))}
            got = per_phase[phase]["all"]["coverage"]
            if pub.get("coverage") is not None and got is not None:
                per_phase[phase]["a2_max_abs_delta"] = abs(float(pub["coverage"]) - float(got))
        out[key] = per_phase
    return out


def s102_top10(index: pd.DataFrame, cache: Path = _CACHE) -> Dict[str, Any]:
    """The 10 archived sweep leaders, all rows vs live rows, against the sqlite headline."""
    con = sqlite3.connect("file:%s?mode=ro"
                          % (cache / "s102_nba_sweep.sqlite").as_posix(), uri=True)
    try:
        top = pd.read_sql("select label, improvement_vs_null, ci_lo, ci_hi, n_ticks, n_eff"
                          " from screen where status='SCREENED'"
                          " order by improvement_vs_null desc limit 10", con)
    finally:
        con.close()
    series = _s102(cache)
    rows = []
    for _, head in top.iterrows():
        spec = {"csv": "s102_nba_sweep_top10_series.parquet",
                "load": lambda c, lab=head["label"]: series[series["hypothesis"] == lab]
                .reset_index(drop=True).copy(),
                "game": "game", "ts": "timestamp", "market": "market", "model": "p_candidate",
                "d": "d", "ci": (float(head["ci_lo"]), float(head["ci_hi"])),
                "note": "sweep hypothesis %s vs the recal null" % head["label"]}
        row = requote(spec, index, cache=cache)
        row["label"] = str(head["label"])
        row["published_improvement"] = float(head["improvement_vs_null"])
        row["published_n_eff"] = float(head["n_eff"])
        rows.append(row)
    return {"n_hypotheses": len(rows), "rows": rows,
            "n_verdicts_changed": sum(1 for r in rows if r["verdict_changed"]),
            "n_a2_reproduced": sum(1 for r in rows if r["a2"]["reproduced"]),
            "a2_note": "each published CI comes from the landed sqlite `screen` table"}


# --------------------------------------------------------------------------- #
def exclusion_counts(cache: Path = _CACHE) -> Dict[str, Any]:
    """The rule's exclusion count on the S86 screen CSV and on the source parquet."""
    s86 = read_series(cache / _S86_CSV)[["game_id", "period", "game_clock_s"]]
    dead = ~live_mask(s86)
    out = {"rule": "live <=> game_clock_s > 0 OR period < 4",
           "corpus_has_final_status_column": False,
           "s86_screen_csv": {"n": int(len(s86)), "n_dead": int(dead.sum()),
                              "share_dead": float(dead.mean()),
                              "n_games": int(s86["game_id"].nunique()),
                              "n_games_with_zero_live": int(
                                  (s86[~dead].groupby("game_id").size()
                                   .reindex(s86["game_id"].unique()).fillna(0) == 0).sum())}}
    if _PARQUET.exists():
        par = pd.read_parquet(_PARQUET, columns=["game_id", "period", "game_clock_s"])
        pdead = ~live_mask(par)
        out["checkpoint_parquet"] = {
            "n": int(len(par)), "n_dead": int(pdead.sum()), "share_dead": float(pdead.mean()),
            "s146_post_final_count": 235513,
            "delta_vs_s146": int(pdead.sum()) - 235513,
            "note": "S146 counted rows that are BOTH matched to the last play state AND over the "
                    "300 s rail; this state rule also catches post-buzzer ticks inside 300 s of "
                    "the final play, so it is the larger of the two."}
    return out


def build(cache: Path = _CACHE) -> Dict[str, Any]:
    index = live_index(cache)
    rows = {name: requote(spec, index, cache=cache) for name, spec in _SPECS.items()}
    a2 = {k: v["a2"] for k, v in rows.items() if "a2" in v}
    cells, coverage, sweep = (s86_cells(index, cache=cache), s101_coverage(index, cache=cache),
                              s102_top10(index, cache=cache))
    cover_deltas = [v["a2_max_abs_delta"] for arm in coverage.values() for v in arm.values()
                    if "a2_max_abs_delta" in v]
    return {
        "row": "S148",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tier": "RE-QUOTE (no refit, no charge, no prereg seal, no K read, no bar moved)",
        "improvement_bar": BAR,
        "live_rule": exclusion_counts(cache),
        "informative_mask": "tick_informative.flag_ticks on the FULL series (published "
                            "semantics), intersected with live",
        "a2_reproduction": a2,
        "a2_failures": sorted(k for k, v in a2.items() if not v["reproduced"]),
        "rows": rows,
        "s86_cells": cells,
        "s101_grouped_coverage": coverage,
        "s102_top10": sweep,
        "a2_summary": {
            "headlines": {"n": len(a2), "n_reproduced": sum(1 for v in a2.values()
                                                            if v["reproduced"]), "tol": 1e-9},
            "s86_cells": {"n": sum(1 for r in cells["cells"] if "a2_max_abs_delta" in r),
                          "max_abs_delta": max([r["a2_max_abs_delta"] for r in cells["cells"]
                                                if "a2_max_abs_delta" in r] or [0.0])},
            "s101_phase_coverage": {"n": len(cover_deltas),
                                    "max_abs_delta": max(cover_deltas or [0.0])},
            "s102_top10": {"n": len(sweep["rows"]), "n_reproduced": sweep["n_a2_reproduced"],
                           "max_abs_delta": max(r["a2"]["max_abs_delta"]
                                                for r in sweep["rows"])}},
        "verdicts_changed": sum(1 for v in rows.values() if v["verdict_changed"]),
        "verdicts_changed_total": (sum(1 for v in rows.values() if v["verdict_changed"])
                                   + cells["n_verdicts_changed"] + sweep["n_verdicts_changed"]),
        "n_ahead_all": sum(1 for v in rows.values() if v["all"]["verdict"] == "AHEAD"),
        "n_ahead_live": sum(1 for v in rows.values() if v["live"]["verdict"] == "AHEAD"),
        "honest_note": "Brier and Brier differences only. No dollar, ROI, profit or edge claim. "
                       "A null is a success; every reading here is SINGLE-WINDOW.",
        "edge_claimed": False,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="S148: re-quote NBA tick headlines on live ticks")
    parser.add_argument("--out", default=str(_CACHE / "s148_live_requote_2026-09-03.json"))
    args = parser.parse_args(argv)
    blob = build()
    Path(args.out).write_text(json.dumps(blob, indent=1, sort_keys=True), encoding="utf-8")
    live = blob["live_rule"]["s86_screen_csv"]
    print("wrote %s" % args.out)
    print("rule: %s | S86 CSV dead %d of %d (%.4f)" % (blob["live_rule"]["rule"],
          live["n_dead"], live["n"], live["share_dead"]))
    print("a2 rows %d | failures %s | verdicts changed %d of %d"
          % (len(blob["a2_reproduction"]), blob["a2_failures"] or "none",
             blob["verdicts_changed"], len(blob["rows"])))
    for name, row in sorted(blob["rows"].items()):
        print("  %-11s n %7d -> %7d | n_eff %9.2f -> %9.2f | %+.6f -> %+.6f"
              " | [%+.6f,%+.6f] -> [%+.6f,%+.6f] | %s -> %s%s"
              % (name, row["all"]["n"], row["live"]["n"], row["all"]["n_eff"],
                 row["live"]["n_eff"], row["all"]["mean_loss_differential"],
                 row["live"]["mean_loss_differential"], row["all"]["dm_ci95"][0],
                 row["all"]["dm_ci95"][1], row["live"]["dm_ci95"][0], row["live"]["dm_ci95"][1],
                 row["all"]["verdict"], row["live"]["verdict"],
                 "  CHANGED" if row["verdict_changed"] else ""))
    return 1 if blob["a2_failures"] else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

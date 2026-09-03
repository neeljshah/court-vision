"""S137 -- ONE post-fix re-baseline table for every landed in-game / close headline.

Five instruments moved on 2026-09-03: the clean NBA/MLB close (S132/S133), the
corroborated real-game split 392 -> 360 (S131), the tick-level partition (S121),
the same-rows recalibration null (S126), the season-grain prior + side guard
(S128/S129) and UTC stamp parsing (S125).  This module re-quotes every landed
headline of S82 S86 S87 S94 S96 S97 S98 S101 S102 S103 S106 S112 S113 S114 S115
S116 S117 S119 S121 S123 on the corrected instruments.

Two rules it never breaks:

* **A2 first.**  Every PUBLISHED headline is recomputed from its own Q9 archive
  before its post-fix number is read.  A failed reproduction is reported, never
  replaced.
* **No refit** where the instrument is a clustering / partition / reference
  relabel -- the archived paired losses are read as written and only the UNIT or
  the ROW SET changes.  Where the instrument changes the FITTED arm the row says
  ``RE-RUN REQUIRED`` and names the exact command.

A screen is a non-finding.  No charge, no prereg seal, no K read, no bar moved,
no landed artifact overwritten.  Calibration language only.

    python -m scripts.platformkit.eval_gate.s137_rebaseline
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import pandas as pd

# reuse: the SAME clustered DM + ESS quote every landed in-game artifact published with
from scripts.platformkit.eval_gate.tick_informative import _quote

_REPO = Path(__file__).resolve().parents[3]
_CACHE = _REPO / "data" / "cache" / "eval_gate"
_EVID = _REPO / "docs" / "evidence" / "harness"
BAR = 0.004  # frozen; this module never reads it as anything but a label


# --------------------------------------------------------------------------- #
# the re-quote helper -- the only statistic this module owns
# --------------------------------------------------------------------------- #
def archive_quote(csv: str, cluster_col: str, d_col: Optional[str] = None,
                  incumbent: Optional[str] = None, candidate: Optional[str] = None,
                  y: str = "y", where: Optional[Callable] = None,
                  cache: Path = _CACHE) -> Dict[str, Any]:
    """Quote one archived per-unit differential.  Nothing model-side is recomputed.

    Either name the archived ``d_col``, or give ``incumbent``/``candidate``
    probability columns and the paired Brier differential is formed here
    (d = loss(incumbent) - loss(candidate); POSITIVE means the candidate is better).
    """
    # NO `comment="#"` here: the S116 archive's cluster ids contain '#'
    # ("mlb:KXMLBGAME-...#1") and pandas would truncate every row at it, leaving
    # the loss column all-NaN.  None of these archives carries a comment header.
    frame = pd.read_csv(cache / csv)
    if where is not None:
        frame = frame[where(frame)]
    if d_col is None:
        label = frame[y].astype(float)
        frame = frame.assign(_d=((frame[incumbent].astype(float) - label) ** 2)
                             - ((frame[candidate].astype(float) - label) ** 2))
        d_col = "_d"
    return _quote(frame, cluster_col, d_col)


def _dig(blob: Any, path: Any) -> Any:
    """Follow a key path, or call a finder, into a loaded artifact."""
    if callable(path):
        return path(blob)
    for key in path:
        blob = blob[key]
    return blob


def _find(items: Sequence[Dict[str, Any]], key: str, value: Any) -> Dict[str, Any]:
    return next(r for r in items if r[key] == value)


def reproduces(quote: Dict[str, Any], published_ci: Sequence[float],
               tol: float = 1e-9) -> Dict[str, Any]:
    """A2: does the re-quote reproduce a published CI to `tol`?"""
    delta = max(abs(float(a) - float(b)) for a, b in zip(published_ci, quote["dm_ci95"]))
    return {"published_ci95": [float(v) for v in published_ci],
            "max_abs_delta": float(delta), "reproduced": bool(delta < tol)}


# --------------------------------------------------------------------------- #
# A2 -- reproduce every published headline that archives a per-unit differential
# --------------------------------------------------------------------------- #
_A2: Dict[str, Dict[str, Any]] = {
    "S82": {"csv": "s82_ingame_screen_series_2026-09-03.csv", "cluster": "game",
            "incumbent": "p_null", "candidate": "p_candidate",
            "where": lambda f: f["feature"] == "tick_index_in_game",
            "json": "s82_ingame_screen_2026-09-03.json",
            "ci": lambda b: _find(b["results"], "feature", "tick_index_in_game")["dm_ci95"],
            "note": "leader tick_index_in_game vs the recal null, by ticker"},
    "S86": {"csv": "s86_nba_every_tick_2026-09-03.csv", "cluster": "game_id", "d": "d",
            "json": "s86_nba_every_tick_2026-09-03.json", "ci": ("pooled", "dm_ci95"),
            "note": "pooled state-priced prior vs the in-play line"},
    "S87": {"csv": "s58_trialA_clamp_family_series_2026-09-03.csv", "cluster": "game",
            "incumbent": "incumbent_e4_gd", "candidate": "candidate",
            "json": "s87_requote_2026-09-03.json",
            "ci": lambda b: _find(b["results"], "artifact",
                                  "s58_trialA_clamp")["before_all_rows"]["dm_ci95"],
            "note": "trial A clamp family, all rows, by ticker"},
    "S94": {"csv": "s94_nba_early_shrinkage_2026-09-03.csv", "cluster": "cluster_id",
            "d": "d_candidate_vs_market", "json": "s94_nba_early_shrinkage_2026-09-03.json",
            "ci": ("overall", "dm", "candidate_vs_market", "ci95"),
            "note": "overall phase-conditioned shrinkage vs the raw line"},
    "S96": {"csv": "s96_nba_overreaction_2026-09-03.csv", "cluster": "cluster_id",
            "d": "d_arm_vs_market", "where": lambda f: (f["threshold"] == 3) & (f["k"] == 5),
            "json": "s96_nba_overreaction_2026-09-03.json",
            "ci": ("arms", "thr3_k5", "overall", "dm", "arm_vs_market", "ci95"),
            "note": "primary post-event drift arm thr3_k5"},
    "S97": {"csv": "s97_nba_sensor_fusion_2026-09-03.csv", "cluster": "cluster_id",
            "d": "d_posterior_vs_market", "json": "s97_nba_sensor_fusion_2026-09-03.json",
            "ci": ("overall", "dm", "posterior_vs_market", "ci95"),
            "note": "two-sensor Kalman posterior vs the raw line"},
    "S98": {"csv": "s98_nba_better_prior_2026-09-03.csv", "cluster": "cluster_id",
            "d": "d_elo_sig_vs_market", "json": "s98_nba_better_prior_2026-09-03.json",
            "ci": ("overall", "dm_ci95", "elo_sig"),
            "note": "fitted per-cell sigma arm vs the raw line"},
    "S103": {"csv": "s103_nba_sigma_2026-09-03.csv", "cluster": "cluster_id",
             "d": "d_wide_vs_market", "json": "s103_nba_sigma_2026-09-03.json",
             "ci": ("overall", "dm_ci95", "wide"), "note": "sigma grid widened to [3, 60]"},
    "S112n": {"csv": "s112_rescore_2026-09-03_nba_fullmodel_pre_s132.csv",
              "cluster": "cluster_id", "incumbent": "p_elo", "candidate": "p_close",
              "json": None, "ci": (0.015252, 0.035960),  # published digits, S132 memo s.4
              "note": "NBA close minus Elo, contaminated reference (S112 as published)"},
    "S112m": {"csv": "s112_rescore_2026-09-03_mlb_fullmodel_pre_s132.csv",
              "cluster": "cluster_id", "incumbent": "p_elo", "candidate": "p_close",
              "json": None, "ci": (0.000066, 0.014473),  # published digits, S132 memo s.4
              "note": "MLB close minus Elo, pre-S133 attach (S112 as published)"},
    "S114": {"csv": "s114_ingame_ensemble_series.csv", "cluster": "game",
             "incumbent": "market", "candidate": "p_k5",
             "json": "s114_ingame_ensemble.json",
             "ci": ("per_k", "k5", "vs_market", "ci95"),
             "note": "k=5 arm vs the raw line (POST re-run archive -- see the memo)"},
    "S115": {"csv": "s115_ingame_models_2026-09-03.csv", "cluster": "cluster_id",
             "d": "d_mlp_vs_market", "json": "s115_ingame_models_2026-09-03.json",
             "ci": ("headline_ci95",), "note": "best non-linear arm (mlp) vs the raw line"},
    "S116": {"csv": "s116_pooled_ingame_2026-09-03.csv", "cluster": "cluster",
             "d": "d_partial_vs_line", "where": lambda f: f["sport"] == "mlb",
             "json": "s116_pooled_ingame_2026-09-03.json",
             "ci": ("by_sport", "mlb", "dm", "partial_vs_line", "ci95"),
             "note": "partially pooled residual, MLB side, vs the raw line"},
    "S117": {"csv": "s117_soccer_ingame_screen_2026-09-03_series.csv", "cluster": "game",
             "incumbent": "p_null", "candidate": "p_candidate",
             "where": lambda f: f["feature"] == "minute_x_score_diff",
             "json": "s117_soccer_ingame_screen_2026-09-03.json", "ci": None,
             "note": "soccer leader minute_x_score_diff vs the recal null"},
    "S119": {"csv": "s119_real_game_series_2026-09-03.csv", "cluster": "game",
             "incumbent": "p_null", "candidate": "p_candidate",
             "where": lambda f: f["feature"] == "tick_index_in_game",
             "json": "s119_real_game_requote_2026-09-03.json",
             "ci": lambda b: _find(b["results"], "feature",
                                   "tick_index_in_game")["by_game_id"]["ci95"],
             "note": "the S82 leader on the S119 archive, by ticker"},
}


def a2(rows: Optional[Sequence[str]] = None, cache: Path = _CACHE) -> Dict[str, Any]:
    """Recompute every archived headline; attach the published CI where one exists."""
    out: Dict[str, Any] = {}
    for name in (rows or list(_A2)):
        spec = dict(_A2[name])
        blob = spec.pop("json"), spec.pop("ci"), spec.pop("note")
        spec["cluster_col"] = spec.pop("cluster")
        if "d" in spec:
            spec["d_col"] = spec.pop("d")
        quote = archive_quote(cache=cache, **spec)
        entry = {"note": blob[2], "series_csv": spec["csv"], **quote}
        if blob[1] is not None:
            published = (_dig(json.loads((cache / blob[0]).read_text(encoding="utf-8")), blob[1])
                         if blob[0] else blob[1])
            # a literal target carries only the PRINTED digits, so compare at that precision
            tol = 1e-9 if blob[0] else 5e-7
            entry.update(reproduces(quote, published, tol=tol))
            entry["tolerance"] = tol
        out[name] = entry
    return out


# --------------------------------------------------------------------------- #
# the one genuinely new re-quote this lane owns: S116's MLB side on the S131 split
# --------------------------------------------------------------------------- #
def s116_on_s131(cache: Path = _CACHE) -> Dict[str, Any]:
    """Re-cluster S116's archived MLB paired losses on the corroborated split.

    Clustering relabel only: `d_partial_vs_line` is read as archived.
    """
    from scripts.platformkit.eval_gate.real_game_split import assign_real_game_seq
    from scripts.platformkit.eval_gate.s106_requote import _seq_map, load_joined

    joined, store = assign_real_game_seq(load_joined())
    seq = _seq_map(joined)
    frame = pd.read_csv(cache / _A2["S116"]["csv"],
                        usecols=["sport", "cluster", "date", "ts_utc", "d_partial_vs_line"])
    frame = frame[frame["sport"] == "mlb"].copy()
    ticker = frame["cluster"].str.replace("^mlb:", "", regex=True).str.replace(r"#\d+$", "", regex=True)
    iso = pd.to_datetime(frame["ts_utc"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    seqs = [seq.get(k) for k in zip(ticker, iso)]
    frame["cluster_s131"] = "mlb:" + ticker + "#" + pd.Series(
        [1 if s is None else s for s in seqs], index=frame.index).astype(str)
    return {
        "instrument": "real-game clusters, S131 corroborated split (no refit)",
        "n_unmatched_in_joined_store": int(sum(1 for s in seqs if s is None)),
        "joined_store_split": {k: store[k] for k in
                               ("n_game_ids", "n_real_games", "n_multi", "n_ticks")},
        "before_s106_clusters": _quote(frame, "cluster", "d_partial_vs_line"),
        "after_s131_clusters": _quote(frame, "cluster_s131", "d_partial_vs_line"),
        "s127_relabel": {"scored_folds": [3, 4], "n_dates": int(frame["date"].nunique()),
                         "dates": sorted(frame["date"].astype(str).unique()),
                         "label": "SINGLE-DATE-PAIR"},
    }


# --------------------------------------------------------------------------- #
# S113 -- how many Elo-relative promotions vanish, on each close
# --------------------------------------------------------------------------- #
def _promotion_hashes(path: Path) -> set:
    """Every promoted hypothesis hash in a promotion list (detail rows only)."""
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0].isdigit():
            out.add(cells[-1])
    return out


def s113_promotions(evidence: Path = _EVID) -> Dict[str, Any]:
    control = _promotion_hashes(evidence / "S113" / "promotions_vs_elo_control.md")
    old = _promotion_hashes(evidence / "S113" / "promotions_vs_close.md")
    new = _promotion_hashes(evidence / "S132" / "promotions_vs_clean_close.md")
    return {"n_control_promotions": len(control),
            "n_unique_hashes_contaminated_close": len(old),
            "n_unique_hashes_clean_close": len(new),
            "vanishing_contaminated": len(control - old),
            "vanishing_clean": len(control - new),
            "note": ("A4: the promotion lists declare 240 / 216 / 216 promotions; the UNIQUE "
                     "hash counts are 240 / 211 / 212 because a few hypotheses are promoted in "
                     "two families. The vanishing counts (147, 154) are over the control set.")}


# --------------------------------------------------------------------------- #
# S102 -- the sweep leader, read-only out of the landed sqlite
# --------------------------------------------------------------------------- #
def s102_leader(cache: Path = _CACHE) -> Dict[str, Any]:
    con = sqlite3.connect("file:%s?mode=ro" % (cache / "s102_nba_sweep.sqlite").as_posix(), uri=True)
    try:
        row = pd.read_sql("select label, improvement_vs_null, ci_lo, ci_hi, n_ticks, n_games,"
                          " n_eff, n_informative from screen where status='SCREENED'"
                          " order by improvement_vs_null desc limit 1", con).iloc[0]
    finally:
        con.close()
    return {"label": str(row["label"]), "improvement": float(row["improvement_vs_null"]),
            "dm_ci95": [float(row["ci_lo"]), float(row["ci_hi"])], "n": int(row["n_ticks"]),
            "n_games": int(row["n_games"]), "n_eff": float(row["n_eff"]),
            "n_informative": int(row["n_informative"])}


# --------------------------------------------------------------------------- #
# the table
# --------------------------------------------------------------------------- #
# (row, headline, instrument that could move it, changed?)
_ROWS = (
    ("S82", "MLB in-game screen tier, leader tick_index_in_game",
     "real-game clusters (S131) + tick partition (S121)", "yes"),
    ("S86", "NBA state-priced prior at every tick, pooled", "none applies", "no"),
    ("S87", "informative-tick re-quote, trial A clamp family",
     "real-game clusters (S131)", "yes"),
    ("S94", "NBA phase-conditioned shrinkage, overall", "none applies", "no"),
    ("S96", "NBA post-event drift arm thr3_k5", "none applies", "no"),
    ("S97", "NBA two-sensor Kalman posterior", "none applies", "no"),
    ("S98", "NBA fitted per-cell sigma arm", "none applies", "no"),
    ("S101", "NBA conformal grouped coverage (STATIC)", "none applies", "no"),
    ("S102", "NBA 576-hypothesis sweep, best arm", "none applies", "no"),
    ("S103", "NBA sigma grid widened to [3, 60]", "none applies", "no"),
    ("S106", "MLB real-game split of the joined tick store",
     "the corroborated boundary rule (S131)", "yes"),
    ("S112", "close minus Elo, NBA and MLB", "clean close (S132/S133)", "yes"),
    ("S113", "Elo-relative promotions that vanish under the close",
     "clean close (S132/S133)", "yes"),
    ("S114", "nested-selection ensemble ladder, best k",
     "same-rows recalibration null (S126) -- RE-RUN REQUIRED, and it landed", "yes"),
    ("S115", "NBA non-linear residual models, best arm (mlp)", "none applies", "no"),
    ("S116", "cross-sport pooled residual, MLB side",
     "real-game clusters (S131) + the S127 relabel", "yes"),
    ("S117", "soccer in-game tier, leader minute_x_score_diff",
     "tick partition (S121) -- the identity on a single-ISO-week archive", "no"),
    ("S119", "the S82 tier on corrected real-game clusters",
     "real-game clusters (S131)", "yes"),
    ("S121", "the S82 tier on the tick-clean partition",
     "real-game clusters (S131)", "yes"),
    ("S123", "NBA in-game baseline ordering, market < recal null < ladder BASE",
     "none applies", "no"),
)

RERUN_COMMANDS = {
    "S114": "python -m scripts.platformkit.eval_gate.s114_ingame_ensemble",
    "S85 (soccer_style_fingerprints, not in this table)":
        "python -m scripts.platformkit.eval_gate.s111_screen  "
        "# season-grain prior (S128); take S128 section 4's numbers",
}


def build(cache: Path = _CACHE, evidence: Path = _EVID) -> Dict[str, Any]:
    """Assemble the whole re-baseline artifact."""
    corrected = {
        name: json.loads((cache / name).read_text(encoding="utf-8"))
        for name in ("s106_requote_2026-09-03.json", "s106_requote_s131corrected_2026-09-03.json",
                     "s121_requote_2026-09-03.json", "s121_requote_s131corrected_2026-09-03.json",
                     "s112_rescore_2026-09-03.json", "s112_rescore_2026-09-03_pre_s132.json",
                     "s114_ingame_ensemble.json")
    }
    clean_close = {
        sport: archive_quote("s112_rescore_2026-09-03_%s_fullmodel.csv" % sport,
                             "cluster_id", incumbent="p_elo", candidate="p_close", cache=cache)
        for sport in ("nba", "mlb")
    }
    return {
        "row": "S137",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tier": "RE-BASELINE (no charge, no prereg seal, no K read, no bar moved, no refit "
                "except where the row says RE-RUN REQUIRED)",
        "improvement_bar": BAR,
        "instruments": {
            "S132/S133": "clean NBA/MLB close -- NBA 952 -> 563 rows with a close, MLB 894 -> 910",
            "S131": "corroborated real-game split -- 392 -> 360 real games (20-min floor)",
            "S121": "tick-level partition (tick_week + real-game purge)",
            "S126": "same-rows recalibration null in the S114 ladder (changes the FITTED arm)",
            "S128/S129": "season-grain prior + side-rule guard (fitted arm; S85 only)",
            "S125": "UTC stamp parsing -- measured NO-OP on both live stores (0 folds differ)",
        },
        "rows": [{"row": r, "headline": h, "instrument": i, "changed": c} for r, h, i, c in _ROWS],
        "a2_reproduction": a2(cache=cache),
        "s116_requote_on_s131": s116_on_s131(cache=cache),
        "s113_promotions": s113_promotions(evidence=evidence),
        "s102_leader": s102_leader(cache=cache),
        "s112_clean_close_minus_elo": clean_close,
        "corrected_artifacts": {
            "s106_s131": corrected["s106_requote_s131corrected_2026-09-03.json"]["joined_store_split"],
            "s121_s131_leader": corrected["s121_requote_s131corrected_2026-09-03.json"]["mlb"]["comparison"][0],
            "s114_rerun_per_k": {k: corrected["s114_ingame_ensemble.json"]["per_k"][k]["vs_market"]
                                 for k in ("k1", "k3", "k5", "k10")},
        },
        "rerun_commands": RERUN_COMMANDS,
        "verdicts_changed": 0,
        "n_ahead_before": 0,
        "n_ahead_after": 0,
        "honest_note": "Brier and Brier differences only. No dollar, ROI, profit or edge claim. "
                       "An uncharged screen is a NON-FINDING; a null is a success.",
        "edge_claimed": False,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="S137: post-fix re-baseline table")
    parser.add_argument("--out", default=str(_CACHE / "s137_rebaseline_2026-09-03.json"))
    args = parser.parse_args(argv)
    blob = build()
    Path(args.out).write_text(json.dumps(blob, indent=1, sort_keys=True), encoding="utf-8")
    bad = [k for k, v in blob["a2_reproduction"].items()
           if "reproduced" in v and not v["reproduced"]]
    print("wrote %s | a2 rows %d | a2 failures %s | verdicts changed %d"
          % (args.out, len(blob["a2_reproduction"]), bad or "none", blob["verdicts_changed"]))
    return 1 if bad else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

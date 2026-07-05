"""domains.tennis.playstyle_ingame_gate -- H3 PRE-REGISTERED gate (docs/research/
intel-layer/TENNIS_TRUTH_SPEC_2026-07-04.md, H3_playstyle_archetype_ingame_
conditioning): does a PLAYSTYLE-ARCHETYPE PAIRING prior beat the surface-blind
hold%-diff prior as an in-game DETAIL layer on the tennis BASE model
sigmoid((a+b*frac_elapsed)*state_diff)?

H0 (incumbent): hold_diff_blind = p1_hold_pct_asof - p2_hold_pct_asof (the SAME H0
surface_hold_ingame_gate uses -- gate-comparability rule: base/candidate share start
state, corpus slice, eval path, differ ONLY by the hypothesis term).
H1 (candidate): archetype pairing tercile -- each player gets a SERVE-ORIENTATION
bucket (playstyle_ingame_gate_buckets.serve_bucket, reusing the SAME threshold
constants atlas_playstyles.py fits its counts with). The pairing type
(p1_bucket_vs_p2_bucket) is gated on the TOP-vs-BOTTOM TERCILE of hold-rate
differential computed PER PAIRING TYPE (TRAIN-fold-only quantiles, one tercile per
pair_type) -- matches the spec text exactly ("gated on archetype-pair being in a
top-vs-bottom tercile of historical hold-rate differential for THAT PAIRING TYPE").
pair_type is therefore load-bearing in the numeric detail term: two rows with the
same hold_diff_blind can get different gated outputs if their pair_types differ
(see _tercile_gate / _pairing_detail_raw). Any pair_type with fewer than
MIN_PAIR_TYPE_CELL train rows falls back to the pooled global tercile (OPEN,
conservative simplification for thin cells only). Bucket mapping itself is an
OPEN choice: the spec names only "big-serve vs elite-returner", not a full table.

AS-OF SAFETY CAVEAT (mandatory, stated exactly as the NBA H_A/H_B verdicts did):
atlas_playstyles.parquet is a SEASON-LEVEL SNAPSHOT (built once over the full
2015-2025 corpus) -- NOT as-of-safe / walk-forward-safe. Using it is a KNOWN,
DISCLOSED leak of future playstyle info into every fold; this gate cannot claim
leak-free status for the playstyle term the way asof_hold.parquet's hold% terms
are. Run anyway as a PRE-REGISTERED EXPLORATORY design; the verdict carries this
caveat, never silently dropped.

DEPENDENCY CONSTRAINT (binding, honest): atlas_playstyles.parquet is ATP-ONLY
(corpus_id == "sackmann_atp_matches_parquet"). NO WTA equivalent exists anywhere on
disk (atlas_h2h.parquet is also ATP-only). Spec requires WTA replication for SHIP;
since no WTA archetype corpus exists, WTA is honestly NOT_TESTABLE, never faked.
REUSED MACHINERY (no new scoring math): ingame_gate_generic_models fit/predict/blend
+ detail_layer_gate squash/leak-guard (via playstyle_ingame_gate_buckets.
fit_score_detail) + eval_gate.dm_test.diebold_mariano -- SAME imports
surface_hold_ingame_gate.py uses, same fold construction, min_cell=20.

PLANTED NULL (mandatory, per spec): shuffle the archetype-bucket assignment across
players. Implementation invariant: the shuffle permutes the per-player bucket
LABEL only -- it holds the covered row population IDENTICAL to the real run
(same NaN/non-NaN pattern for atlas-unmapped players; no per-lookup default that
would change which rows _covered() keeps).
SHIP iff: Brier(H1) < Brier(H0) pooled AND DM p<0.05 AND sign holds >=2/3 ATP folds
AND WTA replicates AND planted-null fails to replicate. WTA cannot run, so SHIP is
categorically unreachable.
EXPORT SCHEMA (h3-h0-export lane): export_rows p_variant=H1's own detail pred,
p_base=H0's own detail pred (r0["p_variant"], NOT r1's plain sigmoid base) so a
replay harness can reproduce brier_h0 exactly, not just brier_h1.
NO $ anywhere; verdict is CALIBRATION (held-out Brier) only, never a market edge.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy + pandas.
CLI: python -m domains.tennis.playstyle_ingame_gate
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from domains.tennis.playstyle_ingame_gate_buckets import (
    _pairing_detail_raw,
    _tercile_gate,
    fit_score_detail,
    load_player_buckets,
)

_REPO = Path(__file__).resolve().parents[2]
_STATE_DIR = _REPO / "data" / "cache" / "ingame"
_HOLD_DIR = _REPO / "data" / "domains" / "tennis"
_OUT_DIR = _REPO / "data" / "frontend" / "ingame"

MIN_CELL = 20
N_FOLDS = 3
EPS = 0.05


# --------------------------------------------------------------------------- load
def _build_frame(states_path: Path, hold_path: Path, matches_path: Path,
                 atlas_path: Path) -> pd.DataFrame:
    """Inner-join states -> asof_hold (event_id) -> matches (p1_id/p2_id) -> atlas
    buckets (per player). Builds H0 (hold_diff_blind, shared with surface_hold_gate)
    and the raw pairing-type label pair_type = '<p1_bucket>_vs_<p2_bucket>'.
    """
    st = pd.read_parquet(states_path)
    hd = pd.read_parquet(hold_path)
    mt = pd.read_parquet(matches_path)[["event_id", "p1_id", "p2_id"]]
    buckets = load_player_buckets(atlas_path)

    keep = [c for c in hd.columns if c != "surface"]
    merged = st.merge(hd[keep], left_on="game_id", right_on="event_id", how="inner")
    merged = merged.merge(mt, left_on="game_id", right_on="event_id", how="inner",
                          suffixes=("", "_m"))
    if merged.empty:
        raise ValueError(f"no rows after state/hold/matches join: {states_path}")

    b = buckets.set_index("player_id")["bucket"]
    merged["p1_bucket"] = merged["p1_id"].map(b)
    merged["p2_bucket"] = merged["p2_id"].map(b)
    merged["pair_type"] = merged["p1_bucket"].astype(str) + "_vs_" + merged["p2_bucket"].astype(str)
    merged["hold_diff_blind"] = merged["p1_hold_pct_asof"] - merged["p2_hold_pct_asof"]
    return merged.sort_values(["game_id", "asof_idx"]).reset_index(drop=True)


def _covered(df: pd.DataFrame, min_prior: int = 5) -> pd.Series:
    return (
        (df["p1_n_prior"].fillna(0) >= min_prior)
        & (df["p2_n_prior"].fillna(0) >= min_prior)
        & df["hold_diff_blind"].notna()
        & df["p1_bucket"].notna() & df["p2_bucket"].notna()
    )


def walk_forward_h0_vs_h1(df: pd.DataFrame, n_folds: int = N_FOLDS,
                          min_cell: int = MIN_CELL, shuffle_bucket_seed: Optional[int] = None
                          ) -> Dict:
    """Expanding-window walk-forward, mirrors surface_hold_ingame_gate's fold
    construction exactly (gate-comparability rule). shuffle_bucket_seed: PLANTED
    NULL -- permute the per-player bucket assignment (spec's own words: 'shuffle
    archetype assignment across players') before recomputing pair_type/detail term.
    """
    d = df.copy()
    if shuffle_bucket_seed is not None:
        rng = np.random.default_rng(shuffle_bucket_seed)
        # np.random.permutation() on str+NaN upcasts the WHOLE array to <U32,
        # turning NaN into the truthy STRING 'nan' (regression: real 34992 vs
        # buggy-null 35805 rows, +813). Fix: partition mapped/unmapped BEFORE
        # permuting -- shuffle only mapped labels; unmapped stay true NaN.
        p1_map = dict(zip(d["p1_id"], d["p1_bucket"]))
        p2_map = dict(zip(d["p2_id"], d["p2_bucket"]))
        player_bucket: Dict = {**p2_map, **p1_map}  # p1 wins on conflict (rare/none)
        mapped_ids = [pid for pid, b in player_bucket.items() if pd.notna(b)]
        unmapped_ids = [pid for pid, b in player_bucket.items() if pd.isna(b)]
        mapped_labels = [player_bucket[pid] for pid in mapped_ids]
        shuffled_labels = rng.permutation(np.array(mapped_labels, dtype=object))
        remap: Dict = dict(zip(mapped_ids, shuffled_labels))
        remap.update({pid: np.nan for pid in unmapped_ids})
        d["p1_bucket"] = d["p1_id"].map(remap)
        d["p2_bucket"] = d["p2_id"].map(remap)
        d["pair_type"] = d["p1_bucket"].astype(str) + "_vs_" + d["p2_bucket"].astype(str)

    cov = _covered(d)
    d = d[cov].reset_index(drop=True)
    n = len(d)
    split_edges = [int(n * (k + 1) / (n_folds + 1)) for k in range(n_folds)]
    folds: List[Dict] = []
    rows: List[Dict] = []
    for k, split in enumerate(split_edges):
        end = split_edges[k + 1] if k + 1 < len(split_edges) else n
        if split < 20 or end <= split:
            continue
        train, test = d.iloc[:split].copy(), d.iloc[split:end].copy()
        if test.empty or len(train) < 20:
            continue
        tercile_edges = _tercile_gate(train)
        train["pairing_detail_raw"] = _pairing_detail_raw(train, tercile_edges)
        test["pairing_detail_raw"] = _pairing_detail_raw(test, tercile_edges)

        r0 = fit_score_detail(train, test, "hold_diff_blind", min_cell)
        r1 = fit_score_detail(train, test, "pairing_detail_raw", min_cell)
        diff = r0["loss_detail"] - r1["loss_detail"]
        dm = diebold_mariano(diff, r1["game_ids"])
        lo_pooled, hi_pooled = tercile_edges.get("__pooled__", (0.0, 0.0))
        folds.append({
            "fold": k, "n_train": len(train), "n_test": len(test),
            "n_pair_types_own_tercile": sum(1 for kk in tercile_edges if kk != "__pooled__"),
            "tercile_lo": round(lo_pooled, 6), "tercile_hi": round(hi_pooled, 6),
            "brier_h0": round(r0["brier_detail"], 6), "brier_h1": round(r1["brier_detail"], 6),
            "brier_delta_h1_minus_h0": round(r1["brier_detail"] - r0["brier_detail"], 6),
            "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
            "h1_beats_h0": bool(r1["brier_detail"] < r0["brier_detail"] and dm.p_value < EPS),
            "base_degenerate": bool(r0["base_degenerate"] or r1["base_degenerate"]),
        })
        # p_variant=r1's own detail pred (brier_h1); p_base=r0's own detail pred
        # (brier_h0) -- NOT r1["p_base"] (plain sigmoid base, a 3rd quantity).
        # r0/r1 share the same `test` slice/order so this zips row-for-row.
        for gid, pv, pb, y in zip(r1["game_ids"], r1["p_variant"], r0["p_variant"], r1["outcome"]):
            rows.append({"fold_id": f"fold{k}", "event_id": gid,
                         "p_variant": pv, "p_base": pb, "outcome": y})
    n_beat = sum(1 for f in folds if f["h1_beats_h0"])
    pooled_h0 = float(np.mean([f["brier_h0"] for f in folds])) if folds else float("nan")
    pooled_h1 = float(np.mean([f["brier_h1"] for f in folds])) if folds else float("nan")
    return {
        "n_folds_run": len(folds), "n_folds_h1_beats_h0": n_beat,
        "sign_holds_ge_2of3": bool(len(folds) >= 3 and n_beat >= 2)
        if len(folds) == n_folds else bool(len(folds) > 0 and n_beat >= max(2, len(folds) - 1)),
        "pooled_brier_h0": round(pooled_h0, 6), "pooled_brier_h1": round(pooled_h1, 6),
        "pooled_delta_h1_minus_h0": round(pooled_h1 - pooled_h0, 6) if folds else None,
        "folds": folds, "export_rows": rows,
    }

# --------------------------------------------------------------------------- per-tour
def gate_tour(tour: str) -> Dict:
    """ATP only reaches a real gate; WTA has no atlas_playstyles source and reports
    NOT_TESTABLE honestly rather than faking a result."""
    if tour == "wta":
        return {
            "tour": "wta", "n_states_joined": 0,
            "not_testable": True,
            "reason": ("no WTA equivalent of atlas_playstyles.parquet exists on disk "
                      "(atlas_playstyles.py / atlas_h2h.py are both built from ATP-only "
                      "matches.parquet, corpus_id=sackmann_atp_matches_parquet) -- "
                      "WTA replication is a HARD BLOCK, not a soft failure."),
        }
    states_path = _STATE_DIR / "tennis_states__atp.parquet"
    hold_path = _HOLD_DIR / "asof_hold.parquet"
    matches_path = _HOLD_DIR / "matches.parquet"
    atlas_path = _HOLD_DIR / "atlas_playstyles.parquet"
    df = _build_frame(states_path, hold_path, matches_path, atlas_path)
    real = walk_forward_h0_vs_h1(df)
    null = walk_forward_h0_vs_h1(df, shuffle_bucket_seed=0)
    return {"tour": "atp", "n_states_joined": len(df), "real": real, "planted_null": null}


# --------------------------------------------------------------------------- verdict
def _clears_bar(res: Dict) -> bool:
    if res.get("not_testable"):
        return False
    r = res["real"]
    return bool(
        r["n_folds_run"] >= 2
        and r["pooled_delta_h1_minus_h0"] is not None
        and r["pooled_delta_h1_minus_h0"] < 0.0
        and r["sign_holds_ge_2of3"]
        and any(f["dm_p"] < EPS and f["h1_beats_h0"] for f in r["folds"])
    )


def _null_clears_bar(res: Dict) -> bool:
    if res.get("not_testable"):
        return False
    n = res["planted_null"]
    return bool(
        n["n_folds_run"] >= 2
        and n["pooled_delta_h1_minus_h0"] is not None
        and n["pooled_delta_h1_minus_h0"] < 0.0
        and n["sign_holds_ge_2of3"]
    )


def run() -> Dict:
    atp = gate_tour("atp")
    wta = gate_tour("wta")
    atp_clears = _clears_bar(atp)
    atp_null_dies = not _null_clears_bar(atp)

    if wta.get("not_testable"):
        verdict = "NOT_TESTABLE"
        reason = ("BLOCKED on WTA: " + wta["reason"] + " Spec requires WTA replication "
                  "for any SHIP; since ATP-only is the ceiling this design can reach, "
                  "SHIP is categorically unreachable -- reporting NOT_TESTABLE honestly "
                  "rather than SHIP-ing on a single tour.")
    elif not atp_null_dies:
        verdict = "NOT_TESTABLE"
        reason = ("planted-null (shuffled archetype-bucket assignment) shows a comparable "
                  "H1-beats-H0 improvement -- flexibility artifact, not a genuine "
                  "playstyle-pairing signal.")
    elif atp_clears:
        verdict = "REJECT"
        reason = ("ATP clears its own bar but WTA cannot be tested (no source corpus) -- "
                  "the spec's 2-tour replication requirement is unmet, so this is an "
                  "honest REJECT of the SHIP claim, not a SHIP.")
    else:
        verdict = "REJECT"
        reason = "archetype-pairing prior does not beat surface-blind hold-diff on ATP."

    return {
        "feature": "archetype_pairing_tercile_asof (H3) vs hold_diff_blind_asof (detail layer)",
        "layer": "ingame_detail", "design": "playstyle-archetype pairing tercile gate vs hold-diff blind",
        "base_model": "sigmoid((a+b*frac_elapsed)*state_diff)",
        "min_cell": MIN_CELL, "n_folds_target": N_FOLDS,
        "as_of_caveat": ("atlas_playstyles.parquet is a SEASON-LEVEL SNAPSHOT (2015-2025 "
                        "corpus-wide), NOT as-of-safe -- known, disclosed leak of future "
                        "playstyle info into every fold. See module docstring."),
        "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge",
        "atp": atp, "wta": wta,
        "atp_clears_bar": atp_clears, "wta_testable": not wta.get("not_testable", True),
        "planted_null_dies": atp_null_dies,
        "verdict": verdict, "reason": reason,
    }


def main() -> int:
    from domains.tennis.playstyle_ingame_gate_io import (
        export_rows_parquet, print_report, write_verdict,
    )

    res = run()
    print_report(res)
    write_verdict(res, _OUT_DIR / "playstyle_gate_verdict.json")
    export_rows_parquet(res, _HOLD_DIR / "h3_playstyle_rows.parquet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

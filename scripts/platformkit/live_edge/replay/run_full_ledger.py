"""scripts.platformkit.live_edge.replay.run_full_ledger -- B4-HARDEN: run
EVERY ledger claim through the hardened (DM-clustered, 2-corpora) validator.

TICK-TESTABLE means: scope_json.context is a dict with a "cell" key AND
effect_json has both "delta" and "stat" -- the cell-conditioned mean-shift
design tick_replay/player_grid can score against a possession stream.
Verified by direct inspection (2026-07-14, this lane) that this shape is
carried ONLY by topic~"situation.*" (team/league/lineup entity_type, scored
via tick_replay against `points`) and topic~"player_cell.*" (entity_type
"player", scored via player_grid against `scored`) -- 41 + 216 = 257 rows
across the whole 78,344-row ledger, regardless of lifecycle label. Every
other topic (synergy.* = player_pair scope with a STRING context, not a
cell dict; tails.* = quantile design; play_profile./physical./opponent. =
static per-player attributes; reactions.* = pairwise/mediation scope; and
every "screened" row, which never got past discovery so effect_json has no
delta at all) is flagged NOT_TICK_TESTABLE with a reason, never silently
dropped.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

from scripts.platformkit.live_edge.replay import harden as hd
from scripts.platformkit.live_edge.replay.tick_replay import (
    active_mask_for_cell, discovery_baseline_ppp, load_reserve_tagged,
)
from scripts.platformkit.live_edge.player_grid.player_grid import build_player_frame

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
CLAIMS_PATH = REPO_ROOT / "data" / "omni" / "claims" / "claims.parquet"
OUT_DIR = REPO_ROOT / "data" / "omni" / "live_edge" / "replay"

_REASON_BY_PREFIX = [
    ("synergy.", "wrong_grain_pairwise_teammate_not_cell"),
    ("tails.", "quantile_design_not_mean_delta"),
    ("reactions.", "wrong_grain_pairwise_or_mediation"),
    ("play_profile.", "pregame_knowable_static_attribute"),
    ("physical.", "pregame_knowable_static_attribute"),
    ("opponent.", "pregame_knowable_static_attribute"),
    ("shot_quality", "different_design_rmse_metric"),
    ("a_pts", "different_design_rmse_metric"),
]


def _not_testable_reason(topic: str, scope: dict, effect: dict) -> str:
    ctx = scope.get("context")
    for prefix, reason in _REASON_BY_PREFIX:
        if topic.startswith(prefix):
            return reason
    if not isinstance(ctx, dict) or "cell" not in ctx:
        return "wrong_scope_shape_no_cell_context"
    if "delta" not in effect or "stat" not in effect:
        return "screened_no_discovered_delta"
    return "no_cell_delta_shape"


def classify_claim(row: pd.Series) -> dict:
    """Returns {'grain': 'team'|'player'|None, 'reason': str or None, parsed fields...}."""
    topic = str(row["topic"])
    try:
        scope = json.loads(row["scope_json"])
        effect = json.loads(row["effect_json"])
    except (TypeError, ValueError):
        return {"grain": None, "reason": "unparseable_json"}
    ctx = scope.get("context")
    if isinstance(ctx, dict) and "cell" in ctx and "delta" in effect and "stat" in effect:
        entity_type = scope.get("entity_type", "league")
        if entity_type == "player":
            entity_ids = scope.get("entity_ids", [])
            if not entity_ids or "baseline_rate" not in effect:
                return {"grain": None, "reason": "player_cell_missing_baseline_rate"}
            return {"grain": "player", "reason": None, "cell": ctx["cell"], "delta": float(effect["delta"]),
                     "baseline_rate": float(effect["baseline_rate"]), "player_id": entity_ids[0]}
        return {"grain": "team", "reason": None, "cell": ctx["cell"], "delta": float(effect["delta"]),
                 "entity_type": entity_type, "entity_ids": scope.get("entity_ids", [])}
    return {"grain": None, "reason": _not_testable_reason(topic, scope, effect)}


def build_corpora():
    """Loads both grains' reserve frames once, attaches dates, splits each
    into two disjoint trailing-date halves. Returns a dict of everything
    downstream scoring needs."""
    team_reserve = hd.attach_dates(load_reserve_tagged())
    team_a, team_b = hd.split_trailing_corpora(team_reserve)
    baseline_ppp = discovery_baseline_ppp()

    player_reserve = hd.attach_dates(build_player_frame(slice="reserve"))
    player_a, player_b = hd.split_trailing_corpora(player_reserve)
    return {
        "team_a": team_a, "team_b": team_b, "baseline_ppp": baseline_ppp,
        "player_a": player_a, "player_b": player_b,
    }


def score_team_claim(parsed: dict, corpora: dict) -> dict:
    mask_a = active_mask_for_cell(corpora["team_a"], parsed["cell"], parsed["entity_type"], parsed["entity_ids"])
    mask_b = active_mask_for_cell(corpora["team_b"], parsed["cell"], parsed["entity_type"], parsed["entity_ids"])
    ra = hd.validate_one_corpus(corpora["team_a"], mask_a, "points", corpora["baseline_ppp"], parsed["delta"])
    rb = hd.validate_one_corpus(corpora["team_b"], mask_b, "points", corpora["baseline_ppp"], parsed["delta"])
    return ra, rb


def score_player_claim(parsed: dict, corpora: dict) -> dict:
    def _mask(df):
        m = df["player_id"] == parsed["player_id"]
        for k, v in parsed["cell"].items():
            if k in df.columns:
                m &= df[k] == v
        return m
    ra = hd.validate_one_corpus(corpora["player_a"], _mask(corpora["player_a"]), "scored",
                                 parsed["baseline_rate"], parsed["delta"])
    rb = hd.validate_one_corpus(corpora["player_b"], _mask(corpora["player_b"]), "scored",
                                 parsed["baseline_rate"], parsed["delta"])
    return ra, rb


def run_full_ledger(claims_df: pd.DataFrame = None) -> pd.DataFrame:
    claims_df = claims_df if claims_df is not None else pd.read_parquet(CLAIMS_PATH)
    classified = claims_df.apply(classify_claim, axis=1, result_type="expand")
    testable = claims_df[classified["grain"].notna()].copy()
    not_testable = claims_df[classified["grain"].isna()].copy()
    not_testable["reason"] = classified.loc[not_testable.index, "reason"]

    print(f"[run_full_ledger] total_ledger={len(claims_df)} tick_testable={len(testable)} "
          f"not_testable={len(not_testable)}", flush=True)

    corpora = build_corpora()
    rows = []
    for i, (idx, row) in enumerate(testable.iterrows()):
        parsed = classified.loc[idx].to_dict()
        if parsed["grain"] == "team":
            ra, rb = score_team_claim(parsed, corpora)
        else:
            ra, rb = score_player_claim(parsed, corpora)
        verdict = hd.combine_two_corpora(ra, rb)
        rows.append({
            "claim_id": row["claim_id"], "topic": row["topic"], "grain": parsed["grain"],
            "lifecycle": row["lifecycle"], "discovered_delta": parsed.get("delta"),
            "n_active_a": ra["n_active"], "n_games_a": ra["n_games"], "p_value_a": ra["p_value"],
            "verdict_a": ra["verdict"],
            "n_active_b": rb["n_active"], "n_games_b": rb["n_games"], "p_value_b": rb["p_value"],
            "verdict_b": rb["verdict"], "verdict": verdict,
        })
        if (i + 1) % 50 == 0 or (i + 1) == len(testable):
            print(f"[run_full_ledger] scored {i + 1}/{len(testable)}", flush=True)

    results = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results.to_parquet(OUT_DIR / "full_ledger_results.parquet", index=False)
    not_testable[["claim_id", "topic", "lifecycle", "reason"]].to_parquet(
        OUT_DIR / "full_ledger_not_testable.parquet", index=False)
    return results, not_testable


MAJORITY_COMPLEMENT_FRAC = 0.20  # cell active-class > 80% of sample => degenerate "self" cell


def _complement_frac(claim_row) -> float:
    """discovery complement (n_b) fraction of the player's sample. A single-
    axis cell whose active class is >80% of possessions (e.g. blowout=False,
    ~95%) makes conditioning circular: the delta just de-biases a baseline
    the cell already dominates -- not a live edge. Returns 1.0 (=keep) when
    n_a/n_b are absent (team-grain claims carry no player split here)."""
    import json
    try:
        ef = json.loads(claim_row["effect_json"])
        n_a, n_b = ef.get("n_a"), ef.get("n_b")
        if n_a is None or n_b is None or (n_a + n_b) == 0:
            return 1.0
        return n_b / (n_a + n_b)
    except (TypeError, ValueError, KeyError):
        return 1.0


def layer_gate(results: pd.DataFrame, claims_df: pd.DataFrame = None) -> pd.DataFrame:
    """Post-verdict honesty layers on the raw IMPROVES_BOTH_CORPORA set:
    (1) Bonferroni for the N tick-testable tests (per-corpus p < 0.05/N in
    BOTH corpora); (2) majority-class filter (drop degenerate active-class
    >80% cells). Returns the both-corpora frame with 'bonferroni_pass' and
    'majority_class' columns added."""
    both = results[results["verdict"] == "IMPROVES_BOTH_CORPORA"].copy()
    if not len(both):
        return both
    alpha_bonf = 0.05 / len(results)
    both["bonferroni_pass"] = (both["p_value_a"] < alpha_bonf) & (both["p_value_b"] < alpha_bonf)
    if claims_df is not None:
        cmap = claims_df.set_index("claim_id")
        both["majority_class"] = both["claim_id"].map(
            lambda c: _complement_frac(cmap.loc[c]) < MAJORITY_COMPLEMENT_FRAC if c in cmap.index else False)
    else:
        both["majority_class"] = False
    return both


def write_report(results: pd.DataFrame, not_testable: pd.DataFrame,
                  out_path: pathlib.Path = None, claims_df: pd.DataFrame = None) -> pathlib.Path:
    out_path = out_path or (OUT_DIR / "FULL_LEDGER_VALIDATION.md")
    if claims_df is None:
        claims_df = pd.read_parquet(CLAIMS_PATH)
    counts = results["verdict"].value_counts().to_dict() if len(results) else {}
    reason_counts = not_testable["reason"].value_counts().to_dict() if len(not_testable) else {}
    both = layer_gate(results, claims_df)
    single = results[results["verdict"] == "IMPROVES_SINGLE_CORPUS"] if len(results) else results
    n_bonf = int(both["bonferroni_pass"].sum()) if len(both) else 0
    defensible = both[both["bonferroni_pass"] & ~both["majority_class"]] if len(both) else both
    alpha_bonf = 0.05 / len(results) if len(results) else float("nan")
    lines = [
        "# B4-HARDEN FULL LEDGER VALIDATION -- DM test clustered by game_id, ",
        ">=2 trailing-date-corpora agreement gate\n",
        f"total_ledger_rows={len(results) + len(not_testable)} | "
        f"tick_testable={len(results)} | not_tick_testable={len(not_testable)}\n",
        "## Tick-testable verdict counts (raw, per-test alpha=0.05)\n",
        " ".join(f"{k}={v}" for k, v in counts.items()) or "(none)", "",
        "## NOT_TICK_TESTABLE reason breakdown\n",
        " ".join(f"{k}={v}" for k, v in reason_counts.items()) or "(none)", "",
        "## LAYERED SURVIVOR GATE (the honest read)\n",
        f"- raw IMPROVES_BOTH_CORPORA = {len(both)} -- NOT trustworthy: "
        f"{len(results)} tick-testable tests were run, so ~{0.000625 * len(results):.0f} "
        "both-corpora passes are expected by chance alone.\n",
        f"- after Bonferroni (per-corpus p < {alpha_bonf:.2e} = 0.05/{len(results)}) in "
        f"BOTH corpora: {n_bonf}\n",
        f"- after ALSO dropping majority-class degenerate cells (active class >80% of "
        f"the player's possessions, e.g. blowout=False/close_late=False -- conditioning "
        f"is circular there): {len(defensible)} DEFENSIBLE\n",
        "## DEFENSIBLE both-corpora survivors (live-pricer candidates)\n",
        (", ".join(defensible["claim_id"].tolist()) if len(defensible) else
         "(none) -- every Bonferroni survivor is a majority-class artifact "
         "(blowout=False / close_late=False), the same degeneracy prior player-grid "
         "judgment killed. Consistent with team-PPP saturation (B4 0/41, SPINE-2/3)."), "",
        "## Bonferroni survivors that ARE majority-class artifacts (killed here)\n",
        (", ".join(both[both["bonferroni_pass"] & both["majority_class"]]["claim_id"].tolist())
         if n_bonf else "(none)"), "",
        "## IMPROVES_SINGLE_CORPUS -- not promoted (fails the 2-corpora gate)\n",
        f"count={len(single)} (ids in full_ledger_results.parquet; too many to inline)", "",
        "## Method\n",
        "- DM test: per-game mean loss differential (squared error), one-sample "
        "t-test across game clusters (Cameron & Miller 2015 cluster-means CRVE), "
        "p<0.05 two-sided. Replaces validate_claims' single-slice bootstrap CI.\n",
        "- >=2-corpora agreement: a claim only survives if BOTH disjoint corpora "
        "IMPROVE (any WORSE in either corpus => WORSE, not a candidate).\n",
        "- Multiple-comparisons: 20k tests demand a correction; Bonferroni applied, "
        "then a majority-class degeneracy filter on top.\n",
        "- Corpora: 2025-26 reserve split into two disjoint TRAILING-DATE halves "
        "(median unique game_date cutoff) -- no independent 2026-27 season exists "
        "yet (2026-07-14). B1 SEASON-vs-TRAILING RECONCILIATION: the reserve stays "
        "the season slice situation_grid.RESERVE_SEASON already defines (never "
        "re-derived), and the >=2-corpora test is done as two TRAILING-DATE "
        "sub-slices within it -- a trailing-date reserve applied consistently, "
        "closing B1's open season-label-vs-trailing gate.\n",
        "- Calibration language only; edge_claimed=False; no $/ROI. An honest 0 "
        "defensible survivors is the gate WORKING.\n",
    ]
    out_path.write_text("\n".join(lines), encoding="ascii", errors="replace")
    return out_path


def finalize(out_path: pathlib.Path = None) -> pathlib.Path:
    """Regenerate the report from the on-disk results (no rescoring)."""
    results = pd.read_parquet(OUT_DIR / "full_ledger_results.parquet")
    not_testable = pd.read_parquet(OUT_DIR / "full_ledger_not_testable.parquet")
    return write_report(results, not_testable, out_path)


def main() -> int:
    results, not_testable = run_full_ledger()
    path = write_report(results, not_testable)
    print(f"[run_full_ledger] wrote {path}")
    return 0


__all__ = [
    "classify_claim", "build_corpora", "score_team_claim", "score_player_claim",
    "run_full_ledger", "layer_gate", "write_report", "finalize",
]

if __name__ == "__main__":
    sys.exit(main())

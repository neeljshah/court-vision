"""scripts.platformkit.autoloop.shadow_settle_wired -- M09's wired shadows
#2/#3 (rung-8 is #1, still in shadow_settle_job.py). Each provisional's
metric/corpus shape does not fit the generic brier_model_minus_market
ledger-scan (see shadow_settle_job.py's docstring), so each gets a dedicated
WAIT-FOR-DATA-style shadow that watches new-data readiness only -- never
reruns the source benchmark/gate's own (expensive) simulation or fit; running
the actual rerun + any promotion stays human. Split out of shadow_settle_job
.py to hold the <=300 LOC/file cap.

(2) MLB ingame-CRPS total_runs|end_inning_7 MODEL_SHARPER_PROVISIONAL (n=55,
delta 0.7327, CI[0.413,1.081], see crps_market/last_run_ingame_mlb.json):
watches new grade-joined MLB game-file count vs that benchmark's own
baseline; min_n = the checkpoint's own registered n (comparably-powered
second window).

(3) soccer chain-engine state-conditioning PROVISIONAL_SURVIVOR (F6 gate,
domains/soccer/knowledge/validation_ledger.jsonl, evidence 389ccc71): watches
new StatsBomb-eligible match count (reuses the gate's own
_eligible_competitions filter, never reimplemented) vs
soccer_chain_engine_v1_full_power.json's baseline.

Per-file test: scripts/platformkit/autoloop/test_shadow_settle_job.py
(imports this module's functions directly).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

_REPO = Path(__file__).resolve().parents[3]
MLB_CRPS_KEY = ("wired_shadow", "mlb_ingame_crps_total_end_inning7_disjoint_window", "")
MLB_CRPS_OUT = _REPO / "scripts" / "platformkit" / "benchmarks" / "crps_market" / "last_run_ingame_mlb.json"
_MLB_CRPS_CHECKPOINT = "total_runs|end_inning_7"
SOCCER_CHAIN_KEY = ("wired_shadow", "soccer_chain_state_conditioning_full_power", "")
SOCCER_CHAIN_OUT = _REPO / "data" / "frontend" / "ops" / "soccer_chain_engine_v1_full_power.json"
EXTRA_WATERMARK_PATHS: Tuple[Path, ...] = (
    _REPO / "data" / "cache" / "statsbomb" / "match_meta_full.parquet",  # soccer_chain corpus growth
    MLB_CRPS_OUT, SOCCER_CHAIN_OUT,  # a fresh human rerun re-arms these two wired shadows
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mlb_crps_baseline() -> Optional[Dict[str, Any]]:
    if not MLB_CRPS_OUT.is_file():
        return None
    doc = json.loads(MLB_CRPS_OUT.read_text(encoding="utf-8"))
    cp = doc.get("checkpoints", {}).get(_MLB_CRPS_CHECKPOINT)
    if not cp:
        return None
    return {"n_game_files": int(doc.get("n_game_files", 0)), "min_n": int(cp["n"]),
            "value": cp.get("paired_delta_mean"), "ci95": cp.get("paired_delta_95ci"),
            "verdict": cp.get("verdict")}


def shadow_mlb_crps(state: Dict[str, Any], rec: Callable[[Dict[str, Any]], None], *,
                    n_avail_fn: Optional[Callable[[], int]] = None) -> Dict[str, Any]:
    """Second wired shadow: watches new grade-joined MLB game files vs the
    benchmark's own last-run baseline -- never reruns the simulation itself."""
    if MLB_CRPS_KEY in state["terminal"]:
        return {"status": "terminal"}
    baseline = _mlb_crps_baseline()
    if baseline is None:
        return {"status": "no_baseline"}
    if n_avail_fn is not None:
        n_avail = n_avail_fn()
    else:
        from scripts.platformkit.benchmarks.crps_market import ingame_mlb as IM
        n_avail = len(list(IM._GAME_DIR.glob("*.jsonl"))) if IM._GAME_DIR.is_dir() else 0  # noqa: SLF001
    n_new = n_avail - baseline["n_game_files"]
    if state["last_n"].get(MLB_CRPS_KEY) == n_new:
        return {"status": "unchanged", "n_new": n_new}
    powered = n_new >= baseline["min_n"]
    base = {"source_ledger": MLB_CRPS_KEY[0], "key": MLB_CRPS_KEY[1], "sport": "mlb",
            "as_of": MLB_CRPS_KEY[2], "ts": _now_iso(),
            "metric": "mlb_ingame_crps_new_grade_joined_files", "edge_claimed": False}
    rec(dict(base, kind="SHADOW_TICK", n_forward=int(n_new), value=None, ci95=None,
             powered=bool(powered), min_n=baseline["min_n"],
             note="registered %s (baseline n=%d game files, delta=%s CI=%s); %d new grade-joined "
                  "game files since baseline -- raw-file-count proxy for disjoint-window readiness, "
                  "not a recomputed CRPS stat" % (baseline["verdict"], baseline["n_game_files"],
                                                  baseline["value"], baseline["ci95"], n_new)))
    if powered:
        rec(dict(base, kind="PROMOTE_CANDIDATE", n_forward=int(n_new), powered=True,
                 note="%d new game files (>= min_n=%d) available -- candidate for an independent-"
                      "corpus rerun via scripts.platformkit.benchmarks.crps_market.ingame_mlb "
                      "(existing entrypoint, existing args); promotion bar = CI excluding zero on "
                      "that disjoint window; running it + promotion stays human"
                      % (n_new, baseline["min_n"])))
    return {"status": "ticked", "n_new": n_new, "powered": powered}


def _soccer_chain_baseline() -> Optional[Dict[str, Any]]:
    if not SOCCER_CHAIN_OUT.is_file():
        return None
    doc = json.loads(SOCCER_CHAIN_OUT.read_text(encoding="utf-8"))
    panel_b = doc.get("pooled", {}).get("panel_B_delta_brier_naive_minus_model", {})
    return {"n_matches_total": int(doc.get("n_matches_total", 0)),
            "min_matches": int(doc.get("min_matches_per_competition", 0)),
            "verdict": doc.get("verdict"), "panel_b_ci": panel_b.get("ci95_competition_clustered_bootstrap")}


def shadow_soccer_chain(state: Dict[str, Any], rec: Callable[[Dict[str, Any]], None], *,
                        eligible_n_fn: Optional[Callable[[], int]] = None) -> Dict[str, Any]:
    """Third wired shadow: watches new StatsBomb-eligible match count (reuses
    the gate's own _eligible_competitions filter) vs its own last-run baseline
    -- never refits the model/reruns the MC sim itself."""
    if SOCCER_CHAIN_KEY in state["terminal"]:
        return {"status": "terminal"}
    baseline = _soccer_chain_baseline()
    if baseline is None:
        return {"status": "no_baseline"}
    min_n = baseline["min_matches"]
    if eligible_n_fn is not None:
        n_matches_now = eligible_n_fn()
    else:
        import pandas as pd
        from domains.soccer.chain_engine import validate_full_power as VFP
        min_n = min_n or VFP.MIN_MATCHES_DEFAULT
        meta = pd.read_parquet(VFP.MATCH_META_FULL, columns=["competition"])
        comps = VFP._eligible_competitions(meta, min_n)  # noqa: SLF001 -- the gate's own filter, not reimplemented
        n_matches_now = int(meta["competition"].isin(comps).sum())
    n_new = n_matches_now - baseline["n_matches_total"]
    if state["last_n"].get(SOCCER_CHAIN_KEY) == n_new:
        return {"status": "unchanged", "n_new": n_new}
    powered = n_new >= min_n
    base = {"source_ledger": SOCCER_CHAIN_KEY[0], "key": SOCCER_CHAIN_KEY[1], "sport": "soccer",
            "as_of": SOCCER_CHAIN_KEY[2], "ts": _now_iso(),
            "metric": "soccer_chain_new_eligible_matches", "edge_claimed": False}
    rec(dict(base, kind="SHADOW_TICK", n_forward=int(n_new), value=None, ci95=baseline["panel_b_ci"],
             powered=bool(powered), min_n=min_n,
             note="registered %s (baseline n=%d eligible matches @ min_matches=%d, panel-B CI=%s); "
                  "%d new eligible matches since baseline -- eligible-match-count proxy, not a "
                  "recomputed panel" % (baseline["verdict"], baseline["n_matches_total"], min_n,
                                        baseline["panel_b_ci"], n_new)))
    if powered:
        rec(dict(base, kind="PROMOTE_CANDIDATE", n_forward=int(n_new), powered=True,
                 note="%d new eligible matches (>= min_n=%d) available -- candidate for a rerun via "
                      "domains.soccer.chain_engine.validate_full_power (existing entrypoint, existing "
                      "args); panel-B discipline = pooled CI excludes zero above 0 AND "
                      "n_disjoint_groups_with_survivor < 2 to close; running it + promotion stays human"
                      % (n_new, min_n)))
    return {"status": "ticked", "n_new": n_new, "powered": powered}


__all__ = ["shadow_mlb_crps", "shadow_soccer_chain", "MLB_CRPS_KEY", "SOCCER_CHAIN_KEY",
           "MLB_CRPS_OUT", "SOCCER_CHAIN_OUT", "EXTRA_WATERMARK_PATHS"]

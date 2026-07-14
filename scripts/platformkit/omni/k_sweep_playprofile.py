"""scripts.platformkit.omni.k_sweep_playprofile -- K play_profile dimension (NBA).

Mines the "play_profile" coverage dimension (S15.K1: shot diet + zones, action
tendencies, usage by role, pace preference, foul propensity) from data/cache/
profiles/nba_player_profiles.parquet (long format: entity_id/entity_name/
window/attribute/raw_value/percentile/n). LANDMINE: percentile is ALREADY
orientation-normalized -- claims use raw_value only, never percentile as the
value.

Two claim families:
1. DESCRIPTIVE STATE (type=structural): one claim per (player, attribute) in
   BASKET, season_2025_26 window. A player's shot diet / zone shares / foul
   rate IS his profile, not a discovered effect -- no p-value, no escalation,
   so this does NOT touch the K3 reserve-discipline guard (that guards
   statistical DISCOVERY on held-out rows; this is a literal season-to-date
   snapshot the upstream profile builder already computed and stores).
2. CONDITIONAL test (type=conditional): zone_efg_rim stability, season_2024_25
   (full-season baseline) vs last20_2024_25 (recent-form) -- the one attribute
   with a last20 window populated cheaply (ingredients.rim_fga == n here, so a
   two-proportion z-test applies directly, no per-game reads needed). Both
   windows are fully inside the discovery slice (2025-10-01 cutover per
   k_sweep_nba.RESERVE_CUTOVER) so no reserve rows are touched.

Full 559-player active pool (not the 200-player TOP_N cap other K sweeps use
-- this is a parquet-scan against a pre-aggregated store, cheap at full pool).

Batch write: claims_ledger.add_claim() rebuilds claims.parquet on EVERY call
(append_jsonl_atomic reads+rewrites the whole journal per row); benchmarked
~0.11s/claim on the live journal and growing with file size (O(n) per
append) -- at this sweep's ~6k claims that is 15-30 minutes. Instead
_batch_add_claims appends every new "add" event (same row shape add_claim
writes) in ONE write_text_atomic call, then calls the public
cl.rebuild_parquet() exactly once (benchmarked <1s total for 6k rows).
claims_ledger.py itself is untouched (import-only, per lane ownership).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_k_sweep_playprofile.py -q
"""
from __future__ import annotations

import json
import math
import pathlib
from datetime import datetime, timezone

import pandas as pd

from scripts.platformkit.io_atomic import write_text_atomic
from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_coverage as kc
from scripts.platformkit.omni.k_sweep_nba import BH_ALPHA, bh_adjust

_PROFILES_SOURCE = pathlib.Path("data/cache/profiles/nba_player_profiles.parquet")
_PREDS_DIR = pathlib.Path("data/omni/preds/k_sweep_playprofile_v1")
_LANE = "k_sweep_playprofile_v1"
_DIMENSION = "play_profile"

_DESCRIPTIVE_WINDOW = "season_2025_26"
_BASELINE_WINDOW = "season_2024_25"    # discovery slice: pre-2025-10-01 cutover
_RECENT_WINDOW = "last20_2024_25"      # discovery slice: pre-2025-10-01 cutover
_STABILITY_ATTR = "zone_efg_rim"
MIN_PRACTICAL_EFFECT_EFG = 0.05        # 5 shooting-pct points, on a rate not a points stat

BASKET = (
    "usage_absorption", "spacing_contribution", "halfcourt_attempt_share",
    "halfcourt_efg", "pf_per36", "shot_zone_three_rate_per36",
    "shot_zone_two_rate_per36", "transition_attempt_share",
    "zone_attempt_share_rim", "zone_attempt_share_paint",
)
BASKET_MAJORITY = (len(BASKET) // 2) + 1  # cell MINED needs a basket majority present

# ponytail: mirrors claims_ledger._CLAIMS_DIR/_JOURNAL_NAME layout locally
# (documented there) instead of reaching into that module's private attrs --
# needed for the one-shot batch write below; promote to a shared const if a
# third batch-writer needs the same path.
_CLAIMS_DIR = pathlib.Path("data/omni/claims")
_JOURNAL_NAME = "journal.jsonl"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _journal_path(base_dir=None) -> pathlib.Path:
    d = pathlib.Path(base_dir) if base_dir is not None else _CLAIMS_DIR
    return d / _JOURNAL_NAME


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))


def _two_prop_z(p_a: float, n_a: float, p_b: float, n_b: float) -> dict | None:
    """Two-proportion z-test; p_a/n_a = baseline rate/attempts, p_b/n_b = recent."""
    if pd.isna(p_a) or pd.isna(p_b) or n_a is None or n_b is None or n_a <= 0 or n_b <= 0:
        return None
    se = ((p_a * (1 - p_a) / n_a) + (p_b * (1 - p_b) / n_b)) ** 0.5
    if se == 0:
        return None
    delta = float(p_b - p_a)
    z = delta / se
    p = float(2 * (1 - _norm_cdf(abs(z))))
    return {"delta": delta, "se": se, "z": z, "p": p, "n_a": float(n_a), "n_b": float(n_b)}


def _load_profiles(source=None) -> pd.DataFrame:
    cols = ["entity_id", "entity_name", "window", "attribute", "raw_value", "percentile", "n"]
    if isinstance(source, pd.DataFrame):
        return source[cols].copy()
    src = source if source is not None else _PROFILES_SOURCE
    return pd.read_parquet(src, columns=cols)


def _descriptive_claim(player_id: int, attr: str, row) -> dict:
    scope = {
        "sport": "nba", "entity_type": "player", "entity_ids": [int(player_id)],
        "context": "play_profile", "market_families": [],
    }
    topic = f"play_profile.{attr}"
    if row is None:
        statement = f"NBA player {player_id} {attr} season 2025-26: INSUFFICIENT_DATA"
        effect = {"verdict": "INSUFFICIENT_DATA"}
        evidence = {"source": str(_PROFILES_SOURCE), "window": _DESCRIPTIVE_WINDOW}
    else:
        value, pctl, n = row.raw_value, row.percentile, row.n
        statement = f"NBA player {player_id} {attr} = {value:.4f} (pctl {pctl:.2f}, n {n:.2f}) season 2025-26"
        effect = {"verdict": "DESCRIPTIVE", "raw_value": float(value)}
        evidence = {
            "percentile": float(pctl) if pd.notna(pctl) else None,
            "n": float(n) if pd.notna(n) else None,
            "source": str(_PROFILES_SOURCE), "window": _DESCRIPTIVE_WINDOW,
        }
    return {
        "statement": statement, "type": "structural", "scope": scope, "topic": topic,
        "lifecycle": "screened", "effect": effect, "evidence": evidence,
        "provenance": {"created_by_lane": _LANE, "data_asof": _DESCRIPTIVE_WINDOW},
        "links": {"escalate_to_funnel": False},
    }


def _stability_claim(player_id: int, res: dict | None, p_adj: float | None) -> tuple[dict, bool]:
    scope = {
        "sport": "nba", "entity_type": "player", "entity_ids": [int(player_id)],
        "context": f"{_STABILITY_ATTR}_stability",
    }
    topic = f"play_profile.{_STABILITY_ATTR}_stability"
    statement = f"NBA player {player_id} {_STABILITY_ATTR} delta last20 vs season baseline (2024-25 discovery)"
    if res is None:
        return {
            "statement": statement, "type": "conditional", "scope": scope, "topic": topic,
            "lifecycle": "screened", "effect": {"verdict": "INSUFFICIENT_DATA"},
            "evidence": {"source": str(_PROFILES_SOURCE), "reason": "missing baseline or recent window"},
            "provenance": {"created_by_lane": _LANE, "data_asof": _BASELINE_WINDOW},
            "links": {"escalate_to_funnel": False},
        }, False
    escalate = p_adj is not None and p_adj < BH_ALPHA and abs(res["delta"]) >= MIN_PRACTICAL_EFFECT_EFG
    claim = {
        "statement": statement, "type": "conditional", "scope": scope, "topic": topic,
        "lifecycle": "proposed" if escalate else "screened",
        "effect": {"verdict": "TESTED", "delta": res["delta"], "n_a": res["n_a"], "n_b": res["n_b"]},
        "evidence": {
            "p_value": res["p"], "p_adj_bh": p_adj, "source": str(_PROFILES_SOURCE),
            "test": "two_proportion_z",
            "knowability": "reserve-safe: both windows pre-2025-10-01 cutover",
        },
        "provenance": {"created_by_lane": _LANE, "data_asof": _BASELINE_WINDOW},
        "links": {"escalate_to_funnel": escalate},
    }
    return claim, escalate


def _batch_add_claims(claims: list[dict], base_dir=None) -> int:
    """Append many claims in ONE journal rewrite + ONE parquet rebuild (see
    module docstring for why add_claim()'s per-call rebuild is too slow here)."""
    path = _journal_path(base_dir)
    existing = path.read_text(encoding="ascii") if path.is_file() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    existing_ids = set(cl.query(sport="nba", base_dir=base_dir)["claim_id"])
    lines, added = [], 0
    for claim in claims:
        claim_id = cl.make_claim_id(claim["statement"], claim["scope"])
        if claim_id in existing_ids:
            continue
        row = {
            "event": "add", "claim_id": claim_id, "ts": _utc_now_iso(),
            "statement": claim["statement"], "type": claim["type"], "scope": claim["scope"],
            "topic": claim.get("topic", ""), "lifecycle": claim.get("lifecycle", "proposed"),
        }
        for f in ("effect", "evidence", "provenance", "links"):
            row[f] = claim.get(f) or {}
        lines.append(json.dumps(row, ensure_ascii=True, sort_keys=True, default=str))
        existing_ids.add(claim_id)
        added += 1
    if lines:
        write_text_atomic(path, existing + "\n".join(lines) + "\n", encoding="ascii")
        cl.rebuild_parquet(base_dir=base_dir)
    return added


def run_sweep(base_dir=None, source=None, players: pd.DataFrame | None = None) -> dict:
    profiles = _load_profiles(source)
    active = players if players is not None else kc.load_active_players()

    desc = profiles[(profiles["window"] == _DESCRIPTIVE_WINDOW) & (profiles["attribute"].isin(BASKET))]
    desc_lookup = {(r.entity_id, r.attribute): r for r in desc.itertuples()}

    baseline = profiles[(profiles["window"] == _BASELINE_WINDOW) & (profiles["attribute"] == _STABILITY_ATTR)]
    recent = profiles[(profiles["window"] == _RECENT_WINDOW) & (profiles["attribute"] == _STABILITY_ATTR)]
    baseline_lookup = {r.entity_id: r for r in baseline.itertuples()}
    recent_lookup = {r.entity_id: r for r in recent.itertuples()}

    claims: list[dict] = []
    player_status: dict[int, list[str]] = {}
    desc_rows_out: list[dict] = []
    stability_cells: list[dict] = []

    for _, p in active.iterrows():
        pid = int(p["player_id"])
        present = 0
        for attr in BASKET:
            row = desc_lookup.get((pid, attr))
            claims.append(_descriptive_claim(pid, attr, row))
            if row is not None:
                present += 1
                desc_rows_out.append({
                    "player_id": pid, "attribute": attr,
                    "raw_value": row.raw_value, "percentile": row.percentile, "n": row.n,
                })
        player_status[pid] = ["MINED" if present >= BASKET_MAJORITY else "INSUFFICIENT_DATA"]

        b_row, r_row = baseline_lookup.get(pid), recent_lookup.get(pid)
        res = _two_prop_z(b_row.raw_value, b_row.n, r_row.raw_value, r_row.n) if (b_row is not None and r_row is not None) else None
        stability_cells.append({"player_id": pid, "res": res})

    tested = [c for c in stability_cells if c["res"] is not None]
    adj = bh_adjust([c["res"]["p"] for c in tested])
    for c, a in zip(tested, adj):
        c["p_adj"] = a
    p_adj_map = {c["player_id"]: c["p_adj"] for c in tested}

    for cell in stability_cells:
        pid = cell["player_id"]
        claim, escalate = _stability_claim(pid, cell["res"], p_adj_map.get(pid))
        claims.append(claim)
        if escalate:
            player_status[pid].append("ESCALATED")
        elif cell["res"] is None:
            player_status[pid].append("INSUFFICIENT_DATA")
        else:
            player_status[pid].append("MINED")

    # Row-level retention BEFORE any claim is ledgered (S15.K2 binding).
    preds_path = _PREDS_DIR if base_dir is None else pathlib.Path(base_dir) / _PREDS_DIR.name
    preds_path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(desc_rows_out).to_parquet(preds_path / "descriptive_basket.parquet", index=False)
    pd.DataFrame([
        {"player_id": c["player_id"], "delta": c["res"]["delta"] if c["res"] else None,
         "p": c["res"]["p"] if c["res"] else None, "p_adj": c.get("p_adj")}
        for c in stability_cells
    ]).to_parquet(preds_path / f"{_STABILITY_ATTR}_stability.parquet", index=False)

    claims_added = _batch_add_claims(claims, base_dir=base_dir)

    priority = {"ESCALATED": 3, "MINED": 2, "INSUFFICIENT_DATA": 1}
    n_claims_per_player = len(BASKET) + 1
    for pid, statuses in player_status.items():
        best = max(statuses, key=lambda s: priority[s])
        kc.update_cell(pid, _DIMENSION, best, n_claims_per_player, base_dir=base_dir)

    metrics = kc.k5_metrics(base_dir=base_dir)
    insufficient_desc = sum(1 for sts in player_status.values() if sts[0] == "INSUFFICIENT_DATA")
    escalations = sum(1 for sts in player_status.values() if "ESCALATED" in sts)
    return {
        "players_covered": len(player_status),
        "cells_mined": len(claims),
        "claims_added": claims_added,
        "insufficient_data_share": round(insufficient_desc / len(player_status), 4) if player_status else 0.0,
        "bh_survivors": sum(1 for c in tested if c["p_adj"] < BH_ALPHA),
        "escalations": escalations,
        "basket_majority_floor": BASKET_MAJORITY,
        "k5_metrics": metrics,
    }


if __name__ == "__main__":
    result = run_sweep()
    for k, v in result.items():
        if k != "k5_metrics":
            print(f"[k_sweep_playprofile_v1] {k}: {v}")
    print(f"[k_sweep_playprofile_v1] k5_metrics: {result['k5_metrics']}")

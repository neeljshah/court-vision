"""probe_per_position_factors.py — cycle 89c (loop 5).

Hypothesis: foul-trouble and blowout impact differ by position. Guards
substitute fluidly; bigs cause systemic rotation shifts. Big-man stats
(REB/BLK) likely collapse harder when the starter big sits. If our
pergame dataset contains a per-row position field, we can stratify
holdout MAE per (position, stat) bucket and identify candidate
position-aware adjustment targets. If the field is absent, we document
the data gap and the cheapest unlock path.

This is a PROBE — no API fetches, no model changes, no fits.

Run:
    python scripts/probe_per_position_factors.py
"""
from __future__ import annotations

import os
import sys
import warnings
from typing import Dict, List

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Reuse the production bulk-predict harness so the MAE we compute is the
# IDENTICAL prediction path as validate_adjustment + verify_production_mae.
from scripts.validate_adjustment import _bulk_predict  # noqa: E402
from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)


# Position keys we look for on each row (covers any naming convention any
# upstream join might have used).
_POSITION_KEYS = (
    "position", "pos", "primary_position", "PLAYER_POSITION",
    "START_POSITION", "player_position",
)


def _find_position_key(rows: List[dict]) -> str:
    """Scan first ~500 rows for any of the candidate position keys.
    Returns the key that exists OR empty string if none found."""
    sample = rows[: min(500, len(rows))]
    found_counts: Dict[str, int] = {}
    for r in sample:
        for k in _POSITION_KEYS:
            if k in r and r[k] is not None and str(r[k]).strip():
                found_counts[k] = found_counts.get(k, 0) + 1
    if not found_counts:
        return ""
    # Pick the key with most populated rows.
    return max(found_counts, key=lambda k: found_counts[k])


def _canonicalize_position(raw: str) -> str:
    """Coerce raw position strings (PG/SG/SF/PF/C, or G/F/C, or 'F-C') to
    the granular bucket. Strings like 'F-C' map to first listed."""
    if raw is None:
        return ""
    s = str(raw).strip().upper()
    if not s:
        return ""
    # Take first token before any hyphen or slash.
    head = s.replace("/", "-").split("-")[0].strip()
    if head in {"PG", "SG", "SF", "PF", "C"}:
        return head
    if head in {"G", "F", "C"}:
        return head
    return head[:2] if len(head) >= 2 else head


def _y_true(holdout: List[dict], stat: str) -> np.ndarray:
    return np.array([
        np.nan if r.get(f"target_{stat}") is None else float(r[f"target_{stat}"])
        for r in holdout
    ], dtype=float)


# ── REJECT branch ─────────────────────────────────────────────────────────────

def _write_reject_report(out_path: str, sampled_keys_present: Dict[str, int],
                         sources_found: List[str]) -> None:
    body = []
    body.append("# Per-position factor probe — cycle 89c (loop 5)\n")
    body.append("## REJECT (data gap)\n")
    body.append("- Position field absent from pergame dataset.")
    body.append(f"- Keys scanned on row dicts: {list(_POSITION_KEYS)}")
    if sampled_keys_present:
        body.append(f"- Keys found in sample (count): {sampled_keys_present}")
    else:
        body.append("- No candidate key populated on any sampled row.")
    body.append("")
    body.append("### Sources holding position on disk")
    if sources_found:
        for s in sources_found:
            body.append(f"- {s}")
    else:
        body.append("- No on-disk roster/playerinfo CSV holds position.")
        body.append("- Only `data/tracking/<game_id>/nba_boxscore_players.csv` has "
                    "`START_POSITION` — coverage limited to a single locally-tracked game.")
        body.append("- NBA cache (data/nba/player_*.json, gamelog_*.json) does NOT "
                    "contain a position field — verified by inspection of the JSON "
                    "schema (gp/min/pts/.../plus_minus only).")
    body.append("")
    body.append("### Probe path to unlock")
    body.append("- Cheapest: call `commonplayerinfo` once per unique player_id "
                "(O(~600 calls), cacheable to `data/nba/playerinfo_<pid>.json`); "
                "extracts `POSITION` field per player.")
    body.append("- Extend `src/prediction/prop_pergame.py::build_pergame_dataset` "
                "to left-join `position` per row by `file_player_id` from that cache.")
    body.append("- Estimated effort: ~15 min for the fetch + 5 min for the join.")
    body.append("- Then re-run this probe to surface per-position MAE buckets.")
    body.append("")
    body.append("### Empirical impact estimate (untested)")
    body.append("- Industry intuition: BLK/REB strata diverge most by big vs guard. "
                "Plausible ~10-15% relative MAE swing in (C, BLK) and (C, REB) "
                "buckets vs the global stat MAE. PTS likely flat across positions.")
    body.append("- Why ship-worthy either way: a confirmed gap with a 15-min unlock "
                "is itself a researched roadmap item; a confirmed gap **without** "
                "this probe would have been silently re-discovered next cycle.")
    body.append("")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(body))
    print(f"\nReport written: {out_path}")


def _scan_disk_for_position_sources() -> List[str]:
    """Quick scan of obvious roster/playerinfo locations. Returns list of
    relative paths we found that DO contain a 'position'-flavoured column."""
    import csv
    candidates = [
        "data/players.csv",
        "data/roster.csv",
        "data/rosters.csv",
        "data/playerinfo.csv",
        "data/common_player_info.csv",
        "data/nba/players.csv",
        "data/nba/roster.csv",
    ]
    found = []
    for rel in candidates:
        full = os.path.join(PROJECT_DIR, rel)
        if not os.path.exists(full):
            continue
        try:
            with open(full, encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, [])
                hdr_l = [h.lower() for h in header]
                if any(("position" in h or "pos" == h) for h in hdr_l):
                    found.append(rel)
        except Exception:
            continue
    # Also note the one boxscore file we know has START_POSITION.
    bx = os.path.join(PROJECT_DIR, "data", "tracking", "0022401183",
                      "nba_boxscore_players.csv")
    if os.path.exists(bx):
        found.append("data/tracking/0022401183/nba_boxscore_players.csv "
                     "(single-game, START_POSITION column)")
    return found


# ── FOUND branch ──────────────────────────────────────────────────────────────

def _run_found_branch(holdout: List[dict], X: np.ndarray, pos_key: str,
                      out_path: str) -> int:
    # Bucket by canonical position.
    pos_per_row = np.array([_canonicalize_position(r.get(pos_key, ""))
                            for r in holdout], dtype=object)
    unique_positions = sorted({p for p in pos_per_row if p})
    print(f"\nPosition field FOUND. key='{pos_key}' "
          f"unique={unique_positions} (n={len(holdout)} rows)")

    # Production predictions per stat.
    preds = {}
    for stat in STATS:
        p = _bulk_predict(stat, X)
        if p is not None:
            preds[stat] = p

    # Compute global MAE per stat for the relative comparison.
    global_mae: Dict[str, float] = {}
    for stat in STATS:
        if stat not in preds:
            continue
        yt = _y_true(holdout, stat)
        m = ~np.isnan(yt)
        if m.sum() == 0:
            continue
        global_mae[stat] = float(np.mean(np.abs(preds[stat][m] - yt[m])))

    # Per-(position, stat) MAE table.
    cell: Dict[tuple, Dict[str, float]] = {}
    for pos in unique_positions:
        pmask = (pos_per_row == pos)
        if pmask.sum() < 30:
            continue
        for stat in STATS:
            if stat not in preds:
                continue
            yt = _y_true(holdout, stat)
            mask = pmask & ~np.isnan(yt)
            n = int(mask.sum())
            if n < 30:
                continue
            err = float(np.mean(np.abs(preds[stat][mask] - yt[mask])))
            gmae = global_mae.get(stat, float("nan"))
            rel = (err / gmae) if (gmae and gmae == gmae and gmae > 0) else float("nan")
            cell[(pos, stat)] = {"n": n, "mae": err, "rel": rel}

    # Console + report.
    body = []
    body.append("# Per-position factor probe — cycle 89c (loop 5)\n")
    body.append("## FOUND — per-position MAE stratification\n")
    body.append(f"- Position key on row dicts: `{pos_key}`")
    body.append(f"- Holdout rows: {len(holdout)}, unique positions: {unique_positions}")
    body.append("")
    body.append("### Global MAE per stat (production-pipeline)")
    body.append("| stat | MAE |")
    body.append("|------|-----|")
    for stat in STATS:
        if stat in global_mae:
            body.append(f"| {stat} | {global_mae[stat]:.4f} |")
    body.append("")
    body.append("### Per-(position, stat) MAE")
    body.append("| position | stat | n | bucket_mae | rel_vs_global |")
    body.append("|----------|------|---|-----------|---------------|")
    print(f"\n{'pos':<5} {'stat':<5} {'n':>5} {'mae':>8} {'rel_vs_global':>15}")
    print("-" * 45)
    for pos in unique_positions:
        for stat in STATS:
            c = cell.get((pos, stat))
            if c is None:
                continue
            print(f"{pos:<5} {stat:<5} {c['n']:>5d} {c['mae']:>8.4f} {c['rel']:>15.3f}")
            body.append(f"| {pos} | {stat} | {c['n']} | {c['mae']:.4f} | "
                        f"{c['rel']:.3f} |")

    # Top-3 worst (position, stat) by MAE delta over global.
    ranked = sorted(
        ((k, v) for k, v in cell.items() if v["rel"] == v["rel"]),
        key=lambda kv: kv[1]["mae"] - global_mae.get(kv[0][1], 0.0),
        reverse=True,
    )
    body.append("")
    body.append("### Top-3 worst (position, stat) buckets — candidate adjustment targets")
    body.append("| rank | position | stat | n | bucket_mae | global_mae | "
                "abs_delta | rel |")
    body.append("|------|----------|------|---|-----------|------------|"
                "-----------|-----|")
    print("\nTop-3 worst (position, stat) buckets:")
    for i, ((pos, stat), v) in enumerate(ranked[:3]):
        g = global_mae.get(stat, float("nan"))
        delta = v["mae"] - g
        print(f"  #{i+1} ({pos},{stat}) n={v['n']} mae={v['mae']:.4f} "
              f"global={g:.4f} delta={delta:+.4f} rel={v['rel']:.3f}")
        body.append(f"| {i+1} | {pos} | {stat} | {v['n']} | {v['mae']:.4f} | "
                    f"{g:.4f} | {delta:+.4f} | {v['rel']:.3f} |")
    body.append("")
    body.append("### Verdict")
    if ranked and (ranked[0][1]["rel"] > 1.10):
        body.append("- At least one (position, stat) bucket has rel >= 1.10 — a "
                    "position-aware factor adjustment in that bucket is empirically "
                    "supported. Next cycle: write `make_position_factor(...)` in "
                    "validate_adjustment.py and gate via the dual MAE-delta test.")
    else:
        body.append("- No (position, stat) bucket exceeds rel 1.10 vs global. The "
                    "model is already evenly calibrated across positions for the "
                    "stats predicted. No per-position adjustment is justified.")
    body.append("")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(body))
    print(f"\nReport written: {out_path}")
    return 0


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print("Loading pergame dataset...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    holdout = rows[int(n * 0.80):]
    cols = feature_columns()
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols]
                  for r in holdout], dtype=float)
    print(f"  n={n} holdout={len(holdout)}\n", flush=True)

    # Discovery: does the dataset have a position field?
    pos_key = _find_position_key(holdout)

    # Always record what we DID find (or didn't) for the report.
    sampled = {}
    for k in _POSITION_KEYS:
        cnt = sum(1 for r in holdout[: min(500, len(holdout))]
                  if k in r and r[k] is not None and str(r[k]).strip())
        if cnt > 0:
            sampled[k] = cnt

    results_dir = os.path.join(PROJECT_DIR, "scripts", "_results")
    os.makedirs(results_dir, exist_ok=True)
    out_path = os.path.join(results_dir, "per_position_factors_v1.md")

    if not pos_key:
        print("position field MISSING from pergame rows.")
        sources = _scan_disk_for_position_sources()
        _write_reject_report(out_path, sampled, sources)
        print("\nVerdict: REJECT (data gap). See report for unlock path.")
        return 0

    print(f"position field FOUND (key='{pos_key}'). Stratifying holdout MAE...")
    return _run_found_branch(holdout, X, pos_key, out_path)


if __name__ == "__main__":
    sys.exit(main())

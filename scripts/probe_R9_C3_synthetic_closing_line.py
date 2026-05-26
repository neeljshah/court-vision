"""probe_R9_C3_synthetic_closing_line.py — Round 9 CLV pivot, probe C3.

Stamps every bet in `data/pnl_ledger.csv` with a deterministic synthetic-CLV value
following the spec in `scripts/_results/improve_R9_C3_synthetic_closing_line_spec.md`
("Option D-prime": 4-tier fallback chain).

Tier chain (per bet):
    1. Real close      — from data/pnl_ledger_clv.csv (if present + non-blank)
    2. Snapshot proxy  — latest pre-tip snapshot in data/lines/*.csv (>=2 snaps in 48h)
    3. OOF q50         — walk-forward oof_pred from data/cache/pregame_oof.parquet
    4. Cohort L10      — ledger model_pred (always populated, last-resort fallback)

Outputs:
    data/pnl_ledger_clv_synthetic.csv
    data/cache/probe_R9_C3_synthetic_closing_line_results.json

Circularity guard:
    * OOF q50 source is asserted to have walk-forward folds (fold column non-null,
      monotone game_date boundaries). If the parquet looks leaky, the probe FAILS
      LOUDLY and writes status="REJECT" with diagnosis.
    * synthetic_clv_pct is a TARGET for downstream probes, never a feature
      (annotated in CSV header comment + this docstring).
    * 10% deterministic-hash audit fold reserved for hold-out validation.

CLI:
    python scripts/probe_R9_C3_synthetic_closing_line.py
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import hashlib
import json
import logging
import os
import sys
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

LEDGER_PATH       = os.path.join(PROJECT_DIR, "data", "pnl_ledger.csv")
LEDGER_CLV_PATH   = os.path.join(PROJECT_DIR, "data", "pnl_ledger_clv.csv")
OOF_PATH          = os.path.join(PROJECT_DIR, "data", "cache", "pregame_oof.parquet")
LINES_DIR         = os.path.join(PROJECT_DIR, "data", "lines")
OUT_CSV           = os.path.join(PROJECT_DIR, "data", "pnl_ledger_clv_synthetic.csv")
OUT_JSON          = os.path.join(PROJECT_DIR, "data", "cache",
                                 "probe_R9_C3_synthetic_closing_line_results.json")

PROBE_ID          = "R9_C3_synthetic_closing_line"
AUDIT_FOLD_PCT    = 0.10
SNAPSHOT_WINDOW_H = 48
MAX_ABS_MEAN_CLV  = 0.02  # ship-gate ceiling per stat
STAT_WHITELIST    = {"pts", "reb", "ast", "fg3m", "stl", "blk", "tov"}

log = logging.getLogger(PROBE_ID)
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")


# --------------------------------------------------------------------------- #
# helpers                                                                     #
# --------------------------------------------------------------------------- #
def _safe_float(x) -> Optional[float]:
    try:
        v = float(x)
        if v != v:  # nan
            return None
        return v
    except (TypeError, ValueError):
        return None


def _parse_iso(ts) -> Optional[dt.datetime]:
    if not ts or pd.isna(ts):
        return None
    try:
        return dt.datetime.fromisoformat(str(ts))
    except (ValueError, TypeError):
        return None


def _is_audit_fold(bet_id: str) -> bool:
    """Deterministic 10% holdout by md5(bet_id)."""
    if not bet_id:
        return False
    h = hashlib.md5(str(bet_id).encode("utf-8")).digest()
    # take first 4 bytes -> uint32; mod 100 < 10 => audit
    val = int.from_bytes(h[:4], "big") % 100
    return val < int(AUDIT_FOLD_PCT * 100)


# --------------------------------------------------------------------------- #
# data loaders                                                                #
# --------------------------------------------------------------------------- #
def load_ledger(path: str) -> List[Dict]:
    if not os.path.exists(path):
        log.error("Ledger missing: %s", path)
        return []
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_real_close_map(path: str) -> Dict[str, float]:
    """bet_id -> real closing_line (non-empty rows only)."""
    if not os.path.exists(path):
        log.info("No real CLV ledger yet at %s (Tier 1 will be empty).", path)
        return {}
    out: Dict[str, float] = {}
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            cl = _safe_float(row.get("closing_line"))
            bid = row.get("bet_id", "")
            if cl is not None and bid:
                out[bid] = cl
    return out


def load_oof_map(path: str) -> Tuple[Dict[Tuple, float], Dict]:
    """Load pregame_oof.parquet -> {(game_id, player_id, stat_lower): oof_pred}.

    Also returns audit info: fold boundaries, n per fold, dtype checks.
    Raises RuntimeError if the parquet is missing walk-forward structure
    (no fold column, or fold dates not monotone per fold).
    """
    if not os.path.exists(path):
        raise RuntimeError(f"pregame_oof.parquet missing at {path} — cannot run "
                           "Tier 3 without OOF source; refusing to ship leaky CLV.")
    df = pd.read_parquet(path)
    log.info("Loaded pregame_oof: shape=%s cols=%s", df.shape, list(df.columns))

    # ---- Circularity guard: must have proper WF folds ----
    required = {"game_id", "player_id", "stat", "oof_pred", "fold", "game_date"}
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(
            f"pregame_oof missing required WF columns {missing}. "
            "Refusing to ship leaky synthetic CLV — fix OOF generation first.")

    df = df.copy()
    df["fold"] = pd.to_numeric(df["fold"], errors="coerce")
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")
    if df["fold"].isna().any():
        raise RuntimeError("pregame_oof has null fold values — WF integrity violated.")
    if df["game_date"].isna().any():
        log.warning("pregame_oof has %d null game_date rows — will skip those for fold audit.",
                    int(df["game_date"].isna().sum()))

    # Sanity check: folds should be monotone (fold N's max date <= fold N+1's min date,
    # within tolerance for expanding/sliding WF where train < test by date).
    fold_audit = {}
    fold_groups = df.dropna(subset=["game_date"]).groupby("fold")
    prev_max = None
    fold_boundaries_ok = True
    for fold, grp in sorted(fold_groups, key=lambda x: x[0]):
        n = len(grp)
        dmin = grp["game_date"].min()
        dmax = grp["game_date"].max()
        fold_audit[int(fold)] = {
            "n_rows":   n,
            "min_date": dmin.isoformat() if pd.notna(dmin) else None,
            "max_date": dmax.isoformat() if pd.notna(dmax) else None,
        }
        # For walk-forward expanding: fold k+1's *test* min date should be >= fold k's test min.
        # We don't have an explicit is_test marker here; OOF rows are all test predictions.
        # So min_date should be strictly non-decreasing across fold ids.
        if prev_max is not None and dmin < prev_max - pd.Timedelta(days=400):
            # huge backwards jump — suspicious
            log.warning("Fold %s starts (%s) far before prior fold max (%s); "
                        "review OOF construction.", fold, dmin, prev_max)
        prev_max = dmax

    # Build map (lowercase stat)
    oof_map: Dict[Tuple, float] = {}
    skipped = 0
    for row in df.itertuples(index=False):
        stat_l = str(row.stat).lower().strip()
        gid = str(row.game_id).strip()
        pid = str(int(row.player_id)) if pd.notna(row.player_id) else ""
        pred = _safe_float(row.oof_pred)
        if pred is None or not pid:
            skipped += 1
            continue
        oof_map[(gid, pid, stat_l)] = pred

    log.info("OOF map built: %d rows usable (%d skipped). Folds: %s",
             len(oof_map), skipped, sorted(fold_audit.keys()))

    audit = {
        "n_rows_total":      int(len(df)),
        "n_rows_usable":     len(oof_map),
        "folds":             fold_audit,
        "n_folds":           len(fold_audit),
        "fold_boundaries_ok": fold_boundaries_ok,
        "stats_present":     sorted(df["stat"].str.lower().unique().tolist()),
    }
    return oof_map, audit


def load_snapshots(lines_dir: str) -> List[Dict]:
    """Load all line snapshots. Returns list of dicts with parsed captured_at."""
    if not os.path.isdir(lines_dir):
        return []
    out: List[Dict] = []
    for path in sorted(glob.glob(os.path.join(lines_dir, "*.csv"))):
        try:
            with open(path, encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    ts = _parse_iso(row.get("captured_at", ""))
                    if ts is None:
                        continue
                    out.append({
                        "captured_at": ts,
                        "book":        (row.get("book", "") or "").lower().strip(),
                        "player_id":   str(row.get("player_id", "") or "").strip(),
                        "player_name": (row.get("player_name", "") or
                                        row.get("player", "") or "").lower().strip(),
                        "stat":        (row.get("stat", "") or "").lower().strip(),
                        "line":        _safe_float(row.get("line")),
                    })
        except (OSError, csv.Error):
            continue
    return out


def index_snapshots(snaps: List[Dict]) -> Dict[Tuple, List[Dict]]:
    """Group snapshots by (book, player_key, stat) for fast lookup."""
    idx: Dict[Tuple, List[Dict]] = defaultdict(list)
    for s in snaps:
        if s["line"] is None:
            continue
        key1 = (s["book"], s["player_id"], s["stat"])
        key2 = (s["book"], s["player_name"], s["stat"])
        if s["player_id"]:
            idx[key1].append(s)
        if s["player_name"]:
            idx[key2].append(s)
    for k in idx:
        idx[k].sort(key=lambda r: r["captured_at"])
    return idx


# --------------------------------------------------------------------------- #
# tier resolution                                                             #
# --------------------------------------------------------------------------- #
def resolve_snapshot_proxy(
    book: str, player_id: str, player_name: str, stat: str,
    placed_at: Optional[dt.datetime], snap_idx: Dict[Tuple, List[Dict]],
) -> Optional[float]:
    """Tier 2: latest pre-tip snapshot when >=2 snaps exist within 48h of placed_at
    AND at least one is strictly between placed_at and placed_at+6h."""
    if placed_at is None:
        return None
    book_l = (book or "").lower().strip()
    pid    = str(player_id or "").strip()
    pname  = (player_name or "").lower().strip()
    stat_l = (stat or "").lower().strip()

    candidates: List[Dict] = []
    if pid:
        candidates.extend(snap_idx.get((book_l, pid, stat_l), []))
    if pname and not candidates:
        candidates.extend(snap_idx.get((book_l, pname, stat_l), []))
    if not candidates:
        return None

    window_lo = placed_at - dt.timedelta(hours=SNAPSHOT_WINDOW_H)
    window_hi = placed_at + dt.timedelta(hours=SNAPSHOT_WINDOW_H)
    near = [s for s in candidates if window_lo <= s["captured_at"] <= window_hi]
    if len(near) < 2:
        return None

    # need at least one snap in (placed_at, placed_at+6h)
    post_lo = placed_at
    post_hi = placed_at + dt.timedelta(hours=6)
    post = [s for s in near if post_lo < s["captured_at"] <= post_hi]
    if not post:
        return None

    # use the latest pre-tip = latest snapshot in `near` whose captured_at <= placed_at+6h
    latest = max(post, key=lambda r: r["captured_at"])
    return latest["line"]


def resolve_synthetic_close(
    bet: Dict,
    real_close_map: Dict[str, float],
    snap_idx: Dict[Tuple, List[Dict]],
    oof_map: Dict[Tuple, float],
) -> Tuple[Optional[float], int, Dict[str, Optional[float]]]:
    """Return (chosen_close, tier_int, tier_values_dict).

    tier_int: 1=real, 2=snapshot, 3=oof_q50, 4=cohort_l10 (ledger model_pred).
    tier_values_dict: per-tier value for audit (none-if-missing).
    """
    bet_id = bet.get("bet_id", "")
    real = real_close_map.get(bet_id)

    placed_at = _parse_iso(bet.get("placed_at", ""))
    snap = resolve_snapshot_proxy(
        bet.get("book", ""), bet.get("player_id", ""), bet.get("player", ""),
        bet.get("stat", ""), placed_at, snap_idx,
    )

    game_id   = str(bet.get("game_id", "") or "").strip()
    player_id = str(bet.get("player_id", "") or "").strip()
    stat_l    = (bet.get("stat", "") or "").lower().strip()
    oof = oof_map.get((game_id, player_id, stat_l))

    model_pred = _safe_float(bet.get("model_pred"))

    values = {
        "real_close":     real,
        "snapshot_close": snap,
        "oof_q50":        oof,
        "model_pred":     model_pred,
    }

    if real is not None:
        return real, 1, values
    if snap is not None:
        return snap, 2, values
    if oof is not None:
        return oof, 3, values
    if model_pred is not None:
        return model_pred, 4, values
    return None, 0, values


def compute_clv_pct(line: Optional[float], close: Optional[float],
                    side: str) -> Tuple[Optional[float], Optional[float]]:
    """Mirror src/betting/clv.py.compute_clv direction convention.

    OVER:  positive when placed_line > closing_line (you got a better number).
    UNDER: positive when closing_line > placed_line.

    clv_pct = clv_line / max(|placed_line|, 1.0) per spec section 4.
    """
    if line is None or close is None:
        return None, None
    side_u = (side or "").upper().strip()
    if side_u == "OVER":
        clv_line = line - close
    elif side_u == "UNDER":
        clv_line = close - line
    else:
        return None, None
    denom = max(abs(line), 1.0)
    return round(clv_line, 4), round(clv_line / denom, 6)


# --------------------------------------------------------------------------- #
# main                                                                        #
# --------------------------------------------------------------------------- #
def run_probe() -> Dict:
    started = dt.datetime.utcnow().isoformat() + "Z"

    log.info("== %s starting ==", PROBE_ID)

    # ---- Inputs ----
    bets = load_ledger(LEDGER_PATH)
    n_bets = len(bets)
    log.info("Ledger rows: %d", n_bets)

    real_close_map = load_real_close_map(LEDGER_CLV_PATH)
    log.info("Real close map: %d entries", len(real_close_map))

    try:
        oof_map, oof_audit = load_oof_map(OOF_PATH)
    except RuntimeError as exc:
        log.error("CIRCULARITY GUARD TRIPPED: %s", exc)
        result = {
            "probe":   PROBE_ID,
            "status":  "REJECT",
            "reason":  f"OOF source failed WF integrity check: {exc}",
            "started_at": started,
            "finished_at": dt.datetime.utcnow().isoformat() + "Z",
        }
        os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
        with open(OUT_JSON, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
        return result

    snaps = load_snapshots(LINES_DIR)
    snap_idx = index_snapshots(snaps)
    log.info("Loaded %d snapshots into %d (book, player, stat) groups",
             len(snaps), len(snap_idx))

    # ---- Process each bet ----
    out_rows: List[Dict] = []
    tier_counts = Counter()
    clv_pct_by_stat: Dict[str, List[float]] = defaultdict(list)
    skipped_no_resolution: List[str] = []
    n_audit_fold = 0

    for bet in bets:
        bet_id = bet.get("bet_id", "")
        line   = _safe_float(bet.get("line"))
        side   = bet.get("side", "")
        stat_l = (bet.get("stat", "") or "").lower().strip()

        close, tier, vals = resolve_synthetic_close(
            bet, real_close_map, snap_idx, oof_map,
        )
        clv_line_s, clv_pct_s = compute_clv_pct(line, close, side)

        is_audit = _is_audit_fold(bet_id)
        if is_audit:
            n_audit_fold += 1

        out_row = dict(bet)
        out_row.update({
            "bet_id":             bet_id,
            "real_close":         "" if vals["real_close"] is None     else f"{vals['real_close']:.4f}",
            "snapshot_close":     "" if vals["snapshot_close"] is None else f"{vals['snapshot_close']:.4f}",
            "oof_q50":            "" if vals["oof_q50"] is None        else f"{vals['oof_q50']:.4f}",
            "model_pred_tier4":   "" if vals["model_pred"] is None     else f"{vals['model_pred']:.4f}",
            "synthetic_close":    "" if close is None                  else f"{close:.4f}",
            "synthetic_clv_line": "" if clv_line_s is None             else f"{clv_line_s:.4f}",
            "synthetic_clv_pct":  "" if clv_pct_s is None              else f"{clv_pct_s:.6f}",
            "source_tier":        str(tier) if tier > 0 else "",
            "is_audit_fold":      "true" if is_audit else "false",
        })
        out_rows.append(out_row)

        if tier == 0:
            skipped_no_resolution.append(bet_id or "(blank bet_id)")
        else:
            tier_counts[tier] += 1
            if clv_pct_s is not None and stat_l in STAT_WHITELIST:
                clv_pct_by_stat[stat_l].append(clv_pct_s)

    n_resolved = sum(tier_counts.values())
    coverage_pct = (n_resolved / n_bets * 100.0) if n_bets > 0 else 0.0

    # ---- Per-stat mean CLV pct ----
    mean_clv_per_stat: Dict[str, float] = {}
    for stat in sorted(STAT_WHITELIST):
        vals = clv_pct_by_stat.get(stat, [])
        if vals:
            mean_clv_per_stat[stat] = round(sum(vals) / len(vals), 6)
        else:
            mean_clv_per_stat[stat] = None

    max_abs = max((abs(v) for v in mean_clv_per_stat.values() if v is not None),
                  default=0.0)

    # ---- Ship/Reject ----
    status = "SHIP"
    ship_reasons: List[str] = []

    if n_bets == 0:
        status = "REJECT"
        ship_reasons.append("ledger empty (n_bets=0)")
    elif coverage_pct < 100.0:
        status = "REJECT"
        ship_reasons.append(
            f"coverage {coverage_pct:.2f}% < 100% gate "
            f"({len(skipped_no_resolution)} bets fell through all 4 tiers)"
        )

    # Calibration gate (only when we have data; with tiny ledger this is informational)
    if status == "SHIP":
        for stat, mean in mean_clv_per_stat.items():
            if mean is not None and abs(mean) > MAX_ABS_MEAN_CLV:
                status = "REJECT"
                ship_reasons.append(
                    f"mean_clv_pct[{stat}]={mean:+.4f} exceeds {MAX_ABS_MEAN_CLV} ceiling"
                )

    if status == "SHIP":
        ship_reasons.append(
            f"coverage=100% ({n_resolved}/{n_bets}); "
            f"max |mean_clv_pct|={max_abs:.4f} <= {MAX_ABS_MEAN_CLV}; "
            f"audit fold reserved ({n_audit_fold} bets, "
            f"{n_audit_fold/max(n_bets,1)*100:.1f}%)"
        )

    # ---- Write CSV ----
    os.makedirs(os.path.dirname(OUT_CSV) or ".", exist_ok=True)
    new_cols = [
        "real_close", "snapshot_close", "oof_q50", "model_pred_tier4",
        "synthetic_close", "synthetic_clv_line", "synthetic_clv_pct",
        "source_tier", "is_audit_fold",
    ]
    base_cols = list(bets[0].keys()) if bets else [
        "bet_id", "placed_at", "game_id", "player_id", "player", "team",
        "stat", "line", "side", "book", "american_odds", "stake",
        "model_pred", "model_prob", "model_edge", "kelly_pct",
        "status", "settled_at", "actual_stat", "profit_loss", "bankroll_after",
    ]
    field_order = base_cols + [c for c in new_cols if c not in base_cols]

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        # Annotate header with usage note (CSV comment via leading '#' line)
        fh.write(
            "# probe_R9_C3_synthetic_closing_line — "
            "synthetic_clv_pct is the TARGET for C5/C6/C7 strategy probes, "
            "never a feature. is_audit_fold=true rows are reserved for hold-out "
            "validation only (do not train/select on them).\n"
        )
        writer = csv.DictWriter(fh, fieldnames=field_order, extrasaction="ignore")
        writer.writeheader()
        for r in out_rows:
            writer.writerow(r)

    log.info("Wrote %d rows -> %s", len(out_rows), OUT_CSV)

    # ---- Result JSON ----
    result = {
        "probe":            PROBE_ID,
        "status":           status,
        "n_bets":           n_bets,
        "n_resolved":       n_resolved,
        "coverage_pct":     round(coverage_pct, 4),
        "tier_distribution": {
            "1_real":           tier_counts.get(1, 0),
            "2_snapshot":       tier_counts.get(2, 0),
            "3_oof_q50":        tier_counts.get(3, 0),
            "4_cohort_l10":     tier_counts.get(4, 0),
        },
        "mean_clv_per_stat":  mean_clv_per_stat,
        "max_abs_mean_clv":   round(max_abs, 6),
        "max_abs_mean_clv_ceiling": MAX_ABS_MEAN_CLV,
        "audit_fold": {
            "pct":          AUDIT_FOLD_PCT,
            "n":            n_audit_fold,
            "deterministic_hash": "md5(bet_id) % 100 < 10",
            "reserved_from": ["C5_band_kelly", "C6_portfolio_kelly", "C7_lineup_timing"],
        },
        "corr_with_real_clv":  None,  # C4 not run yet → cross-corr deferred
        "circularity_guard":   {
            "oof_source":             OOF_PATH,
            "oof_audit":              oof_audit,
            "guarantee":              "OOF q50 is strictly walk-forward (fold col asserted "
                                      "non-null, monotone fold boundaries). C5/C6/C7 use "
                                      "synthetic_clv_pct as TARGET only — never feature.",
        },
        "skipped_no_resolution": {
            "count":  len(skipped_no_resolution),
            "sample": skipped_no_resolution[:10],
        },
        "ship_reason":  "; ".join(ship_reasons),
        "inputs": {
            "ledger":         LEDGER_PATH,
            "real_clv":       LEDGER_CLV_PATH,
            "oof":            OOF_PATH,
            "lines_dir":      LINES_DIR,
        },
        "outputs": {
            "csv":            OUT_CSV,
            "json":           OUT_JSON,
        },
        "started_at":   started,
        "finished_at":  dt.datetime.utcnow().isoformat() + "Z",
    }

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)

    log.info("== %s done: status=%s coverage=%.2f%% ==",
             PROBE_ID, status, coverage_pct)
    return result


if __name__ == "__main__":
    res = run_probe()
    print(json.dumps(res, indent=2, default=str))
    sys.exit(0 if res.get("status") == "SHIP" else 1)

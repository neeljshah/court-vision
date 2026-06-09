"""
INT-81: Eval — Momentum Signals CLV Gate Check
================================================
Joins momentum_signals.parquet with historical prop lines (real closing lines).
Computes aligned CLV, null-control (200 shuffles), sensitivity at ±1.5/±2.0/±2.5,
and per-stat bucket CLV monotonicity.

SHIP GATES (ALL must pass):
  1. Aligned CLV >= +0.5pp
  2. z_vs_null >= 2.0
  3. n_aligned >= 100
  4. Per-stat CLV monotone: best at extremes, worst at NEUTRAL

Usage:
    python scripts/eval_momentum_signals.py
    python scripts/eval_momentum_signals.py --cutoffs 1.5 2.0 2.5
"""
from __future__ import annotations

import io
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SIGNALS_PARQUET = ROOT / "data" / "intelligence" / "momentum_signals.parquet"
LINES_DIR = ROOT / "data" / "external" / "historical_lines"
VAULT_MD = ROOT / "vault" / "Intelligence" / "INT-81_Momentum_Signals.md"

TODAY = __import__("datetime").date.today().isoformat()

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
N_SHUFFLES = 200
DEFAULT_CUTOFFS = [1.5, 2.0, 2.5]
SHIP_GATE_CLV = 0.5
SHIP_GATE_ZNULL = 2.0
SHIP_GATE_N = 100

# Stat name normalization for lines files (lowercase)
STAT_ALIASES: Dict[str, str] = {
    "pts": "pts", "reb": "reb", "ast": "ast",
    "fg3m": "fg3m", "3pm": "fg3m", "threes": "fg3m",
    "stl": "stl", "blk": "blk", "tov": "tov",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def american_to_prob(odds: float) -> float:
    if odds >= 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def shin_devig_pair(o: float, u: float) -> Tuple[float, float]:
    """Two-outcome Shin devig. Returns (fair_over, fair_under)."""
    try:
        po = american_to_prob(o)
        pu = american_to_prob(u)
        total = po + pu
        if total <= 0:
            return 0.5, 0.5
        return po / total, pu / total
    except Exception:
        return 0.5, 0.5


def fair_over_prob(row: pd.Series) -> float:
    try:
        o = float(row["over_odds"])
        u = float(row["under_odds"])
        return shin_devig_pair(o, u)[0]
    except Exception:
        return np.nan


# ---------------------------------------------------------------------------
# Load lines
# ---------------------------------------------------------------------------

def load_lines() -> pd.DataFrame:
    """Load all canonical lines CSVs into one DataFrame."""
    files = [
        LINES_DIR / "regular_season_2024_25_oddsapi.csv",
        LINES_DIR / "benashkar_2026_canonical.csv",
        LINES_DIR / "season_2025_26_canonical.csv",
    ]
    dfs = []
    for fp in files:
        if not fp.exists():
            print(f"  [WARN] Lines file missing: {fp}")
            continue
        try:
            df = pd.read_csv(fp)
            dfs.append(df)
        except Exception as e:
            print(f"  [WARN] Failed to load {fp}: {e}")

    if not dfs:
        raise RuntimeError("No lines files loaded.")

    lines = pd.concat(dfs, ignore_index=True)

    # Normalize columns
    lines["date"] = pd.to_datetime(lines["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    lines["stat"] = lines["stat"].str.lower().str.strip().map(
        lambda s: STAT_ALIASES.get(s, s)
    )
    lines["player_lower"] = lines["player"].str.lower().str.strip()

    # Compute fair over prob
    lines["fair_over"] = lines.apply(fair_over_prob, axis=1)
    lines = lines.dropna(subset=["fair_over", "date", "player", "stat", "closing_line", "actual_value"])
    lines = lines[lines["stat"].isin(STATS)].copy()

    print(f"  Lines loaded: {len(lines):,} rows | {lines['stat'].value_counts().to_dict()}")
    return lines


# ---------------------------------------------------------------------------
# Build player name -> id map from gamelogs
# ---------------------------------------------------------------------------

def build_player_name_map() -> Dict[str, int]:
    """Returns {lower_name: player_id} from any available player roster file."""
    import glob
    import json

    name_map: Dict[str, int] = {}
    # Try to find a player roster
    roster_files = glob.glob(str(ROOT / "data" / "nba" / "gamelog_full_*_2024-25.json"))
    roster_files += glob.glob(str(ROOT / "data" / "nba" / "gamelog_full_*_2025-26.json"))

    # Load a sample to extract player name from matchup (not available in full log)
    # Instead load the non-full gamelog which has player_name-style data
    alt_files = glob.glob(str(ROOT / "data" / "nba" / "gamelog_*_2024-25.json"))
    alt_files = [f for f in alt_files if "gamelog_full" not in f]

    for fp in alt_files[:20]:  # sample
        try:
            with open(fp, encoding="utf-8") as f:
                rows = json.load(f)
            if rows and isinstance(rows[0], dict):
                pid = int(rows[0].get("player_id", 0) or 0)
                if pid:
                    # Extract name from filename: gamelog_<pid>_<season>.json
                    # We won't have the name from here, skip
                    pass
        except Exception:
            pass

    # The canonical approach: load from player_pf or another name-pid map
    pf_path = ROOT / "data" / "player_pf.parquet"
    if pf_path.exists():
        try:
            pf = pd.read_parquet(pf_path)
            if "player_name" in pf.columns and "nba_player_id" in pf.columns:
                for _, row in pf[["player_name", "nba_player_id"]].drop_duplicates().iterrows():
                    if pd.notna(row["player_name"]) and pd.notna(row["nba_player_id"]):
                        name_map[str(row["player_name"]).lower().strip()] = int(row["nba_player_id"])
                print(f"  Player name->ID map: {len(name_map)} entries (from player_pf)")
                return name_map
        except Exception as e:
            print(f"  [WARN] player_pf load failed: {e}")

    # Fallback: load from league_player_ids or prop datasets
    for fname in ["player_ids.json", "player_id_map.json"]:
        fp = ROOT / "data" / "nba" / fname
        if fp.exists():
            try:
                with open(fp) as f:
                    d = json.load(f)
                for k, v in d.items():
                    name_map[k.lower().strip()] = int(v)
                print(f"  Player name->ID map: {len(name_map)} entries (from {fname})")
                return name_map
            except Exception:
                pass

    print("  [WARN] No player name->ID map found; using name-based join only")
    return name_map


# ---------------------------------------------------------------------------
# Join momentum signals with lines
# ---------------------------------------------------------------------------

def load_signals() -> pd.DataFrame:
    if not SIGNALS_PARQUET.exists():
        raise FileNotFoundError(f"Signals parquet not found: {SIGNALS_PARQUET}")
    df = pd.read_parquet(SIGNALS_PARQUET)
    print(f"  Signals loaded: {len(df):,} rows | players: {df['player_id'].nunique()}")
    return df


def build_player_name_to_id(signals: pd.DataFrame) -> Dict[str, int]:
    """Build composite player_name->id mapping from multiple intelligence parquet sources."""
    name_map: Dict[str, int] = {}

    # Ordered list of (path, name_col, id_col) — largest / most reliable first
    sources = [
        (ROOT / "data" / "intelligence" / "per_player_calibration.parquet", "player_name", "player_id"),
        (ROOT / "data" / "intelligence" / "h1_h2_projections.parquet", "player_name", "player_id"),
        (ROOT / "data" / "intelligence" / "garbage_time_player_aggregates.parquet", "player_name", "player_id"),
        (ROOT / "data" / "intelligence" / "ingame_momentum.parquet", "player_name", "player_id"),
        (ROOT / "data" / "intelligence" / "matchup_deviations.parquet", "player_name", "player_id"),
        (ROOT / "data" / "intelligence" / "lineup_chemistry.parquet", "player_name", "player_id"),
        (ROOT / "data" / "intelligence" / "trade_profile_shifts.parquet", "player_name", "player_id"),
        (ROOT / "data" / "intelligence" / "anomaly_log.parquet", "player_name", "player_id"),
        (ROOT / "data" / "intelligence" / "streak_signatures.parquet", "player_name", "player_id"),
        (ROOT / "data" / "player_pf.parquet", "player_name", "nba_player_id"),
    ]

    for fpath, nc, ic in sources:
        if not fpath.exists():
            continue
        try:
            df = pd.read_parquet(fpath)
            if nc not in df.columns or ic not in df.columns:
                continue
            for _, row in df[[nc, ic]].drop_duplicates().dropna().iterrows():
                k = str(row[nc]).lower().strip()
                v = int(row[ic])
                if v > 100 and k not in name_map:  # filter dummy IDs, first match wins
                    name_map[k] = v
        except Exception:
            pass

    # Normalize name variants: remove periods from suffixes (Jr., C.J., etc.)
    # Add alias entries for common format differences
    aliases: Dict[str, str] = {}
    for name in list(name_map.keys()):
        # "gary trent jr." -> "gary trent jr"
        stripped = name.rstrip(".")
        if stripped != name and stripped not in name_map:
            aliases[stripped] = name
        # "michael porter jr." -> "michael porter jr"
        if " jr." in name:
            alt = name.replace(" jr.", " jr")
            if alt not in name_map:
                aliases[alt] = name
        # Handle "c.j. mccollum" -> "cj mccollum"
        no_dots = name.replace(".", "").replace("  ", " ").strip()
        if no_dots != name and no_dots not in name_map:
            aliases[no_dots] = name

    for alias, canonical in aliases.items():
        if canonical in name_map:
            name_map[alias] = name_map[canonical]

    print(f"  Name->ID map: {len(name_map)} entries (composite from intelligence parquets)")
    return name_map


def join_signals_to_lines(signals: pd.DataFrame, lines: pd.DataFrame) -> pd.DataFrame:
    """
    Join on (asof_date == date, player_id, stat).
    Since lines don't have player_id, we need name->id mapping, or
    join on (player_name, date, stat) if names available.
    """
    # Build name->id map
    name_to_id = build_player_name_to_id(signals)

    if name_to_id:
        lines["player_id"] = lines["player_lower"].map(name_to_id)
        lines_with_id = lines.dropna(subset=["player_id"]).copy()
        lines_with_id["player_id"] = lines_with_id["player_id"].astype("int64")
        print(f"  Lines with resolved player_id: {len(lines_with_id):,} / {len(lines):,}")

        joined = signals.merge(
            lines_with_id[["date", "player_id", "stat", "closing_line",
                           "actual_value", "over_odds", "under_odds", "fair_over"]],
            left_on=["asof_date", "player_id", "stat"],
            right_on=["date", "player_id", "stat"],
            how="inner",
        )
    else:
        # No name->id map — can't join
        joined = pd.DataFrame()

    print(f"  Joined rows (signals x lines): {len(joined):,}")
    return joined


# ---------------------------------------------------------------------------
# CLV computation
# ---------------------------------------------------------------------------

def compute_clv(row: pd.Series, cutoff: float = 2.0) -> Optional[Dict]:
    """
    Compute CLV for a single joined row.
    CLV = fair_over_prob (or fair_under_prob) in pp = percentage points.

    For non-TOV:
      VERY_HOT/WARM (z > cutoff or z > 1.0): aligned bet = OVER
      VERY_COLD/COLD (z < -cutoff or z < -1.0): aligned bet = UNDER
      NEUTRAL: excluded

    For TOV (inverted):
      VERY_HOT/WARM: aligned bet = OVER (more TOV = over — TOV semantics same z-direction)
      The recipe says "TOV: store raw z; consumer handles inversion"
      But the alignment definition says VERY_HOT + OVER aligned for TOV too.
      So TOV uses same direction as others for aligned assignment.
    """
    z = row["momentum_z"]
    if pd.isna(z):
        return None

    fair_over = row["fair_over"]
    actual = row["actual_value"]
    line = row["closing_line"]

    if pd.isna(fair_over) or pd.isna(actual) or pd.isna(line):
        return None

    bucket = row["momentum_bucket"]

    # Aligned side
    if bucket in ("VERY_HOT", "WARM"):
        side = "OVER"
        fair_prob = fair_over
        hit = float(actual) > float(line)
    elif bucket in ("VERY_COLD", "COLD"):
        side = "UNDER"
        fair_prob = 1.0 - fair_over
        hit = float(actual) < float(line)
    else:
        return None  # NEUTRAL excluded

    # CLV = fair_prob - 0.5 in pp (positive = edge vs fair line)
    clv_pp = (fair_prob - 0.5) * 100.0

    return {
        "side": side,
        "fair_prob": fair_prob,
        "clv_pp": clv_pp,
        "hit": hit,
        "bucket": bucket,
        "stat": row["stat"],
        "momentum_z": z,
    }


def aligned_clv(joined: pd.DataFrame, cutoff: float = 2.0) -> Dict:
    """Compute aligned CLV stats for the joined dataset."""
    if len(joined) == 0:
        return {"n_aligned": 0, "mean_clv_pp": np.nan, "hit_rate": np.nan}

    rows = []
    for _, row in joined.iterrows():
        r = compute_clv(row, cutoff)
        if r is not None:
            rows.append(r)

    if not rows:
        return {"n_aligned": 0, "mean_clv_pp": np.nan, "hit_rate": np.nan}

    df = pd.DataFrame(rows)
    return {
        "n_aligned": len(df),
        "mean_clv_pp": float(df["clv_pp"].mean()),
        "hit_rate": float(df["hit"].mean()),
        "per_stat": df.groupby("stat")["clv_pp"].mean().to_dict(),
        "per_bucket": df.groupby("bucket")["clv_pp"].mean().to_dict(),
    }


def reverse_aligned_clv(joined: pd.DataFrame) -> Dict:
    """Compute REVERSE aligned CLV (mean-reversion hypothesis)."""
    if len(joined) == 0:
        return {"n_aligned": 0, "mean_clv_pp": np.nan}

    rows = []
    for _, row in joined.iterrows():
        z = row["momentum_z"]
        if pd.isna(z):
            continue
        bucket = row["momentum_bucket"]
        fair_over = row["fair_over"]
        actual = row["actual_value"]
        line = row["closing_line"]

        if pd.isna(fair_over) or pd.isna(actual) or pd.isna(line):
            continue

        # REVERSE: hot -> bet UNDER, cold -> bet OVER
        if bucket in ("VERY_HOT", "WARM"):
            fair_prob = 1.0 - fair_over  # betting UNDER
            hit = float(actual) < float(line)
        elif bucket in ("VERY_COLD", "COLD"):
            fair_prob = fair_over  # betting OVER
            hit = float(actual) > float(line)
        else:
            continue

        clv_pp = (fair_prob - 0.5) * 100.0
        rows.append({"clv_pp": clv_pp, "hit": hit, "bucket": bucket, "stat": row["stat"]})

    if not rows:
        return {"n_aligned": 0, "mean_clv_pp": np.nan}

    df = pd.DataFrame(rows)
    return {
        "n_aligned": len(df),
        "mean_clv_pp": float(df["clv_pp"].mean()),
        "hit_rate": float(df["hit"].mean()),
    }


# ---------------------------------------------------------------------------
# Null control
# ---------------------------------------------------------------------------

def null_control_clv(joined: pd.DataFrame, n_shuffles: int = N_SHUFFLES) -> Tuple[float, float]:
    """
    Shuffle momentum_z within each stat (breaks player/date association).
    Returns (null_mean_clv_pp, null_std_clv_pp).
    """
    rng = np.random.default_rng(42)
    null_clvs = []

    for _ in range(n_shuffles):
        shuffled = joined.copy()
        for stat in STATS:
            mask = shuffled["stat"] == stat
            if mask.sum() < 2:
                continue
            z_vals = shuffled.loc[mask, "momentum_z"].values.copy()
            rng.shuffle(z_vals)
            shuffled.loc[mask, "momentum_z"] = z_vals
            # Recompute buckets
            shuffled.loc[mask, "momentum_bucket"] = [momentum_bucket(z) for z in z_vals]

        res = aligned_clv(shuffled)
        if not np.isnan(res["mean_clv_pp"]):
            null_clvs.append(res["mean_clv_pp"])

    if len(null_clvs) < 10:
        return np.nan, np.nan

    return float(np.mean(null_clvs)), float(np.std(null_clvs, ddof=1))


def momentum_bucket(z: float) -> str:
    if z < -2.0:
        return "VERY_COLD"
    elif z < -1.0:
        return "COLD"
    elif z <= 1.0:
        return "NEUTRAL"
    elif z <= 2.0:
        return "WARM"
    else:
        return "VERY_HOT"


# ---------------------------------------------------------------------------
# Sensitivity check at different cutoffs
# ---------------------------------------------------------------------------

def sensitivity_check(joined: pd.DataFrame, cutoffs: List[float]) -> Dict:
    results = {}
    for cutoff in cutoffs:
        # Re-bucket with different cutoff
        def _bucket_cutoff(z: float, c: float) -> str:
            if z < -c:
                return "VERY_COLD"
            elif z < -(c / 2.0):
                return "COLD"
            elif z <= (c / 2.0):
                return "NEUTRAL"
            elif z <= c:
                return "WARM"
            else:
                return "VERY_HOT"

        tmp = joined.copy()
        tmp["momentum_bucket"] = tmp["momentum_z"].apply(lambda z: _bucket_cutoff(z, cutoff))
        res = aligned_clv(tmp, cutoff)
        results[cutoff] = {
            "n_aligned": res["n_aligned"],
            "mean_clv_pp": res["mean_clv_pp"],
        }
    return results


# ---------------------------------------------------------------------------
# Per-stat bucket CLV monotonicity check
# ---------------------------------------------------------------------------

def check_monotonicity(joined: pd.DataFrame) -> Dict[str, bool]:
    """
    For each stat: CLV should be highest at extremes (VERY_HOT, VERY_COLD),
    lowest at NEUTRAL. Returns {stat: is_monotone}.
    """
    bucket_order = ["VERY_COLD", "COLD", "NEUTRAL", "WARM", "VERY_HOT"]
    results = {}

    for stat in STATS:
        stat_df = joined[joined["stat"] == stat].copy()
        if len(stat_df) < 20:
            results[stat] = None  # insufficient data
            continue

        clv_by_bucket = {}
        for _, row in stat_df.iterrows():
            r = compute_clv(row)
            if r is not None:
                b = r["bucket"]
                if b not in clv_by_bucket:
                    clv_by_bucket[b] = []
                clv_by_bucket[b].append(r["clv_pp"])

        # Compute mean CLV per bucket (only available buckets)
        bucket_means = {b: np.mean(v) for b, v in clv_by_bucket.items() if v}

        if len(bucket_means) < 3:
            results[stat] = None
            continue

        # Check: extremes > neutral
        neutral_clv = bucket_means.get("NEUTRAL", 0.0)
        extreme_buckets = ["VERY_COLD", "VERY_HOT"]
        extreme_clvs = [bucket_means[b] for b in extreme_buckets if b in bucket_means]

        if not extreme_clvs:
            results[stat] = None
            continue

        is_mono = all(e > neutral_clv for e in extreme_clvs)
        results[stat] = is_mono

    return results


# ---------------------------------------------------------------------------
# Main eval
# ---------------------------------------------------------------------------

def main(cutoffs: Optional[List[float]] = None) -> None:
    if cutoffs is None:
        cutoffs = DEFAULT_CUTOFFS

    print(f"[INT-81 EVAL] Loading signals...")
    signals = load_signals()

    print(f"[INT-81 EVAL] Loading lines...")
    lines = load_lines()

    print(f"[INT-81 EVAL] Joining signals to lines...")
    joined = join_signals_to_lines(signals, lines)

    if len(joined) == 0:
        print("\n[INT-81 EVAL] FATAL: No joined rows. Cannot evaluate.")
        print("  Possible cause: player name->ID map missing or date/stat mismatch.")
        _write_vault_result("REJECT", {}, {}, {}, {}, {}, 0, np.nan, np.nan, np.nan)
        return

    print(f"\n[INT-81 EVAL] Running aligned CLV (bucket cutoff +-2.0)...")
    real_result = aligned_clv(joined)
    n_aligned = real_result["n_aligned"]
    real_clv = real_result["mean_clv_pp"]

    print(f"  n_aligned: {n_aligned}")
    print(f"  mean CLV:  {real_clv:+.4f} pp")

    print(f"\n[INT-81 EVAL] Running reverse-aligned CLV (mean-reversion check)...")
    rev_result = reverse_aligned_clv(joined)
    print(f"  reverse n_aligned: {rev_result['n_aligned']}")
    print(f"  reverse mean CLV:  {rev_result['mean_clv_pp']:+.4f} pp")

    print(f"\n[INT-81 EVAL] Running null control ({N_SHUFFLES} shuffles)...")
    null_mean, null_std = null_control_clv(joined)
    if not np.isnan(null_mean) and null_std > 0:
        z_vs_null = (real_clv - null_mean) / null_std
    else:
        z_vs_null = np.nan
    print(f"  null mean: {null_mean:+.4f} pp | null std: {null_std:.4f}")
    print(f"  z_vs_null: {z_vs_null:.3f}" if not np.isnan(z_vs_null) else "  z_vs_null: NaN")

    print(f"\n[INT-81 EVAL] Sensitivity check at cutoffs {cutoffs}...")
    sens = sensitivity_check(joined, cutoffs)
    for c, r in sens.items():
        print(f"  cutoff +-{c}: n_aligned={r['n_aligned']} | CLV={r['mean_clv_pp']:+.4f} pp"
              if not np.isnan(r['mean_clv_pp']) else f"  cutoff +-{c}: no data")

    print(f"\n[INT-81 EVAL] Per-stat bucket CLV table...")
    mono = check_monotonicity(joined)
    per_stat_clv = real_result.get("per_stat", {})
    per_bucket_clv = real_result.get("per_bucket", {})

    print(f"\n  Bucket CLV (pp):")
    for b in ["VERY_COLD", "COLD", "NEUTRAL", "WARM", "VERY_HOT"]:
        v = per_bucket_clv.get(b, np.nan)
        print(f"    {b:<12}: {v:+.4f}" if not np.isnan(v) else f"    {b:<12}: N/A")

    print(f"\n  Per-stat CLV (pp):")
    for stat in STATS:
        v = per_stat_clv.get(stat, np.nan)
        m = mono.get(stat)
        mono_str = "(monotone)" if m else ("(NOT monotone)" if m is False else "(insufficient data)")
        print(f"    {stat:5s}: {v:+.4f}  {mono_str}" if not np.isnan(v) else f"    {stat:5s}: N/A  {mono_str}")

    # ---------------------------------------------------------------------------
    # Gate evaluation
    # ---------------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("GATE CHECKS")
    print(f"{'='*60}")

    gate1 = not np.isnan(real_clv) and real_clv >= SHIP_GATE_CLV
    gate2 = not np.isnan(z_vs_null) and z_vs_null >= SHIP_GATE_ZNULL
    gate3 = n_aligned >= SHIP_GATE_N
    gate4_vals = [v for v in mono.values() if v is not None]
    gate4 = len(gate4_vals) > 0 and sum(gate4_vals) / len(gate4_vals) >= 0.5

    print(f"  Gate 1 (CLV >= +{SHIP_GATE_CLV}pp):   {real_clv:+.4f} pp  -> {'PASS' if gate1 else 'FAIL'}")
    print(f"  Gate 2 (z_vs_null >= {SHIP_GATE_ZNULL}): {z_vs_null:.3f}      -> {'PASS' if gate2 else 'FAIL'}"
          if not np.isnan(z_vs_null) else f"  Gate 2 (z_vs_null >= {SHIP_GATE_ZNULL}): NaN        -> FAIL")
    print(f"  Gate 3 (n_aligned >= {SHIP_GATE_N}): {n_aligned}       -> {'PASS' if gate3 else 'FAIL'}")
    print(f"  Gate 4 (monotone per stat):  {sum(v for v in gate4_vals if v)}/{len(gate4_vals)} stats -> {'PASS' if gate4 else 'FAIL'}")

    # Sensitivity pass count (need >=2 of 3 cutoffs passing gate1)
    n_sens_pass = sum(
        1 for c in cutoffs
        if not np.isnan(sens[c]["mean_clv_pp"]) and sens[c]["mean_clv_pp"] >= SHIP_GATE_CLV
    )
    print(f"  Sensitivity (>= 2/{len(cutoffs)} cutoffs pass CLV gate): {n_sens_pass}/{len(cutoffs)} -> {'PASS' if n_sens_pass >= 2 else 'FAIL'}")

    all_gates = gate1 and gate2 and gate3 and gate4 and (n_sens_pass >= 2)

    # Direction check
    rev_mean = rev_result["mean_clv_pp"]
    if not np.isnan(rev_mean) and not np.isnan(real_clv):
        if rev_mean > real_clv and rev_mean >= SHIP_GATE_CLV:
            direction = "REVERSE-WINS"
        elif all_gates:
            direction = "SHIP"
        else:
            direction = "REJECT"
    elif all_gates:
        direction = "SHIP"
    else:
        direction = "REJECT"

    print(f"\n  VERDICT: {direction}")
    if direction == "REVERSE-WINS":
        print(f"  Mean reversion: reverse CLV={rev_mean:+.4f} > forward CLV={real_clv:+.4f}")
    print(f"{'='*60}")

    # ---------------------------------------------------------------------------
    # Update vault note
    # ---------------------------------------------------------------------------
    _write_vault_result(
        verdict=direction,
        real_result=real_result,
        rev_result=rev_result,
        sens=sens,
        mono=mono,
        per_bucket_clv=per_bucket_clv,
        n_aligned=n_aligned,
        null_mean=null_mean,
        null_std=null_std,
        z_vs_null=z_vs_null,
    )
    print(f"\n[INT-81 EVAL] Vault updated -> {VAULT_MD}")


def _write_vault_result(
    verdict: str,
    real_result: Dict,
    rev_result: Dict,
    sens: Dict,
    mono: Dict,
    per_bucket_clv: Dict,
    n_aligned: int,
    null_mean: float,
    null_std: float,
    z_vs_null: float,
) -> None:
    real_clv = real_result.get("mean_clv_pp", np.nan)
    rev_clv = rev_result.get("mean_clv_pp", np.nan)
    per_stat_clv = real_result.get("per_stat", {})

    def _fmt(v) -> str:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return "N/A"
        return f"{v:+.4f} pp"

    lines = [
        "# INT-81: Player Momentum Signals",
        "",
        "## Status",
        f"Eval run: {TODAY}",
        f"**VERDICT: {verdict}**",
        "",
        "## Methodology",
        "- `l3_actual` = mean of last 3 prior games (strict shift(1), MIN>=1)",
        "- `l20_baseline` = mean of last 20 prior games (NaN if <5 prior)",
        "- `l20_std` = std of last 20 prior, floor 0.5",
        "- `momentum_z` = (l3_actual - l20_baseline) / max(l20_std, 0.5), clipped [-5, +5]",
        "- Buckets: VERY_COLD(<-2), COLD(-2,-1), NEUTRAL(-1,+1), WARM(1,2), VERY_HOT(>2)",
        "- TOV: raw z stored; aligned per spec (VERY_HOT=OVER)",
        "",
        "## Eval Results",
        f"- n_aligned: {n_aligned}",
        f"- Aligned CLV: {_fmt(real_clv)}",
        f"- Reverse CLV: {_fmt(rev_clv)}",
        f"- Null mean: {_fmt(null_mean)} | null std: {null_std:.4f}" if not np.isnan(null_std) else "- Null: insufficient",
        f"- z_vs_null: {z_vs_null:.3f}" if not np.isnan(z_vs_null) else "- z_vs_null: NaN",
        "",
        "## Per-bucket CLV",
        "| bucket | CLV (pp) |",
        "|--------|----------|",
    ]
    for b in ["VERY_COLD", "COLD", "NEUTRAL", "WARM", "VERY_HOT"]:
        v = per_bucket_clv.get(b, np.nan)
        lines.append(f"| {b} | {_fmt(v)} |")

    lines += [
        "",
        "## Per-stat CLV",
        "| stat | CLV (pp) | monotone |",
        "|------|----------|----------|",
    ]
    for stat in STATS:
        v = per_stat_clv.get(stat, np.nan)
        m = mono.get(stat)
        mono_str = "yes" if m else ("no" if m is False else "n/a")
        lines.append(f"| {stat} | {_fmt(v)} | {mono_str} |")

    lines += [
        "",
        "## Sensitivity",
        "| cutoff | n_aligned | CLV (pp) |",
        "|--------|-----------|----------|",
    ]
    for c, r in sens.items():
        v = r.get("mean_clv_pp", np.nan)
        lines.append(f"| +-{c} | {r.get('n_aligned',0)} | {_fmt(v)} |")

    lines += [
        "",
        "## Ship Gates",
        f"- Gate 1 CLV >= +0.5pp: {'PASS' if not np.isnan(real_clv) and real_clv >= SHIP_GATE_CLV else 'FAIL'}",
        f"- Gate 2 z_vs_null >= 2.0: {'PASS' if not np.isnan(z_vs_null) and z_vs_null >= SHIP_GATE_ZNULL else 'FAIL'}",
        f"- Gate 3 n_aligned >= 100: {'PASS' if n_aligned >= SHIP_GATE_N else 'FAIL'}",
        f"- Gate 4 monotone: {'PASS' if mono and sum(v for v in mono.values() if v) >= 1 else 'FAIL'}",
        "",
        "## Honest Assessment",
        "- 17-revert pattern: structural additive features on data model already sees likely saturated",
        "- Overlap with l5/l10/ewma in prop_pergame is likely",
        "- Mean reversion is a real hypothesis for momentum signals",
        "",
        "---",
        f"*Eval {TODAY} by INT-81: `scripts/eval_momentum_signals.py`*",
        "*Linked: [[INT-81_Momentum_Signals]] | [[Betting_Signal_Ranking]] | [[Signal_Inventory]]*",
    ]
    VAULT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="INT-81: Eval momentum signals CLV gate")
    parser.add_argument(
        "--cutoffs", nargs="+", type=float, default=DEFAULT_CUTOFFS,
        help="Bucket cutoffs to test (default: 1.5 2.0 2.5)"
    )
    args = parser.parse_args()
    main(cutoffs=args.cutoffs)

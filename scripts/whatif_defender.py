"""whatif_defender.py — user-facing CLI for the (offense, defender) matchup
adjustment.

This sits on top of ``src/prediction/defender_matchup_residual`` and is the
manual "during-game" tool: when the operator SEES the defender on TV (e.g.
during a timeout / dead ball), they ask:

    "What does the model do to Wemby's points if Hartenstein is on him?"

The script wraps the pure-lookup module with:

  * fuzzy player-name resolution ("wemby" → 1641705, "sga" → 1628983)
  * base projection sourced from the playoff-adjusted q50 cache by default
  * one-shot pretty-printed answer OR a sorted ``--vs-all`` table

Examples
--------
    python scripts/whatif_defender.py --player Wemby --defender Hartenstein --stat pts
    python scripts/whatif_defender.py --player Wemby --defender Holmgren --stat pts
    python scripts/whatif_defender.py --player SGA --defender Vassell --stat pts
    python scripts/whatif_defender.py --player Wemby --stat pts --vs-all
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Optional, Tuple, List

# Local imports — make the project root importable regardless of cwd.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.prediction.defender_matchup_residual import (  # noqa: E402
    apply_matchup_adjustment,
    load_matchup_table,
    load_series_avg_table,
)

# ── nicknames / aliases ──────────────────────────────────────────────────────
# Lowercase the keys; both stems and full nicknames go here.
_NAME_ALIASES = {
    "wemby":       "Victor Wembanyama",
    "wembanyama":  "Victor Wembanyama",
    "sga":         "Shai Gilgeous-Alexander",
    "shai":        "Shai Gilgeous-Alexander",
    "gilgeous":    "Shai Gilgeous-Alexander",
    "hartenstein": "Isaiah Hartenstein",
    "harten":      "Isaiah Hartenstein",
    "holmgren":    "Chet Holmgren",
    "chet":        "Chet Holmgren",
    "vassell":     "Devin Vassell",
    "castle":      "Stephon Castle",
    "fox":         "De'Aaron Fox",
    "jdub":        "Jalen Williams",
    "j-dub":       "Jalen Williams",
    "dort":        "Luguentz Dort",
    "lu dort":     "Luguentz Dort",
    "caruso":      "Alex Caruso",
    "jaylin":      "Jaylin Williams",
    "kornet":      "Luke Kornet",
    "harper":      "Dylan Harper",
    "mccain":      "Jared McCain",
    "wallace":     "Cason Wallace",
    "champagnie":  "Julian Champagnie",
    "keldon":      "Keldon Johnson",
    "joe":         "Isaiah Joe",
    "wiggins":     "Aaron Wiggins",
    "mitchell":    "Ajay Mitchell",
    "barnes":      "Harrison Barnes",
    "kenrich":     "Kenrich Williams",
    "topic":       "Nikola Topić",
    "topić":  "Nikola Topić",
    "olynyk":      "Kelly Olynyk",
    "plumlee":     "Mason Plumlee",
    "biyombo":     "Bismack Biyombo",
    "bryant":      "Carter Bryant",
}


# ── name → id resolution ─────────────────────────────────────────────────────

def _norm(s: str) -> str:
    return "".join(c for c in s.lower().strip() if c.isalnum() or c == " ").strip()


def _build_name_index(matchup_df, series_df) -> dict:
    """{normalised_name_or_token: player_id} drawn from both tables."""
    idx: dict = {}

    def _add(pid, name):
        try:
            pid_i = int(pid)
        except (TypeError, ValueError):
            return
        if not isinstance(name, str) or not name:
            return
        idx.setdefault(_norm(name), pid_i)
        # Also index last name + first name token.
        toks = _norm(name).split()
        for t in toks:
            idx.setdefault(t, pid_i)

    if matchup_df is not None:
        for _, r in matchup_df.iterrows():
            _add(r.get("off_player_id"), r.get("off_player_name"))
            _add(r.get("def_player_id"), r.get("def_player_name"))
    if series_df is not None:
        for _, r in series_df.iterrows():
            _add(r.get("player_id"), r.get("player_name"))

    # Apply alias overrides (point them at the canonical full-name row).
    for alias_key, canonical_full in _NAME_ALIASES.items():
        canon_norm = _norm(canonical_full)
        if canon_norm in idx:
            idx[alias_key] = idx[canon_norm]
            # also overwrite the bare alias key normalised form
            idx[_norm(alias_key)] = idx[canon_norm]

    return idx


def resolve_player(token: str, matchup_df, series_df) -> Tuple[Optional[int], Optional[str]]:
    """Best-effort player lookup. Accepts:
      * raw integer id ("1641705")
      * full name ("Victor Wembanyama")
      * nickname / stem ("wemby", "sga", "shai")
      * last name ("hartenstein")
    Returns (player_id, full_name) or (None, None).
    """
    if token is None:
        return None, None
    s = str(token).strip()
    # numeric id?
    if s.isdigit():
        pid_i = int(s)
        for df, name_col, id_col in (
            (series_df, "player_name", "player_id"),
            (matchup_df, "off_player_name", "off_player_id"),
            (matchup_df, "def_player_name", "def_player_id"),
        ):
            if df is None:
                continue
            hit = df[df[id_col] == pid_i]
            if not hit.empty:
                return pid_i, str(hit.iloc[0][name_col])
        return pid_i, None

    n = _norm(s)
    idx = _build_name_index(matchup_df, series_df)

    # exact / alias hit
    if n in idx:
        pid = idx[n]
    elif s.lower() in _NAME_ALIASES:
        # alias → canonical full → id
        canon = _NAME_ALIASES[s.lower()]
        pid = idx.get(_norm(canon))
    else:
        # substring fallback across the full normalised name space
        pid = None
        # prefer matches against the FULL normalised names (those have spaces)
        candidates = [(k, v) for k, v in idx.items() if " " in k]
        for full_norm, pid_v in candidates:
            if n in full_norm:
                pid = pid_v
                break
        if pid is None:
            # last-resort: any token that startswith
            for k, v in idx.items():
                if k.startswith(n) and len(n) >= 3:
                    pid = v
                    break
    if pid is None:
        return None, None
    # Recover the canonical full name.
    for df, name_col, id_col in (
        (series_df, "player_name", "player_id"),
        (matchup_df, "off_player_name", "off_player_id"),
        (matchup_df, "def_player_name", "def_player_id"),
    ):
        if df is None:
            continue
        hit = df[df[id_col] == pid]
        if not hit.empty:
            return pid, str(hit.iloc[0][name_col])
    return pid, None


# ── projection sources ──────────────────────────────────────────────────────

def _fresh_q50(player_id: int, stat: str) -> Optional[float]:
    """Pull today's q50 (playoff-adjusted if available) from the intel cache.

    Order:
      1. data/cache/intel_<latest>/playoff_adjusted_q50.csv (q50_playoff_adj)
      2. data/cache/intel_<latest>/slate_fresh_<date>.parquet (q50)
      3. wcf_player_series_avg.csv (per-game average) — last-resort baseline
    """
    try:
        import pandas as pd
    except Exception:
        return None
    cache_root = os.path.join(_ROOT, "data", "cache")
    if not os.path.isdir(cache_root):
        return None
    intel_dirs = sorted(
        [d for d in os.listdir(cache_root) if d.startswith("intel_")]
    )
    if not intel_dirs:
        return None
    latest = os.path.join(cache_root, intel_dirs[-1])

    adj_path = os.path.join(latest, "playoff_adjusted_q50.csv")
    if os.path.isfile(adj_path):
        try:
            df = pd.read_csv(adj_path)
            hit = df[(df["player_id"] == player_id) & (df["stat"] == stat.lower())]
            if not hit.empty:
                v = hit.iloc[0].get("q50_playoff_adj")
                if v is None or (isinstance(v, float) and (v != v)):
                    v = hit.iloc[0].get("q50")
                if v is not None:
                    return float(v)
        except Exception:
            pass

    for name in os.listdir(latest):
        if name.startswith("slate_fresh_") and name.endswith(".parquet"):
            try:
                df = pd.read_parquet(os.path.join(latest, name))
                cols = {c.lower(): c for c in df.columns}
                pid_col = cols.get("player_id")
                stat_col = cols.get("stat")
                q50_col = cols.get("q50") or cols.get("q50_playoff_adj")
                if pid_col and stat_col and q50_col:
                    hit = df[(df[pid_col] == player_id) &
                             (df[stat_col].str.lower() == stat.lower())]
                    if not hit.empty:
                        return float(hit.iloc[0][q50_col])
            except Exception:
                pass

    series_df = load_series_avg_table()
    stat_col_map = {
        "pts": "pts_pg", "reb": "reb_pg", "ast": "ast_pg",
        "fg3m": "fg3m_pg", "stl": "stl_pg", "blk": "blk_pg", "tov": "tov_pg",
    }
    col = stat_col_map.get(stat.lower())
    if series_df is not None and col is not None:
        hit = series_df[series_df["player_id"] == player_id]
        if not hit.empty:
            try:
                return float(hit.iloc[0][col])
            except Exception:
                return None
    return None


# ── output ──────────────────────────────────────────────────────────────────

def _format_pair_row(matchup_df, off_id: int, def_id: int) -> Optional[dict]:
    row = matchup_df[(matchup_df["off_player_id"] == off_id) &
                     (matchup_df["def_player_id"] == def_id)]
    if row.empty:
        return None
    r = row.iloc[0]
    return {
        "off_name": str(r["off_player_name"]),
        "def_name": str(r["def_player_name"]),
        "partial_poss": float(r["partial_poss"]),
        "pts_allowed": float(r["pts_allowed"]),
        "fg_pct": float(r["fg_pct_allowed"]),
        "fg3_pct": float(r["fg3_pct_allowed"]),
        "matchup_min": float(r["matchup_min"]),
        "games_matched": int(r["games_matched"]),
    }


def _print_one(player_name, defender_name, base, adjusted, reason, raw):
    pct = (adjusted - base) / base * 100.0 if base else 0.0
    mult_str = "n/a"
    if "mult=" in reason:
        try:
            mult_str = reason.split("mult=")[-1].rstrip(",")
            mult_str = mult_str.split(",")[0]
        except Exception:
            pass
    print(f"\n  {player_name}  vs  {defender_name}")
    print(f"  ----------------------------------------")
    print(f"  base projection      : {base:.3f}")
    print(f"  multiplier           : {mult_str}")
    print(f"  adjusted projection  : {adjusted:.3f}    ({pct:+.2f}%)")
    if raw is not None:
        print(f"  -- matchup raw --")
        print(f"    partial poss     : {raw['partial_poss']:.1f}")
        print(f"    pts allowed      : {raw['pts_allowed']:.1f}")
        print(f"    fg pct allowed   : {raw['fg_pct']*100:.1f}%")
        print(f"    3p pct allowed   : {raw['fg3_pct']*100:.1f}%")
        print(f"    matchup minutes  : {raw['matchup_min']:.1f}")
        print(f"    games matched    : {raw['games_matched']}")
    print(f"  reason               : {reason}\n")


# ── main ────────────────────────────────────────────────────────────────────

def main(argv=None):
    examples = (
        "examples:\n"
        "  python scripts/whatif_defender.py --player Wemby --defender Hartenstein --stat pts\n"
        "  python scripts/whatif_defender.py --player Wemby --defender Holmgren    --stat pts\n"
        "  python scripts/whatif_defender.py --player SGA   --defender Vassell     --stat pts\n"
        "  python scripts/whatif_defender.py --player Wemby --stat pts --vs-all\n"
    )
    p = argparse.ArgumentParser(
        prog="whatif_defender.py",
        description="What-if matchup adjustment for the live engine. "
                    "Looks up the (offensive, defender) pair in the WCF "
                    "matchup tape and applies the same Bayesian-shrunk "
                    "multiplier the live engine would use.",
        epilog=examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--player",   required=True,
                   help="offensive player - name, nickname, or NBA player_id")
    p.add_argument("--defender", required=False,
                   help="defender - name, nickname, or NBA player_id "
                        "(omit when using --vs-all)")
    p.add_argument("--stat", required=True,
                   choices=["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"],
                   help="stat key (live engine convention)")
    p.add_argument("--projection", type=float, default=None,
                   help="base projection (default: q50 from playoff_adjusted_q50.csv "
                        "for today's intel cache)")
    p.add_argument("--vs-all", action="store_true",
                   help="show the adjustment vs every plausible defender for the "
                        "offensive player; sorted by adjusted projection")

    args = p.parse_args(argv)

    matchup_df = load_matchup_table()
    series_df = load_series_avg_table()
    if matchup_df is None:
        print("ERROR: matchup CSV not found.")
        return 2
    if series_df is None:
        print("ERROR: series average CSV not found.")
        return 2

    off_id, off_name = resolve_player(args.player, matchup_df, series_df)
    if off_id is None:
        print(f"ERROR: could not resolve offensive player '{args.player}'.")
        return 2

    # Resolve base projection.
    base = args.projection
    if base is None:
        base = _fresh_q50(off_id, args.stat)
    if base is None:
        print(f"ERROR: no base projection available for {off_name} {args.stat}. "
              f"Pass --projection <value>.")
        return 2

    # ── vs-all path ──────────────────────────────────────────────────────────
    if args.vs_all:
        candidates = matchup_df[matchup_df["off_player_id"] == off_id]
        if candidates.empty:
            print(f"No defenders in matchup table for {off_name}.")
            return 0
        rows = []
        for _, r in candidates.iterrows():
            d_id = int(r["def_player_id"])
            d_name = str(r["def_player_name"])
            adjusted, reason = apply_matchup_adjustment(
                off_id, args.stat, base,
                defender_id=d_id, matchup_df=matchup_df, series_df=series_df,
            )
            mult = adjusted / base if base else float("nan")
            rows.append({
                "defender": d_name,
                "poss": float(r["partial_poss"]),
                "pts_allowed": float(r["pts_allowed"]),
                "mult": mult,
                "adjusted": adjusted,
                "reason": reason,
            })
        rows.sort(key=lambda x: x["adjusted"], reverse=True)
        print(f"\n  {off_name} -- {args.stat.upper()} vs every defender in WCF tape")
        print(f"  base projection: {base:.3f}\n")
        hdr = f"  {'defender':<28} {'poss':>7} {'ptsA':>6} {'mult':>7} {'adj':>9}  status"
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for r in rows:
            status = "applied" if "applied" in r["reason"] else r["reason"].split(":", 1)[-1]
            print(f"  {r['defender']:<28} {r['poss']:>7.1f} {r['pts_allowed']:>6.1f} "
                  f"{r['mult']:>7.3f} {r['adjusted']:>9.3f}  {status}")
        print()
        return 0

    # ── single-defender path ─────────────────────────────────────────────────
    if not args.defender:
        print("ERROR: --defender is required unless --vs-all is set.")
        return 2

    def_id, def_name = resolve_player(args.defender, matchup_df, series_df)
    if def_id is None:
        print(f"ERROR: could not resolve defender '{args.defender}'.")
        return 2

    adjusted, reason = apply_matchup_adjustment(
        off_id, args.stat, base,
        defender_id=def_id, matchup_df=matchup_df, series_df=series_df,
    )
    raw = _format_pair_row(matchup_df, off_id, def_id)
    _print_one(off_name or args.player,
               def_name or args.defender,
               base, adjusted, reason, raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

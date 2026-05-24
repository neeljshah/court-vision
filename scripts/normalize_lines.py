"""normalize_lines.py — convert varied sportsbook export formats to canonical.

Cycle 42 (loop 5): the daily-ops `compare_to_lines.py` expects exactly one
CSV schema (`player,opp,venue,stat,line,over_odds,under_odds`). Real-world
sportsbook exports come in many shapes. This CLI sniffs the input columns
and emits the canonical format ready for `compare_to_lines.py` or the
historical backtest harness.

Adapters
--------
  dk       — DraftKings export (`Player,Team,Opponent,Market,Line,Over Odds,
             Under Odds`). `Market` ∈ {Points, Rebounds, Assists,
             3-Pointers Made, Steals, Blocks, Turnovers}.
  pp       — PrizePicks export (`Player,League,Opp,Stat Type,Line`).
             No odds column; we default to -110 / -110.
  generic  — any CSV. Pass `--player-col` / `--line-col` / `--stat-col` /
             optionally `--opp-col`, `--venue-col`, `--over-col`,
             `--under-col`. Stat names are mapped to canonical via the
             same alias table as the dk/pp adapters.

Run:
    python scripts/normalize_lines.py dk_export.csv -o out.csv
    python scripts/normalize_lines.py pp.csv --format pp -o out.csv
    python scripts/normalize_lines.py weird.csv --format generic \\
        --player-col Athlete --line-col OU --stat-col Prop
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from typing import Dict, List, Optional


# Canonical stat tokens used everywhere downstream (prop_pergame.STATS).
_CANONICAL_STATS = {"pts", "reb", "ast", "fg3m", "stl", "blk", "tov"}

# Generous alias table — covers DraftKings "Market" values, PrizePicks
# "Stat Type" values, FanDuel "Stat", and common abbreviations.
_STAT_ALIASES: Dict[str, str] = {
    # PTS
    "pts": "pts", "points": "pts", "player points": "pts", "pt": "pts",
    # REB
    "reb": "reb", "rebounds": "reb", "rebound": "reb",
    "player rebounds": "reb", "trb": "reb",
    # AST
    "ast": "ast", "assists": "ast", "assist": "ast",
    "player assists": "ast",
    # FG3M
    "fg3m": "fg3m", "3-pointers made": "fg3m", "3 pointers made": "fg3m",
    "3pm": "fg3m", "threes made": "fg3m", "three pointers made": "fg3m",
    "3pt made": "fg3m", "made threes": "fg3m",
    # STL
    "stl": "stl", "steals": "stl", "steal": "stl",
    # BLK
    "blk": "blk", "blocks": "blk", "block": "blk",
    "blocked shots": "blk",
    # TOV
    "tov": "tov", "turnovers": "tov", "turnover": "tov", "to": "tov",
}


_CANONICAL_HEADER = ["player", "opp", "venue", "stat",
                     "line", "over_odds", "under_odds"]


def _norm(s: str) -> str:
    return str(s or "").strip().lower()


def _map_stat(raw: str) -> Optional[str]:
    """Return canonical stat token, or None if unknown."""
    if raw is None:
        return None
    key = _norm(raw)
    if key in _CANONICAL_STATS:
        return key
    return _STAT_ALIASES.get(key)


def _detect_format(headers: List[str]) -> str:
    """Sniff which adapter matches the CSV columns."""
    hs = {_norm(h) for h in headers}
    # DraftKings: Player, Team, Opponent, Market, Line, Over Odds, Under Odds
    if {"player", "opponent", "market", "line"}.issubset(hs):
        return "dk"
    # PrizePicks: Player, League, Opp, Stat Type, Line  (no odds)
    if {"player", "stat type", "line"}.issubset(hs) and "opp" in hs:
        return "pp"
    # Generic fallback — caller must use --format generic explicitly so
    # we don't silently mis-map an unrecognised file.
    raise ValueError(
        "could not auto-detect sportsbook format. Pass --format "
        "{dk|pp|generic} explicitly. Saw headers: " + ", ".join(headers)
    )


def _parse_odds(raw, default: int = -110) -> int:
    if raw is None or str(raw).strip() == "":
        return default
    s = str(raw).strip().replace("+", "")
    try:
        return int(float(s))
    except ValueError:
        return default


def _venue_from_team_opp(team: str, opp: str) -> str:
    """Best-effort venue inference. Most books export OPPONENT only and use
    '@OPP' to mark away games (the team-line is the player's team). We don't
    have that signal universally, so default 'home' unless an explicit
    venue column is present in the generic adapter."""
    o = (opp or "").strip()
    if o.startswith("@"):
        return "away"
    return "home"


def _clean_opp(opp: str) -> str:
    return (opp or "").strip().lstrip("@").upper()


# ---------- adapters ----------

def _convert_dk(rows: List[dict]) -> List[dict]:
    out = []
    for r in rows:
        rl = {_norm(k): v for k, v in r.items()}
        stat = _map_stat(rl.get("market", ""))
        if stat is None:
            raise ValueError(
                f"DraftKings: unknown Market value {rl.get('market')!r}. "
                "Add it to _STAT_ALIASES if it should be supported."
            )
        opp = _clean_opp(rl.get("opponent", ""))
        venue = _venue_from_team_opp(rl.get("team", ""), rl.get("opponent", ""))
        out.append({
            "player":     (rl.get("player") or "").strip(),
            "opp":        opp,
            "venue":      venue,
            "stat":       stat,
            "line":       (rl.get("line") or "").strip(),
            "over_odds":  _parse_odds(rl.get("over odds")),
            "under_odds": _parse_odds(rl.get("under odds")),
        })
    return out


def _convert_pp(rows: List[dict]) -> List[dict]:
    out = []
    for r in rows:
        rl = {_norm(k): v for k, v in r.items()}
        stat = _map_stat(rl.get("stat type", ""))
        if stat is None:
            raise ValueError(
                f"PrizePicks: unknown Stat Type {rl.get('stat type')!r}. "
                "Add it to _STAT_ALIASES if it should be supported."
            )
        opp = _clean_opp(rl.get("opp", ""))
        venue = _venue_from_team_opp(rl.get("team", ""), rl.get("opp", ""))
        out.append({
            "player":     (rl.get("player") or "").strip(),
            "opp":        opp,
            "venue":      venue,
            "stat":       stat,
            "line":       (rl.get("line") or "").strip(),
            "over_odds":  -110,  # PrizePicks is pick'em
            "under_odds": -110,
        })
    return out


def _convert_generic(rows: List[dict], args) -> List[dict]:
    """Caller supplies the column names via --player-col, --line-col, etc."""
    out = []
    for r in rows:
        rl = {_norm(k): v for k, v in r.items()}
        stat_raw = rl.get(_norm(args.stat_col), "")
        stat = _map_stat(stat_raw)
        if stat is None:
            raise ValueError(
                f"generic: unknown stat {stat_raw!r} from column "
                f"{args.stat_col!r}. Add it to _STAT_ALIASES if it should "
                "be supported."
            )
        opp = _clean_opp(rl.get(_norm(args.opp_col), "") if args.opp_col else "")
        venue_raw = (rl.get(_norm(args.venue_col), "") if args.venue_col else "")
        venue = (venue_raw or "home").strip().lower()
        if not venue.startswith(("h", "a")):
            venue = "home"
        out.append({
            "player":     (rl.get(_norm(args.player_col)) or "").strip(),
            "opp":        opp,
            "venue":      venue,
            "stat":       stat,
            "line":       (rl.get(_norm(args.line_col)) or "").strip(),
            "over_odds":  _parse_odds(
                rl.get(_norm(args.over_col)) if args.over_col else None
            ),
            "under_odds": _parse_odds(
                rl.get(_norm(args.under_col)) if args.under_col else None
            ),
        })
    return out


_ADAPTERS = {"dk": _convert_dk, "pp": _convert_pp}


def normalize(input_csv: str, fmt: str = "auto", args=None) -> List[dict]:
    """Read `input_csv`, return list of canonical-schema dicts.

    Tests import this directly. CLI is a thin wrapper around it.
    """
    with open(input_csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return []
    if fmt == "auto":
        fmt = _detect_format(list(rows[0].keys()))
    if fmt == "generic":
        if args is None or not args.player_col or not args.line_col \
                or not args.stat_col:
            raise ValueError(
                "generic adapter requires --player-col, --line-col, "
                "and --stat-col"
            )
        return _convert_generic(rows, args)
    if fmt not in _ADAPTERS:
        raise ValueError(f"unknown format {fmt!r}; expected dk|pp|generic")
    return _ADAPTERS[fmt](rows)


def write_canonical(out_path: str, rows: List[dict]) -> None:
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_CANONICAL_HEADER)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in _CANONICAL_HEADER})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_csv", help="Sportsbook export CSV")
    ap.add_argument("--format", choices=["auto", "dk", "pp", "generic"],
                    default="auto")
    ap.add_argument("-o", "--output", required=True,
                    help="Output CSV in canonical schema")
    # Generic adapter knobs (ignored for dk/pp).
    ap.add_argument("--player-col", default=None)
    ap.add_argument("--line-col",   default=None)
    ap.add_argument("--stat-col",   default=None)
    ap.add_argument("--opp-col",    default=None)
    ap.add_argument("--venue-col",  default=None)
    ap.add_argument("--over-col",   default=None)
    ap.add_argument("--under-col",  default=None)
    args = ap.parse_args()

    if not os.path.exists(args.input_csv):
        print(f"[fail] not found: {args.input_csv}"); sys.exit(1)

    try:
        out_rows = normalize(args.input_csv, args.format, args=args)
    except ValueError as e:
        print(f"[fail] {e}"); sys.exit(2)

    if not out_rows:
        print("[fail] empty input CSV"); sys.exit(1)

    write_canonical(args.output, out_rows)
    print(f"[done] normalized {len(out_rows)} rows -> {args.output}")


if __name__ == "__main__":
    main()

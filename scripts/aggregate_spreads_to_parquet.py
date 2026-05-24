"""aggregate_spreads_to_parquet.py — cycle 91c (loop 5).

Consolidate ESPN scoreboard JSON caches written by
`fetch_pregame_spreads_2025_26.py` into a single tidy parquet:

    data/pregame_spreads.parquet
        game_date     str  YYYY-MM-DD
        home_team     str  NBA 3-letter abbreviation (e.g. BOS)
        away_team     str  NBA 3-letter abbreviation (e.g. NYK)
        home_spread   float  signed line at home perspective
                              (negative = home favoured by |home_spread| pts)
        total         float  posted O/U total (NaN when missing)
        source        str  "espn"
        fetched_at    str  ISO timestamp parquet was built

ESPN's `competitions[0].odds[0]` block carries:
  - "details"  e.g. "LAL -4.5", "BOS -7", "EVEN"
  - "spread"   float (some payloads, sign convention is favourite-relative)
  - "overUnder" float
  - "homeTeamOdds" / "awayTeamOdds" each with {"favorite": bool}

We derive `home_spread` rigorously:
  1. If `details == "EVEN"` (or "PK") -> home_spread = 0.0.
  2. Else parse "<TRICODE> <signed_number>".
  3. Map TRICODE to home or away via the competition's team list.
  4. Sign: favoured team's line is negative; flip when the favoured team is the
     AWAY side (so home_spread = -spread when home is favoured, +|spread| when
     away is favoured).

If parsing fails for any reason that row is skipped (warned once per date).
The aggregator is best-effort: a broken date's cache never blocks the rest.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

_CACHE_DIR  = os.path.join(PROJECT_DIR, "data", "cache", "spreads")
_OUT_PATH   = os.path.join(PROJECT_DIR, "data", "pregame_spreads.parquet")

# ESPN occasionally exposes team-name forms ("Lakers") or display name. We
# always prefer the competitor's `team.abbreviation` (NBA 3-letter code), so
# no mapping table needed for the common path.
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


def parse_odds_detail(details: str, home_abbr: str, away_abbr: str
                      ) -> Optional[float]:
    """Convert ESPN 'details' string into a signed home_spread.

    Returns None when the string can't be parsed.
    """
    if not details:
        return None
    s = details.strip().upper()
    if s in {"EVEN", "PK", "PICK", "PICK 'EM"}:
        return 0.0
    parts = s.split()
    if not parts:
        return None
    tri = parts[0]
    # Spread is typically the first numeric token after the team code.
    num_match = _NUM_RE.search(s[len(tri):])
    if not num_match:
        return None
    mag = abs(float(num_match.group()))
    if tri == home_abbr.upper():
        return -mag
    if tri == away_abbr.upper():
        return mag
    return None


def _pick_best_odds_item(odds_list: list) -> Optional[dict]:
    """Choose the best odds entry from a multi-provider list.

    Preference: ESPN BET (provider id 58) -> first entry with details.
    """
    if not odds_list:
        return None
    espn_bet = [o for o in odds_list
                 if str(((o.get("provider") or {}).get("id"))) == "58"]
    if espn_bet:
        return espn_bet[0]
    for o in odds_list:
        if (o.get("details") or "").strip():
            return o
    return odds_list[0]


def _home_spread_from_team_odds(item: dict) -> Optional[float]:
    """Fallback: derive home_spread from homeTeamOdds.favorite + spread value.

    The core API exposes `spread` (favourite-relative magnitude) and
    `homeTeamOdds.favorite` / `awayTeamOdds.favorite` booleans. When the
    `details` string fails to parse this is the rigorous backup.
    """
    sp = _safe_float(item.get("spread"))
    if sp is None:
        return None
    mag = abs(sp)
    home_odds = item.get("homeTeamOdds") or {}
    away_odds = item.get("awayTeamOdds") or {}
    if bool(home_odds.get("favorite")):
        return -mag
    if bool(away_odds.get("favorite")):
        return mag
    # No favourite flagged AND spread is 0 -> pick'em.
    if mag == 0.0:
        return 0.0
    return None


def extract_game(event: dict) -> Optional[dict]:
    """Pull one tidy row out of an ESPN scoreboard `event`. Returns None on miss."""
    try:
        comps = event.get("competitions") or []
        if not comps:
            return None
        comp = comps[0]
        teams = comp.get("competitors") or []
        if len(teams) < 2:
            return None
        home_abbr = away_abbr = None
        for t in teams:
            abbr = ((t.get("team") or {}).get("abbreviation") or "").upper()
            ha = (t.get("homeAway") or "").lower()
            if ha == "home":
                home_abbr = abbr
            elif ha == "away":
                away_abbr = abbr
        if not home_abbr or not away_abbr:
            return None

        date_raw = (event.get("date") or comp.get("date") or "")[:10]
        # ESPN gives ISO like "2025-11-05T00:30Z" — first 10 chars = YYYY-MM-DD.

        odds_list = comp.get("odds") or []
        item = _pick_best_odds_item(odds_list)
        if item is None:
            return None
        details = (item.get("details") or "").strip()
        total   = _safe_float(item.get("overUnder"))

        home_spread = parse_odds_detail(details, home_abbr, away_abbr)
        if home_spread is None:
            # Fall back to the structured spread + favorite flag.
            home_spread = _home_spread_from_team_odds(item)
        if home_spread is None:
            return None
        return {
            "game_date":   date_raw,
            "home_team":   home_abbr,
            "away_team":   away_abbr,
            "home_spread": float(home_spread),
            "total":       total,
        }
    except Exception:
        return None


def aggregate(cache_dir: str = _CACHE_DIR) -> List[dict]:
    """Walk every cached date file, parse each event, return list of row dicts."""
    rows: List[dict] = []
    if not os.path.isdir(cache_dir):
        return rows
    seen: set = set()  # (game_date, home, away) dedup
    paths = sorted(glob.glob(os.path.join(cache_dir, "*.json")))
    for p in paths:
        try:
            payload = json.load(open(p, encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"  [warn] {os.path.basename(p)}: {e}")
            continue
        events = payload.get("events") or []
        for ev in events:
            row = extract_game(ev)
            if row is None:
                continue
            key = (row["game_date"], row["home_team"], row["away_team"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def write_parquet(rows: List[dict], out_path: str = _OUT_PATH) -> str:
    """Write tidy parquet (best-effort: falls back to CSV if pyarrow missing)."""
    import pandas as pd  # noqa: PLC0415
    if not rows:
        print("[aggregate_spreads] no rows parsed — nothing to write")
        return out_path
    df = pd.DataFrame(rows)
    df["source"] = "espn"
    df["fetched_at"] = datetime.utcnow().isoformat()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    try:
        df.to_parquet(out_path, index=False)
    except Exception as e:
        csv_path = out_path.replace(".parquet", ".csv")
        print(f"  [warn] parquet write failed ({e}); falling back to {csv_path}")
        df.to_csv(csv_path, index=False)
        return csv_path
    return out_path


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default=_CACHE_DIR)
    ap.add_argument("--out", default=_OUT_PATH)
    args = ap.parse_args(argv)

    rows = aggregate(args.cache_dir)
    path = write_parquet(rows, args.out)
    print(f"[aggregate_spreads] wrote {len(rows)} rows -> "
          f"{os.path.relpath(path, PROJECT_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

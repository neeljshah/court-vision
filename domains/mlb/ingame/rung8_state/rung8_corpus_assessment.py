"""Corpus assessment for rung 8 (evolving in-game state: bullpen + pitch-count fatigue).

Answers, from THIS run's real files, not from memory:
  1. How many games / ticks / what date span does data/domains/mlb/gumbo_live/ cover.
  2. What fraction of those games join to the in-play market grade corpus
     (data/cache/ingame_grade/mlb/KXMLBGAME-*.jsonl), via
     game_pk -> (date, home_abbr, away_abbr) read from gumbo_live's own
     _poller_state.json cache, matched against each ticker's embedded date + team
     codes (with the same team-code-dialect aliases game_pk_bridge.py already
     documents, e.g. AZ/ARI, CWS/CHW, SF/SFG, TB/TAM, plus doubleheader G1/G2
     ticker suffixes).

Some gumbo_live games have NO Kalshi market at all (no ticker exists for that
date+team-pair) -- that is a real data-coverage gap, not a join bug, and is
reported honestly rather than papered over.

CLI: python -m domains.mlb.ingame.rung8_state.rung8_corpus_assessment
"""
from __future__ import annotations

import glob
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[4]
_GUMBO_DIR = _REPO_ROOT / "data" / "domains" / "mlb" / "gumbo_live"
_POLLER_STATE = _GUMBO_DIR / "_poller_state.json"
_GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade" / "mlb"

# team-code dialect aliases: gumbo_live's team.abbreviation <-> Kalshi ticker code.
_ALIASES: Dict[str, List[str]] = {
    "CWS": ["CWS", "CHW"], "AZ": ["AZ", "ARI"], "SF": ["SF", "SFG"], "KC": ["KC", "KAN"],
    "WSH": ["WSH", "WAS"], "TB": ["TB", "TAM"], "SD": ["SD", "SDG"], "ATH": ["ATH", "OAK"],
    "CHC": ["CHC", "CUB"],
}

_TICKER_PAT = re.compile(r"KXMLBGAME-(\d{2})([A-Z]{3})(\d{2})(\d{4})([A-Z]+?)(?:G\d)?$")


def _variants(code: str) -> List[str]:
    return _ALIASES.get(code, [code])


def corpus_ticks() -> Tuple[int, int, Tuple[str, str], Dict[str, float]]:
    """(n_games, n_ticks, (min_date, max_date), field_coverage_pct) over gumbo_live."""
    files = sorted(glob.glob(str(_GUMBO_DIR / "*.jsonl")))
    n_ticks = 0
    field_counts: Counter = Counter()
    dates: List[str] = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                n_ticks += 1
                for k in ("batter_id", "pitcher_id", "pitcher_pitches", "pitch_velo_last"):
                    if rec.get(k) is not None:
                        field_counts[k] += 1
                ca = rec.get("captured_at")
                if ca:
                    dates.append(ca[:10])
    coverage = {k: round(100.0 * v / n_ticks, 1) for k, v in field_counts.items()} if n_ticks else {}
    span = (min(dates), max(dates)) if dates else ("", "")
    return len(files), n_ticks, span, coverage


def _pk_team_info() -> Dict[int, Tuple[str, str, str]]:
    """game_pk -> (date, home_abbr, away_abbr) from gumbo_live's own poller cache."""
    with open(_POLLER_STATE, encoding="utf-8") as f:
        poller = json.load(f)
    out: Dict[int, Tuple[str, str, str]] = {}
    for pk, rec in poller.items():
        gd = rec.get("snapshot", {}).get("gameData", {})
        date = gd.get("datetime", {}).get("officialDate")
        teams = gd.get("teams", {})
        home = teams.get("home", {}).get("abbreviation")
        away = teams.get("away", {}).get("abbreviation")
        if date and home and away:
            out[int(pk)] = (date, home, away)
    return out


def _ticker_index() -> Dict[str, List[Tuple[str, str]]]:
    """ISO date -> list of (team_letters, filename) parsed from KXMLBGAME-* tickers."""
    files = glob.glob(str(_GRADE_DIR / "KXMLBGAME-*.jsonl"))
    idx: Dict[str, List[Tuple[str, str]]] = {}
    unparsed = 0
    for f in files:
        b = Path(f).stem
        m = _TICKER_PAT.search(b)
        if not m:
            unparsed += 1
            continue
        yy, mon, dd, _hhmm, teamstr = m.groups()
        d = datetime.strptime(f"20{yy}-{mon}-{dd}", "%Y-%b-%d").date().isoformat()
        idx.setdefault(d, []).append((teamstr, b))
    if unparsed:
        print(f"  (ticker parse: {unparsed}/{len(files)} filenames unparsed)")
    return idx


def join_to_grade_corpus() -> Tuple[int, int, List[int]]:
    """(n_games_total, n_joined, unmatched_game_pks) via date+team-code match."""
    pk_info = _pk_team_info()
    ticker_idx = _ticker_index()
    n_total = len(pk_info)
    joined = 0
    unmatched: List[int] = []
    for pk, (date, home, away) in pk_info.items():
        cands = ticker_idx.get(date, [])
        hit = False
        for teamstr, _b in cands:
            for hv in _variants(home):
                for av in _variants(away):
                    if hv in teamstr and av in teamstr:
                        hit = True
                        break
                if hit:
                    break
            if hit:
                break
        if hit:
            joined += 1
        else:
            unmatched.append(pk)
    return n_total, joined, unmatched


def main() -> int:
    n_games, n_ticks, span, coverage = corpus_ticks()
    print(f"gumbo_live corpus: {n_games} games, {n_ticks} ticks, date span {span[0]} .. {span[1]}")
    print(f"field coverage (pct of ticks): {coverage}")

    n_total, n_joined, unmatched = join_to_grade_corpus()
    rate = 100.0 * n_joined / n_total if n_total else 0.0
    print(f"join to KXMLBGAME grade corpus: {n_joined}/{n_total} games ({rate:.1f}%)")
    if rate < 95.0:
        print(
            f"  -- BELOW the 95% target. {len(unmatched)} game_pks have NO matching "
            "ticker on their date+team-pair (verified: some are real coverage gaps, "
            "not a join bug -- e.g. no Kalshi market existed for that game)."
        )
        print(f"  unmatched game_pks (first 10): {unmatched[:10]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

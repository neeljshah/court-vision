"""domains.basketball_nba.knowledge.validate_foul_trouble_spillover -- mechanism
#39 (C17): when a STARTER reaches 2 personal fouls in period 1, does the
Q1-remainder shot-attempt volume/efficiency of that team's OTHER on-court
players (excluding the fouled starter's own attempts) shift vs games where
no starter hit early foul trouble?

Premise check: foul TIMING (not just the season-final PF total in
player_boxscores) is required and DOES exist locally, in the raw per-quarter
PBP event feed `data/nba/pbp_<game_id>_p1.json` -- each foul event carries a
`(P<n>.T<n>)` personal-foul-count suffix and a `game_clock_sec` timestamp.
Coverage: 1,289 of 3,611 box-scored games (2023-24..2025-26) have a local
p1 file (35.7%) -- a real but partial local corpus, not season-complete;
every verdict below is scoped to that subset.

Leak audit: the trigger (a starter's PF reaching 2, at game_clock_sec<=
CUTOFF_SEC) and the outcome (teammates' shot attempts in the remainder of
period 1, game_clock_sec>CUTOFF_SEC, same game) are both read from the SAME
completed game's play-by-play after the fact -- a contemporaneous same-game
group comparison (foul-trouble-teammates vs no-foul-trouble-teammates),
identical leak posture to `validate_contact_park.py`'s shift check. This is
NOT a live in-game forecast.

Simplifications (ponytail, honesty-documented, not silently smoothed over):
- "2-3 fouls" is operationalized as "PF reaches 2" (the conventional bench
  trigger) -- the earliest qualifying moment, not a separate 3-foul test.
- The excluded/fouled player is matched pbp-last-name -> boxscore-full-name
  by accent-stripped suffix match; rare same-last-name-on-one-team
  collisions are not disambiguated (skipped defensively, see `_match_team`).
- "Usage/efficiency" is FIELD-GOAL attempts only (FTA/TOV excluded from the
  usage proxy) inside a FIXED post-cutoff window, not full team offense.

Run: python -m domains.basketball_nba.knowledge.validate_foul_trouble_spillover
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

from domains.basketball_nba.knowledge._data import LEDGER_PATH, load_player_boxscores
from scripts.platformkit.io_atomic import append_jsonl_atomic

PBP_DIR = Path(__file__).resolve().parents[3] / "data" / "nba"
CUTOFF_SEC = 360          # elapsed sec into period 1 (of 720) splitting trigger-window / outcome-window
FOUL_TRIGGER_PF = 2       # personal-foul count that marks "early foul trouble"
MIN_GROUP_N = 20
ALPHA = 0.01

_FOUL_RE = re.compile(r"\(P(\d+)\.T\d+\)")
_PTS_RE = re.compile(r"\((\d+) PTS\)")


def _norm(name: str) -> str:
    """Accent-strip + lowercase, for pbp last-name <-> boxscore full-name matching."""
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().strip()


def _is_fga(desc: str) -> Optional[int]:
    """Field-goal-attempt classifier from event_desc text. Returns points scored
    (0 for a miss), or None if this row is not an FGA (rebound/foul/turnover/
    free-throw/sub/etc)."""
    if "Free Throw" in desc:
        return None
    if desc.startswith("MISS "):
        return 0
    m = _PTS_RE.search(desc)
    if m and not desc.startswith(("SUB:", "Jump Ball", "Start of", "End of")):
        return int(m.group(1))
    return None


def _load_p1(game_id: str) -> Optional[List[Dict[str, Any]]]:
    path = PBP_DIR / ("pbp_%s_p1.json" % game_id)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        events = json.load(f)
    return sorted((e for e in events if e.get("period") == 1), key=lambda e: e["game_clock_sec"])


def game_rows(game_id: str, starters: pd.DataFrame) -> List[Dict[str, Any]]:
    """One row per (team, starter) for this game: trigger flag + teammates'
    Q1-remainder shot-attempt usage/efficiency, excluding that starter's own
    attempts."""
    events = _load_p1(game_id)
    if not events:
        return []
    trigger_sec: Dict[Tuple[str, str], int] = {}
    for e in events:
        m = _FOUL_RE.search(e["event_desc"])
        if not m or int(m.group(1)) != FOUL_TRIGGER_PF:
            continue
        key = (e["team_abbrev"], _norm(e["player_name"]))
        trigger_sec.setdefault(key, e["game_clock_sec"])
    remainder = [(e["team_abbrev"], _norm(e["player_name"]), pts)
                 for e in events if e["game_clock_sec"] > CUTOFF_SEC
                 for pts in [_is_fga(e["event_desc"])] if pts is not None]
    window_min = (720 - CUTOFF_SEC) / 60.0
    rows: List[Dict[str, Any]] = []
    seen_norms: Dict[str, int] = {}
    for _, srow in starters.iterrows():
        seen_norms[_norm(srow["player_name"])] = seen_norms.get(_norm(srow["player_name"]), 0) + 1
    for _, srow in starters.iterrows():
        team, full_norm = srow["team"], _norm(srow["player_name"])
        if seen_norms[full_norm] > 1:
            continue  # ambiguous same-normalized-name collision on this team -- skip defensively
        # pbp events carry the SHORT (last-)name; match by suffix against the boxscore full name
        t_sec = next((sec for (tm, short_norm), sec in trigger_sec.items()
                      if tm == team and (full_norm.endswith(short_norm) or full_norm == short_norm)), None)
        if t_sec is not None and t_sec > CUTOFF_SEC:
            continue  # trouble arrived after the fixed remainder window starts -- ambiguous, drop
        mate_pts = [pts for tm, short_norm, pts in remainder
                    if tm == team and not (full_norm.endswith(short_norm) or full_norm == short_norm)]
        rows.append({
            "game_id": game_id, "team": team, "starter": srow["player_name"],
            "trigger": t_sec is not None,
            "teammates_fga_rate": len(mate_pts) / window_min,
            "teammates_efficiency": (sum(mate_pts) / len(mate_pts)) if mate_pts else np.nan,
        })
    return rows


def build_dataset() -> pd.DataFrame:
    box = load_player_boxscores()
    starters_all = box[box["starter"]]
    available = {p.name[4:-8] for p in PBP_DIR.glob("pbp_*_p1.json")}  # strip 'pbp_' / '_p1.json'
    game_ids = [g for g in box["game_id"].unique() if g in available]
    dates = box.groupby("game_id")["date"].first()
    rows: List[Dict[str, Any]] = []
    for gid, starters in starters_all[starters_all["game_id"].isin(game_ids)].groupby("game_id"):
        rows.extend(game_rows(gid, starters))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = df["game_id"].map(dates)
    return df


def _verdict(p: float, effect: float, min_abs_effect: float) -> str:
    if p is None or effect is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def _compare(df: pd.DataFrame, metric: str, min_abs_effect: float, half: str, hyp: str) -> Dict[str, Any]:
    d = df.dropna(subset=[metric])
    trig, ctrl = d.loc[d["trigger"], metric], d.loc[~d["trigger"], metric]
    if len(trig) < MIN_GROUP_N or len(ctrl) < MIN_GROUP_N:
        return {"hypothesis": "%s__%s" % (hyp, half), "n": int(len(trig) + len(ctrl)), "effect": None,
                "p": None, "verdict": "NOT_TESTABLE",
                "note": "insufficient n after as-of foul-trigger join (%d trouble / %d control), half=%s"
                        % (len(trig), len(ctrl), half)}
    t, p = stats.ttest_ind(trig, ctrl, equal_var=False)
    eff = float(trig.mean() - ctrl.mean())
    return {"hypothesis": "%s__%s" % (hyp, half), "n": int(len(trig) + len(ctrl)), "effect": round(eff, 5),
            "p": float(p), "verdict": _verdict(p, eff, min_abs_effect),
            "note": "%s: foul-trouble-starter teammates (%.4f, n=%d) vs control teammates (%.4f, n=%d), half=%s"
                    % (metric, trig.mean(), len(trig), ctrl.mean(), len(ctrl), half)}


def _combine(rows: List[Dict[str, Any]], hyp: str) -> Dict[str, Any]:
    testable = [r for r in rows if r["verdict"] != "NOT_TESTABLE"]
    sig = [r for r in testable if r["p"] < ALPHA]
    if len(testable) < 2:
        verdict = "NOT_TESTABLE"
    elif len(sig) >= 2 and len({1 if r["effect"] > 0 else -1 for r in sig}) == 1:
        verdict = "CONFIRMED_LOCAL"
    elif len(sig) == 1:
        verdict = "PROVISIONAL"
    else:
        verdict = "NULL_LOCAL"
    return {"hypothesis": hyp + "__combined", "n": int(sum(r["n"] for r in rows)), "effect": None, "p": None,
            "verdict": verdict,
            "note": "split-half-by-date replication: %s"
                    % "; ".join("%s(p=%s,eff=%s)" % (r["hypothesis"], r["p"], r["effect"]) for r in rows)}


def run() -> List[Dict[str, Any]]:
    df = build_dataset()
    if df.empty:
        rows = [{"hypothesis": "foul_trouble_teammate_spillover", "n": 0, "effect": None, "p": None,
                 "verdict": "NOT_TESTABLE", "note": "no local pbp p1 games overlapped box-scored starters"}]
    else:
        mid = df["date"].median()
        h1, h2 = df[df["date"] <= mid], df[df["date"] > mid]
        rate_rows = [_compare(h1, "teammates_fga_rate", 0.15, "h1", "foul_trouble_usage_shift"),
                     _compare(h2, "teammates_fga_rate", 0.15, "h2", "foul_trouble_usage_shift")]
        eff_rows = [_compare(h1, "teammates_efficiency", 0.08, "h1", "foul_trouble_efficiency_shift"),
                    _compare(h2, "teammates_efficiency", 0.08, "h2", "foul_trouble_efficiency_shift")]
        rows = rate_rows + [_combine(rate_rows, "foul_trouble_usage_shift")] + \
            eff_rows + [_combine(eff_rows, "foul_trouble_efficiency_shift")]
    for r in rows:
        r["sport"] = "basketball_nba"
        r["corpus"] = "player_boxscores+pbp_p1_json (1289 games, split-half by date)"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-42s %-16s n=%-6s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: FGA text classifier + verdict thresholds."""
    assert _is_fga("MISS Russell 25' 3PT Pullup Jump Shot") == 0
    assert _is_fga("Davis 1' Dunk (2 PTS) (Russell 1 AST)") == 2
    assert _is_fga("Davis Free Throw 1 of 2 (3 PTS)") is None
    assert _is_fga("Davis S.FOUL (P1.T1) (K.Cutler)") is None
    assert _is_fga("SUB: Jackson FOR Murray") is None
    assert _norm("Jokić") == "jokic"
    assert _verdict(0.001, 0.5, 0.15) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.5, 0.15) == "NULL_LOCAL"
    assert _verdict(float("nan"), 0.5, 0.15) == "NOT_TESTABLE"
    print("self-check OK")

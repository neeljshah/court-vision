"""domains.soccer.build_wc_replay_corpus -- 2026 World Cup replay corpus builder.

Joins ESPN (soccer/fifa.world) event data to the captured Kalshi KXWCGAME venue history
(data/venue_history/kalshi/soccer_intl/, READ-ONLY) to produce a candle-level in-game
checkpoint corpus: data/cache/inplay_odds/soccer_checkpoints_wc2026.parquet.

MATCHING: (kickoff UTC date, {home_abbr, away_abbr}) unordered pair vs the KXWCGAME event
ticker's own embedded date+codes (domains.soccer.wc_ticker_map). ESPN's team.abbreviation
matches Kalshi's 3-letter codes directly for every WC team spot-checked; unmatched games are
counted and skipped, never guessed.

ALIGNMENT (honest, approximate): the Kalshi candle series carries the true wallclock ts;
"minute" = (candle_ts - kickoff_ts)/60 using ESPN's own kickoff wallclock (header competition
date). This is imprecise by ESPN's article-clock vs Kalshi's own clock (typically <1min) and
does not account for added/stoppage time reported separately from wallclock -- combined with
1-min candle spacing, treat minute as +/-2min. score_home/score_away are attached via
merge_asof(direction="backward") against a cumulative-goal timeline built from ESPN keyEvents
(uncapped minute, unlike ingest_soccer_states.build_states' 90-min-capped grid) -- so a candle
can NEVER see a goal that (by wallclock) hasn't happened yet. tie_prob is attached the same
way from the TIE market's own (asynchronous) candle series. outcome is Kalshi's own settled
"result" field (home/away/tie ticker, whichever settled "yes") -- the actual traded
settlement, cross-checked (not overridden) against ESPN's final score.

INVARIANTS: <=300 LOC; ASCII only; venue_history READ-ONLY; no src/kernel/api/intel edits;
local write only (data/cache/inplay_odds/); no $/edge claims (calibration/Brier only).

CLI: python -m domains.soccer.build_wc_replay_corpus --start 2026-06-11 --end 2026-07-08
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from domains.soccer.ingest_soccer_states import (
    _SUMMARY, _event_ids, _final_score, _get, _team_names, _team_sides,
)
from domains.soccer.wc_ticker_map import build_ticker_index, match_event_any

log = logging.getLogger(__name__)
_REPO = Path(__file__).resolve().parents[2]
_KALSHI_DIR = _REPO / "data" / "venue_history" / "kalshi" / "soccer_intl"
_OUT = _REPO / "data" / "cache" / "inplay_odds" / "soccer_checkpoints_wc2026.parquet"
_LEAGUE = "fifa.world"
_MIN_TS = -10 ** 12  # sentinel seed row, older than any real epoch second
# ESPN team.abbreviation -> Kalshi ticker country code, where they differ (verified
# against the 2026 KXWCGAME ticker set: HTISCO, IRINZL, ARGDZA, ...).
_KALSHI_CODE = {"HAI": "HTI", "IRN": "IRI", "ALG": "DZA"}


def _team_abbrevs(payload: dict) -> Tuple[str, str]:
    """(home_code, away_code) from header competitions, mapped onto Kalshi's country
    codes (_KALSHI_CODE covers the ESPN-vs-Kalshi mismatches), '' if missing."""
    comps = (payload.get("header") or {}).get("competitions") or [{}]
    h = a = ""
    for c in (comps[0].get("competitors") or []):
        abbr = ((c.get("team") or {}).get("abbreviation", "") or "").upper()
        abbr = _KALSHI_CODE.get(abbr, abbr)
        if c.get("homeAway") == "home":
            h = abbr
        elif c.get("homeAway") == "away":
            a = abbr
    return h, a


def _kickoff_dt(payload: dict) -> Optional[datetime]:
    """Kickoff wallclock (UTC) from header.competitions[0].date, or None."""
    comps = (payload.get("header") or {}).get("competitions") or [{}]
    raw = comps[0].get("date") if comps else None
    if not raw:
        return None
    try:
        return datetime.strptime(raw.replace("Z", "+0000"), "%Y-%m-%dT%H:%M%z")
    except ValueError:
        try:
            return datetime.strptime(raw.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            return None


def goal_events_raw(payload: dict, home_id: str) -> List[Tuple[float, bool]]:
    """[(minute_elapsed_UNCAPPED, is_home)] for scoringPlay keyEvents -- unlike
    ingest_soccer_states._goal_events this does NOT cap at 90 (stoppage/extra time
    goals keep their real clock minute, needed for wallclock alignment)."""
    out: List[Tuple[float, bool]] = []
    for ev in (payload.get("keyEvents") or []):
        if not ev.get("scoringPlay"):
            continue
        clk = (ev.get("clock") or {}).get("value")
        tid = str((ev.get("team") or {}).get("id", ""))
        if clk is None or not tid:
            continue
        out.append((float(clk) / 60.0, tid == home_id))
    return out


def _load_market(ticker: str) -> Optional[Dict[str, Any]]:
    p = _KALSHI_DIR / (ticker + ".jsonl")
    if not p.exists():
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            return json.loads(fh.readline())
    except (OSError, json.JSONDecodeError):
        return None


def _candle_df(doc: Dict[str, Any], value_col: str) -> pd.DataFrame:
    rows = [{"ts": int(pd.Timestamp(c["ts"]).timestamp()), value_col: float(c["prob"]),
            "traded": bool(c.get("traded", False))} for c in (doc.get("candles") or [])]
    df = pd.DataFrame(rows, columns=["ts", value_col, "traded"])
    return df.sort_values("ts").reset_index(drop=True)


def _goals_df(goals: List[Tuple[float, bool]], kickoff_ts: int) -> pd.DataFrame:
    """Cumulative (home_goals, away_goals) timeline, ts-indexed, leak-free-ready for
    merge_asof(direction='backward'): a candle can only see goals at/before its own ts."""
    by_ts: Dict[int, List[bool]] = {}
    for minute, is_home in goals:
        ts = kickoff_ts + int(round(minute * 60))
        by_ts.setdefault(ts, []).append(is_home)
    rows = [{"ts": _MIN_TS, "score_home": 0, "score_away": 0}]
    hg = ag = 0
    for ts in sorted(by_ts):
        for is_home in by_ts[ts]:
            hg += int(is_home)
            ag += int(not is_home)
        rows.append({"ts": ts, "score_home": hg, "score_away": ag})
    return pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)


def build_game_rows(event_ticker: str, home_code: str, away_code: str,
                    payload: dict, home_id: str, kickoff_ts: int,
                    hg_final: int, ag_final: int,
                    home_name: str = "", away_name: str = "") -> List[dict]:
    """One matched WC game -> checkpoint rows (home-win-market candle grid). [] if the
    home market has no candles or goal counts don't reconcile against the final score
    (never fabricate)."""
    goals = goal_events_raw(payload, home_id)
    if sum(1 for _, ih in goals if ih) != hg_final:
        return []
    if sum(1 for _, ih in goals if not ih) != ag_final:
        return []

    home_doc = _load_market("%s-%s" % (event_ticker, home_code))
    away_doc = _load_market("%s-%s" % (event_ticker, away_code))
    tie_doc = _load_market("%s-TIE" % event_ticker)
    if not home_doc or not home_doc.get("candles"):
        return []
    outcome = None
    for doc, label in ((home_doc, "home_win"), (away_doc, "away_win"), (tie_doc, "draw")):
        if doc and doc.get("result") == "yes":
            outcome = label
            break
    if outcome is None:
        return []  # unsettled/inconsistent -- never guess an outcome

    base = _candle_df(home_doc, "market_prob")
    if base.empty:
        return []
    goals_df = _goals_df(goals, kickoff_ts)
    merged = pd.merge_asof(base, goals_df, on="ts", direction="backward")
    if tie_doc and tie_doc.get("candles"):
        tie_df = _candle_df(tie_doc, "tie_prob")[["ts", "tie_prob"]]
        merged = pd.merge_asof(merged, tie_df, on="ts", direction="backward")
    else:
        merged["tie_prob"] = None

    game_date = datetime.fromtimestamp(kickoff_ts, tz=timezone.utc).strftime("%Y-%m-%d")
    # In-game corpus: keep kickoff-onward candles only (Kalshi captures days of
    # pregame candles -- ~97% of raw rows; post-whistle pre-settlement candles stay,
    # sliceable by minute). Pregame prices belong in a line-history corpus, not here.
    merged = merged[merged["ts"] >= kickoff_ts]
    rows = []
    for r in merged.itertuples(index=False):
        rows.append({
            "game_id": event_ticker, "game_date": game_date,
            "home_team": home_name, "away_team": away_name, "ts": int(r.ts),
            "minute": round((int(r.ts) - kickoff_ts) / 60.0, 2),
            "score_home": int(r.score_home), "score_away": int(r.score_away),
            "margin": int(r.score_home) - int(r.score_away),
            "market_ticker": "%s-%s" % (event_ticker, home_code),
            "market_prob": float(r.market_prob),
            "tie_prob": float(r.tie_prob) if pd.notna(r.tie_prob) else None,
            "traded": bool(r.traded), "outcome": outcome,
        })
    return rows


def build_corpus(start: date, end: date, getter=None) -> Tuple[pd.DataFrame, Dict[str, int]]:
    idx = build_ticker_index(_KALSHI_DIR)
    pairs = _event_ids(start, end, _LEAGUE, getter)
    all_rows: List[dict] = []
    matched = unmatched = dropped = 0
    for eid, _ds in pairs:
        payload = _get(_SUMMARY.format(l=_LEAGUE, e=eid), getter)
        if not payload:
            unmatched += 1
            continue
        home_id, _away_id = _team_sides(payload)
        home_name, away_name = _team_names(payload)
        home_code, away_code = _team_abbrevs(payload)
        kickoff = _kickoff_dt(payload)
        hg_final, ag_final = _final_score(payload)
        if not home_id or not home_code or not away_code or kickoff is None or hg_final is None:
            unmatched += 1
            continue
        event_ticker = match_event_any(kickoff.date(), home_code, away_code, idx)
        if not event_ticker:
            log.info("unmatched: %s vs %s (%s) kickoff=%s", home_name, away_name,
                     home_code + away_code, kickoff.date())
            unmatched += 1
            continue
        matched += 1
        rows = build_game_rows(event_ticker, home_code, away_code, payload, home_id,
                               int(kickoff.timestamp()), hg_final, ag_final,
                               home_name=home_name, away_name=away_name)
        if rows:
            all_rows.extend(rows)
        else:
            log.info("dropped (reconcile/candles/settle): %s (%s vs %s, final %s-%s)",
                     event_ticker, home_name, away_name, hg_final, ag_final)
            dropped += 1
        time.sleep(0.08)
    df = pd.DataFrame(all_rows) if all_rows else pd.DataFrame()
    stats = {"n_events": len(pairs), "matched": matched, "unmatched": unmatched,
             "dropped_reconcile": dropped, "n_games_in_corpus": int(df["game_id"].nunique())
             if not df.empty else 0, "n_rows": len(df)}
    return df, stats


def write_corpus(start: date, end: date, out: Optional[Path] = None, getter=None) -> Dict[str, int]:
    df, stats = build_corpus(start, end, getter)
    outp = out or _OUT
    outp.parent.mkdir(parents=True, exist_ok=True)
    if not df.empty:
        tmp = outp.with_suffix(outp.suffix + ".tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(outp)  # atomic
    log.info("wc replay corpus: %s -> %s", stats, outp)
    return stats


def _main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Build the 2026 World Cup replay checkpoint corpus.")
    ap.add_argument("--start", default="2026-06-11")
    ap.add_argument("--end", default="2026-07-08")
    args = ap.parse_args(argv)
    s = date.fromisoformat(args.start)
    e = date.fromisoformat(args.end)
    stats = write_corpus(s, e)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

__all__ = ["build_corpus", "write_corpus", "build_game_rows", "goal_events_raw"]

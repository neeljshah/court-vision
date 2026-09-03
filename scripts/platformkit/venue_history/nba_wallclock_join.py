"""Join cached ESPN wall-clock game states to Kalshi NBA candles without future reads.

Writes the int64 checkpoint schema under ``data/cache/inplay_odds`` when called as a
CLI. This is calibration substrate only; it is not a model.
"""
from __future__ import annotations

import glob
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from domains.basketball_nba.espn_nba_bridge import _norm_abbr
from domains.basketball_nba.ingest_pbp_states import _clock_seconds
from scripts.platformkit.eval_gate.asof_join import asof_join_state
from scripts.platformkit.ingame.nba_outcome_resolver import parse_nba_ticker

log = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parents[3]
KALSHI_NBA = _REPO / "data" / "venue_history" / "kalshi" / "nba"
RAW_CACHE = _REPO / "data" / "cache" / "nba_pbp_wallclock_raw"
OUT_PATH = _REPO / "data" / "cache" / "inplay_odds" / "nba_checkpoints_2025_26_playoffs.parquet"

_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={date}"
_SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={eid}"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0"
_SLEEP_S = 1.0  # politeness: 1 req/s
_JOIN_COLUMNS = ["ts", "period", "game_clock_s", "score_home", "score_away", "margin", "market_prob", "traded"]


# -- Pure parsing (no I/O) -- covered directly by the per-file test. ------

def states_from_payload(payload: dict) -> List[dict]:
    """ESPN summary payload -> sorted-by-ts [{ts, period, game_clock_s,
    score_home, score_away, margin}]. One row per play carrying a wallclock
    ISO8601 timestamp + cumulative scores + a parseable clock. Never
    fabricates: a play missing any required field is skipped."""
    out: List[dict] = []
    for p in payload.get("plays") or []:
        wc = p.get("wallclock")
        per = (p.get("period") or {}).get("number")
        hs, as_ = p.get("homeScore"), p.get("awayScore")
        if not wc or per is None or hs is None or as_ is None:
            continue
        try:
            ts = int(datetime.fromisoformat(str(wc).replace("Z", "+00:00")).timestamp())
        except ValueError:
            continue
        sr = _clock_seconds((p.get("clock") or {}).get("displayValue"))
        out.append({
            "ts": ts, "period": int(per), "game_clock_s": sr,
            "score_home": int(hs), "score_away": int(as_), "margin": int(hs) - int(as_),
        })
    out.sort(key=lambda r: r["ts"])
    return out


def _epoch(ts: Any) -> Optional[int]:
    """Kalshi candle ts (ISO8601 'Z' string) or a raw int -> epoch seconds."""
    if isinstance(ts, (int, float)):
        return int(ts)
    try:
        return int(datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _empty_join_frame(max_staleness_s: float) -> pd.DataFrame:
    out = pd.DataFrame(columns=_JOIN_COLUMNS)
    out.attrs.update({"stale_share": 0.0, "max_staleness_s": max_staleness_s})
    return out


def join_game_states(states: List[dict], candles: List[dict], *,
                     max_staleness_s: float = 300.0) -> pd.DataFrame:
    """merge_asof(candles, states, direction='backward') -- each candle gets
    the LATEST state with ts<=candle_ts (no future leak), provided that state
    is no more than ``max_staleness_s`` old. Candles without a usable state
    are dropped. The returned frame records ``stale_share`` and the rail in
    ``DataFrame.attrs``. Empty input -> empty frame with the right columns
    (never raises). *candles* items use the raw Kalshi shape
    {ts: ISO8601|epoch, prob: float, traded: bool}."""
    if not states or not candles:
        return _empty_join_frame(max_staleness_s)
    st = pd.DataFrame(states).sort_values("ts").reset_index(drop=True)
    cd_rows = [{"ts": _epoch(c.get("ts")), "market_prob": c.get("prob"), "traded": bool(c.get("traded"))}
               for c in candles]
    cd = pd.DataFrame([r for r in cd_rows if r["ts"] is not None])
    if cd.empty:
        return _empty_join_frame(max_staleness_s)
    cd = cd.sort_values("ts").reset_index(drop=True)
    merged, stale_share = asof_join_state(
        cd, st, key="ts", max_staleness_s=max_staleness_s)
    merged = merged.dropna(subset=["margin"]).reset_index(drop=True)
    out = merged[_JOIN_COLUMNS]
    out.attrs.update({"stale_share": stale_share, "max_staleness_s": max_staleness_s})
    log.info("wallclock_join ticks=%d retained=%d stale_share=%.6f rail_s=%s",
             len(cd), len(out), stale_share, max_staleness_s)
    return out


# -- Kalshi-side game enumeration (read-only; games.parquet has no playoff rows) --

@dataclass
class GameMeta:
    event_ticker: str
    date: str          # YYYY-MM-DD (Kalshi ticker's own date)
    away: str
    home: str
    home_win: int
    home_ticker: str
    candles: List[dict] = field(default_factory=list)


def _load_jsonl_doc(path: Path) -> Optional[dict]:
    try:
        text = path.read_text(encoding="utf-8").strip()
        return json.loads(text.splitlines()[0]) if text else None
    except (OSError, json.JSONDecodeError, IndexError):
        return None


def enumerate_games(directory: Path = KALSHI_NBA) -> List[GameMeta]:
    """One GameMeta per distinct KXNBAGAME event_ticker (both side-files
    resolved together). Kalshi tricodes are always 3 chars -> the AWAY+HOME
    tail splits deterministically at position 3."""
    by_event: Dict[str, dict] = {}
    for fp in sorted(glob.glob(str(directory / "KXNBAGAME-*.jsonl"))):
        doc = _load_jsonl_doc(Path(fp))
        if doc is None:
            continue
        by_event.setdefault(doc.get("event_ticker", ""), {})[doc.get("ticker", "")] = doc

    games: List[GameMeta] = []
    for event_ticker, sides in sorted(by_event.items()):
        parsed = parse_nba_ticker(event_ticker)  # regex has no $-anchor; event_ticker alone parses
        if parsed is None or len(sides) != 2:
            continue
        gdate, tail, _ = parsed
        if len(tail) != 6:
            continue
        away, home = tail[:3], tail[3:]
        home_ticker = f"{event_ticker}-{home}"
        home_doc = sides.get(home_ticker)
        if home_doc is None or home_doc.get("result") not in ("yes", "no"):
            continue
        games.append(GameMeta(
            event_ticker=event_ticker, date=gdate.strftime("%Y-%m-%d"),
            away=away, home=home,
            home_win=int(home_doc["result"] == "yes"),
            home_ticker=home_ticker, candles=list(home_doc.get("candles") or []),
        ))
    return games


# -- Network + cache layer. ------------------------------------------------

def _fetch_cached(url: str, cache_path: Path, sleep: float = _SLEEP_S) -> dict:
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    import urllib.request
    time.sleep(sleep)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001 -- a fetch failure is an honest exclusion, not fatal
        log.warning("fetch failed url=%s err=%s", url, exc)
        return {}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def _espn_events_for_date(date_str: str) -> Dict[tuple, str]:
    """{(away, home): event_id} for one YYYYMMDD ESPN scoreboard date."""
    payload = _fetch_cached(_SCOREBOARD_URL.format(date=date_str),
                            RAW_CACHE / "scoreboard" / f"{date_str}.json")
    out: Dict[tuple, str] = {}
    for ev in payload.get("events") or []:
        comps = (ev.get("competitions") or [{}])[0].get("competitors") or []
        sides = {}
        for ct in comps:
            ha = ct.get("homeAway")
            abbr = _norm_abbr((ct.get("team") or {}).get("abbreviation", ""))
            if ha in ("home", "away") and abbr:
                sides[ha] = abbr
        if "home" in sides and "away" in sides:
            out[(sides["away"], sides["home"])] = str(ev.get("id"))
    return out


def resolve_event_id(game: GameMeta) -> Optional[str]:
    """ESPN event_id for a GameMeta, trying the ticker date then +/-1 day."""
    base = datetime.strptime(game.date, "%Y-%m-%d")
    for delta in (0, -1, 1):
        d = (base + timedelta(days=delta)).strftime("%Y%m%d")
        eid = _espn_events_for_date(d).get((game.away, game.home))
        if eid is not None:
            return eid
    return None


def fetch_states_for_event(eid: str) -> List[dict]:
    payload = _fetch_cached(_SUMMARY_URL.format(eid=eid), RAW_CACHE / "summary" / f"{eid}.json")
    return states_from_payload(payload)


_INT64_COLS = ("game_id", "ts", "period", "score_home", "score_away", "margin", "outcome_home_win")


def assemble_output(joined: pd.DataFrame, game_id: int, game_date: str,
                    market_ticker: str, home_win: int) -> pd.DataFrame:
    """One game's join_game_states() output -> the final checkpoint schema
    (game_id, game_date, ..., market_ticker, outcome_home_win), all id/count
    columns cast to int64 (never plain int -- see module invariants)."""
    out = joined.copy()
    out.insert(0, "game_id", game_id)
    out.insert(1, "game_date", game_date)
    out["market_ticker"] = market_ticker
    out["outcome_home_win"] = home_win
    for c in _INT64_COLS:
        out[c] = out[c].astype("int64")
    return out


# -- End-to-end build. -------------------------------------------------------

def build_checkpoints(directory: Path = KALSHI_NBA) -> tuple[pd.DataFrame, Dict[str, int]]:
    """Full pipeline: enumerate games -> resolve ESPN event -> fetch states ->
    merge_asof-join to candles. Returns (checkpoints_df, exclusion_counters)."""
    games = enumerate_games(directory)
    counters = {"games_total": len(games), "games_joined": 0,
                "no_espn_event_match": 0, "empty_pbp": 0, "no_candle_overlap": 0}
    frames: List[pd.DataFrame] = []
    for g in games:
        eid = resolve_event_id(g)
        if eid is None:
            counters["no_espn_event_match"] += 1
            continue
        states = fetch_states_for_event(eid)
        if not states:
            counters["empty_pbp"] += 1
            continue
        joined = join_game_states(states, g.candles)
        if joined.empty:
            counters["no_candle_overlap"] += 1
            continue
        frames.append(assemble_output(joined, int(eid), g.date, g.home_ticker, g.home_win))
        counters["games_joined"] += 1

    if not frames:
        return pd.DataFrame(), counters
    return pd.concat(frames, ignore_index=True), counters


def write(out_path: Path = OUT_PATH) -> tuple[Path, Dict[str, int]]:
    df, counters = build_checkpoints()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not df.empty:
        df.to_parquet(out_path, index=False)
    return out_path, counters


def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    path, counters = write()
    print(f"RESULT {counters} -> {path}")


if __name__ == "__main__":
    _main()

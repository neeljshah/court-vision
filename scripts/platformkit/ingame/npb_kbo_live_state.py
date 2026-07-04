"""scripts.platformkit.ingame.npb_kbo_live_state -- LIVE (in-progress) game states for
NPB and KBO, the LANE-3 counterpart to ingame_live_state's ESPN-shaped sports.

THE GAP THIS CLOSES
--------------------
ingame_live_state._SPORTS has no "npb"/"kbo" entry (ESPN carries neither league --
verified live 400 on both site.api paths this wave) so live_state(s)/live_states(s)
always returned None/[] for npb/kbo, which meant inplay_capture_loop._scan_live_by_legs
could never bridge a captured Kalshi NPB/KBO tick to a live game -> the tick's grade
row never got a real state, and downstream outcome grading (npb_outcome_resolver /
kbo_outcome_resolver, both already shipped and OFFLINE-only) had no live path feeding it.
This module supplies that live path, reusing each sport's ALREADY-SHIPPED offline ingest
conventions rather than inventing a new scrape:

  - npb: domains.baseball_npb.ingest_npb's SAME npb.jp schedule-detail page + regex
    shapes (team1/team2/score1/score2), read for TODAY's date instead of backfilled
    months. PROBED LIVE 2026-07-04: the schedule-detail page has only two observable
    score states -- "&nbsp;"/"&nbsp;" (not yet started) and both scores numeric
    (final) -- there is NO distinct mid-game marker on this page (the <div
    class="state"> node is a static "-" separator on every row, live or not; npb.jp's
    dedicated live-score route (/scores/<year>/<mmdd>/) 403s keyless). So NPB status
    here is COARSE: "scheduled" or "final"-shaped (numeric score); a genuinely
    in-progress game (score partially posted) is NOT distinguishable from "not yet
    started" on this feed and reports as "scheduled" with score None -- documented
    honestly, not fabricated. inning is ALWAYS None (no source for it here).

  - kbo: domains.baseball_kbo.ingest_kbo's SAME GetScheduleList endpoint + regex,
    read for TODAY's date. PROBED LIVE 2026-07-04: today's not-yet-final games render
    the EXACT same/same 0-vs-0 placeholder ingest_kbo.py already documents as
    "in-progress/not-yet-final" (see that module's TIES section) -- this IS the one
    honest signal available: same/same 0-0 -> status "in_progress_or_scheduled"
    (cannot further distinguish pregame from mid-game without a play-by-play feed);
    win/lose (or a non-zero same/same tie) -> status "final". koreabaseball.com's
    dedicated ScoreBoard.aspx is static-asset-only (no embedded live JSON found) and
    GetLiveTextRelay needs a per-game id this module does not have -- not pursued
    further this wave (documented, not silently assumed away). inning is ALWAYS None.

HONESTY / SCOPE: this is a COARSE bridge -- good enough for OUTCOME grading (final
home_win via the existing NpbOutcomeResolver/KboOutcomeResolver, which key off the
SAME schedule sources) because a final game's score is unambiguous here. In-game
SEGMENT granularity (inning-level CLV) is NOT available from this feed; frac_elapsed
is always None. No $ / edge claim -- probability/label space only.

Network isolation: http_get is INJECTABLE (same shape as the underlying ingest
modules); no network at import time. Polite: this module makes ONE request per sport
per call (today's month/page only), no backfill loop.

CLI: python -m scripts.platformkit.ingame.npb_kbo_live_state <npb|kbo>

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_npb_kbo_live_state.py -q
"""
from __future__ import annotations

import datetime as _dt
import logging
import re
import urllib.parse
import urllib.request
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0"
_TIMEOUT = 15

# ---- NPB (npb.jp schedule-detail page) -------------------------------------------

_NPB_SCHEDULE_URL = "https://npb.jp/games/{year}/schedule_{month:02d}_detail.html"
_NPB_ROW_RE = re.compile(r'<tr id="date(?P<md>\d{4})"[^>]*>(?P<block>.*?)</tr>', re.S)
_NPB_TEAM1_RE = re.compile(r'team1">([^<]*)</div>')
_NPB_TEAM2_RE = re.compile(r'team2">([^<]*)</div>')
_NPB_SCORE1_RE = re.compile(r'score1">(\d+)</div>')
_NPB_SCORE2_RE = re.compile(r'score2">(\d+)</div>')

# English display alias for the npb.jp native kanji/katakana club name, reused from
# npb_outcome_resolver's already-verified-live Kalshi-code map (reversed). Best-effort
# only -- absent entries fall back to the native npb.jp name unchanged.
_NPB_EN_ALIAS: Dict[str, str] = {
    "DeNA": "Yokohama DeNA BayStars",
    "ヤクルト": "Tokyo Yakult Swallows",
    "広島": "Hiroshima Toyo Carp",
    "阪神": "Hanshin Tigers",
    "日本ハム": "Hokkaido Nippon-Ham Fighters",
    "楽天": "Tohoku Rakuten Golden Eagles",
    "西武": "Saitama Seibu Lions",
    "オリックス": "Orix Buffaloes",
    "ソフトバンク": "Fukuoka SoftBank Hawks",
    "ロッテ": "Chiba Lotte Marines",
    "巨人": "Yomiuri Giants",
    "中日": "Chunichi Dragons",
}


def _npb_default_http_get(url: str) -> str:
    """Fetch url via urllib, return decoded HTML body or "" on any error. Never raises."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        logger.debug("npb_kbo_live_state npb fetch failed url=%s err=%s", url, exc)
        return ""


def _npb_today_rows(body: str, year: int, month: int, day: int) -> List[dict]:
    """Every game-row block for exactly (year, month, day) from a schedule-detail page
    body. PURE -- no I/O. [] if the page has no row for that date."""
    md = f"{month:02d}{day:02d}"
    out: List[dict] = []
    for m in _NPB_ROW_RE.finditer(body):
        if m.group("md") != md:
            continue
        block = m.group("block")
        t1 = _NPB_TEAM1_RE.search(block)
        t2 = _NPB_TEAM2_RE.search(block)
        if not (t1 and t2):
            continue  # off-day placeholder row, no teams at all
        home = t1.group(1).strip()
        away = t2.group(1).strip()
        if not home or not away:
            continue
        s1 = _NPB_SCORE1_RE.search(block)
        s2 = _NPB_SCORE2_RE.search(block)
        hs = float(s1.group(1)) if s1 else None
        as_ = float(s2.group(1)) if s2 else None
        out.append({"home": home, "away": away, "home_score": hs, "away_score": as_})
    return out


def _npb_states(date: Optional[_dt.date], http_get: Optional[Callable]) -> List[Dict]:
    """Live states for today's (or *date*'s) NPB games. Never raises (any error -> [])."""
    try:
        d = date or _dt.date.today()
        getter = http_get or _npb_default_http_get
        url = _NPB_SCHEDULE_URL.format(year=d.year, month=d.month)
        body = getter(url)
        rows = _npb_today_rows(body, d.year, d.month, d.day)
        out: List[Dict] = []
        for r in rows:
            hs, as_ = r["home_score"], r["away_score"]
            final = hs is not None and as_ is not None
            status = "final" if final else "scheduled"
            out.append({
                "sport": "npb", "game_id": f"npb-{d.isoformat()}-{r['away']}-{r['home']}",
                "home": r["home"], "away": r["away"],
                "home_display": _NPB_EN_ALIAS.get(r["home"], r["home"]),
                "away_display": _NPB_EN_ALIAS.get(r["away"], r["away"]),
                "home_score": hs, "away_score": as_,
                "state_diff": (hs - as_) if final else None,
                "inning": None, "frac_elapsed": None,
                "status": status,
            })
        return out
    except Exception as exc:  # noqa: BLE001 -- a scan error is no live games, never a crash
        logger.debug("npb_kbo_live_state npb_states failed: %s", exc)
        return []


# ---- KBO (koreabaseball.com GetScheduleList) --------------------------------------

_KBO_URL = "https://www.koreabaseball.com/ws/Schedule.asmx/GetScheduleList"
_KBO_REFERER = "https://www.koreabaseball.com/Schedule/Schedule.aspx"
_KBO_PLAY_RE = re.compile(
    r'<span>(?P<away>[^<]*)</span>'
    r'<em><span class="(?P<xc>win|lose|same)">(?P<as_>\d+)</span>'
    r'<span>vs</span>'
    r'<span class="(?P<yc>win|lose|same)">(?P<hs>\d+)</span></em>'
    r'<span>(?P<home>[^<]*)</span>'
)
_KBO_DAY_RE = re.compile(r'^(?P<mm>\d{2})\.(?P<dd>\d{2})')


def _kbo_default_http_get(url: str, body: str) -> str:
    """POST *body* to *url*, return decoded response text or "" on any error. Never raises."""
    req = urllib.request.Request(
        url, data=body.encode("utf-8"), method="POST",
        headers={"User-Agent": _UA,
                 "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                 "Referer": _KBO_REFERER})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        logger.debug("npb_kbo_live_state kbo fetch failed url=%s err=%s", url, exc)
        return ""


def _kbo_today_rows(body: str, month: int, day: int) -> List[dict]:
    """Every game-row for exactly (month, day) from a GetScheduleList JSON body. PURE --
    no I/O. [] if the body is not valid JSON or has no row for that date."""
    import json
    try:
        data = json.loads(body) if body else None
    except (ValueError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    rows = data.get("rows", []) if isinstance(data.get("rows"), list) else []
    out: List[dict] = []
    cur_month: Optional[int] = None
    cur_day: Optional[int] = None
    for rg in rows:
        cells = rg.get("row", []) if isinstance(rg, dict) else []
        for cell in cells:
            cls = cell.get("Class")
            text = cell.get("Text", "") or ""
            if cls == "day":
                m = _KBO_DAY_RE.match(text)
                if m:
                    cur_month, cur_day = int(m.group("mm")), int(m.group("dd"))
            elif cls == "play":
                if cur_month != month or cur_day != day:
                    continue
                m = _KBO_PLAY_RE.search(text)
                if not m:
                    continue  # postponed/unplayed -- no score spans at all
                away = m.group("away").strip()
                home = m.group("home").strip()
                if not away or not home:
                    continue
                out.append({
                    "home": home, "away": away,
                    "home_score": float(m.group("hs")), "away_score": float(m.group("as_")),
                    "tied_marker": (m.group("xc") == "same") and (m.group("yc") == "same"),
                })
    return out


def _kbo_states(date: Optional[_dt.date], http_get: Optional[Callable]) -> List[Dict]:
    """Live states for today's (or *date*'s) KBO games. Never raises (any error -> [])."""
    try:
        d = date or _dt.date.today()
        getter = http_get or _kbo_default_http_get
        params = {"leId": "1", "srIdList": "0,9,6", "seasonId": str(d.year),
                  "gameMonth": f"{d.month:02d}", "teamId": ""}
        body = getter(_KBO_URL, urllib.parse.urlencode(params))
        rows = _kbo_today_rows(body, d.month, d.day)
        out: List[Dict] = []
        for r in rows:
            hs, as_ = r["home_score"], r["away_score"]
            # same/same 0-0 is the documented in-progress/not-yet-final placeholder
            # (see module docstring); anything else with a "same" marker is a real tie.
            placeholder = r["tied_marker"] and hs == 0.0 and as_ == 0.0
            status = "in_progress_or_scheduled" if placeholder else "final"
            out.append({
                "sport": "kbo", "game_id": f"kbo-{d.isoformat()}-{r['away']}-{r['home']}",
                "home": r["home"], "away": r["away"],
                "home_display": r["home"], "away_display": r["away"],
                "home_score": None if placeholder else hs,
                "away_score": None if placeholder else as_,
                "state_diff": None if placeholder else (hs - as_),
                "inning": None, "frac_elapsed": None,
                "status": status,
            })
        return out
    except Exception as exc:  # noqa: BLE001 -- a scan error is no live games, never a crash
        logger.debug("npb_kbo_live_state kbo_states failed: %s", exc)
        return []


# ---- dispatch ----------------------------------------------------------------------

_DISPATCH: Dict[str, Callable] = {"npb": _npb_states, "kbo": _kbo_states}


def live_states(sport: str, *, date: Optional[_dt.date] = None,
                http_get: Optional[Callable] = None) -> List[Dict]:
    """All (coarse) game states for *sport* ("npb"|"kbo") for today (or *date*), [] for
    any other sport or on any error. Mirrors ingame_live_state.live_states's return
    shape (list of per-game dicts with home/away/home_display/away_display/home_score/
    away_score/state_diff/status) so callers that already consume that shape (e.g.
    inplay_capture_loop._scan_live_by_legs) work unchanged. Never raises."""
    fn = _DISPATCH.get(str(sport).lower())
    if fn is None:
        return []
    try:
        return fn(date, http_get)
    except Exception as exc:  # noqa: BLE001
        logger.debug("npb_kbo_live_state.live_states(%s) failed: %s", sport, exc)
        return []


def main() -> None:
    import json
    import sys
    sport = sys.argv[1] if len(sys.argv) > 1 else "npb"
    res = live_states(sport)
    print(json.dumps(res, indent=2, ensure_ascii=False) if res else f"no live {sport} states found")


if __name__ == "__main__":
    main()


__all__ = ["live_states"]

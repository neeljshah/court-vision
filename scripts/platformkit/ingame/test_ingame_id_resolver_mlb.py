"""Per-file test for ingame_id_resolver_mlb -- the Kalshi<->statsapi MLB id bridge.

OFFLINE + deterministic: candidates + linescore are INJECTED -- no network.  Covers the
binding rails: a UNIQUE blob match resolves the gamePk; ZERO / AMBIGUOUS / UNMAPPED never
mis-bind (-> None); the statsapi linescore adapts to the EXISTING base-out extractor
(RE24); between half-innings carries no fabricated base-out; the lazy enricher makes no
candidate fetch until a real game needs it.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/ingame/test_ingame_id_resolver_mlb.py -q
"""
from __future__ import annotations

from scripts.platformkit.ingame import ingame_id_resolver_mlb as R


# --- the real active ticker observed live + its statsapi candidate ------------------- #
_TICKER = "KXMLBGAME-26JUN271810AZTB"  # AZ (Arizona) @ TB (Tampa Bay)
_AZTB = {"game_pk": "822960", "away": "Arizona Diamondbacks", "home": "Tampa Bay Rays"}


def test_parse_ticker_parts():
    p = R.parse_kalshi_mlb_ticker(_TICKER)
    assert p == {"yy": "26", "mon": "JUN", "dd": "27", "hhmm": "1810", "blob": "AZTB"}
    # Non-tickers / wrong series -> None (never a fabricated parse).
    assert R.parse_kalshi_mlb_ticker("KXNBAGAME-26JUN271810LALBOS") is None
    assert R.parse_kalshi_mlb_ticker("") is None
    assert R.parse_kalshi_mlb_ticker(None) is None


def test_resolve_unique_match():
    res = R.resolve_ticker(_TICKER, candidates=[_AZTB])
    assert res is not None
    assert res["game_pk"] == "822960"
    assert res["away_abbr"] == "AZ" and res["home_abbr"] == "TB"


def test_resolve_no_match_returns_none():
    # A live game whose teams don't form the AZTB blob -> no match (skip, never wrong-bind).
    other = {"game_pk": "1", "away": "Boston Red Sox", "home": "Colorado Rockies"}
    assert R.resolve_ticker(_TICKER, candidates=[other]) is None


def test_resolve_ambiguous_doubleheader_returns_none():
    # Two simultaneously-live AZ@TB candidates (a doubleheader) -> ambiguous -> None.
    dh = [dict(_AZTB, game_pk="822960"), dict(_AZTB, game_pk="822961")]
    assert R.resolve_ticker(_TICKER, candidates=dh) is None


def test_resolve_unmapped_team_returns_none():
    # An unknown team name maps to no abbrev -> the candidate can't form a blob -> no bind.
    bad = {"game_pk": "9", "away": "Arizona Diamondbacks", "home": "Sasquatch FC"}
    assert R.resolve_ticker(_TICKER, candidates=[bad]) is None


def test_kalshi_distinct_abbrevs():
    # The Kalshi-specific abbrevs that differ from ESPN/statsapi must be exactly these.
    assert R.KALSHI_ABBR["arizona diamondbacks"] == "AZ"
    assert R.KALSHI_ABBR["chicago white sox"] == "CWS"
    assert R.KALSHI_ABBR["san diego padres"] == "SD"
    assert R.KALSHI_ABBR["washington nationals"] == "WSH"
    # All 30 clubs covered (Athletics keyed both old + new name) -> 31 entries.
    assert len(set(R.KALSHI_ABBR.values())) == 30


def _linescore(inning, state, is_top, outs, *, bases=(), balls=None, strikes=None):
    off = {b: {"id": 1} for b in bases}  # occupied bases present as player objects
    ls = {"currentInning": inning, "inningState": state, "isTopInning": is_top,
          "outs": outs, "offense": off}
    if balls is not None:
        ls["balls"] = balls
    if strikes is not None:
        ls["strikes"] = strikes
    return ls


def test_linescore_deep_fields_runner_on_second():
    # Bottom 7, 1 out, runner on 2nd, count 1-1 -> base=2, bos=7, re=0.664.
    ls = _linescore(7, "Bottom", False, 1, bases=("second",), balls=1, strikes=1)
    d = R.linescore_deep_fields(ls)
    assert d["inning"] == 7 and d["half"] == "bottom"
    assert d["outs"] == 1 and d["base"] == 2 and d["bos"] == 7
    assert d["re"] == 0.664 and d["count"] == "1-1"


def test_linescore_between_innings_has_no_baseout():
    # Middle of the 8th (3 outs) -> inning/half kept, base-out absent (no fabricated state).
    ls = _linescore(8, "Middle", True, 3)
    d = R.linescore_deep_fields(ls)
    assert d.get("inning") == 8 and d.get("half") == "top"
    assert "base" not in d and "outs" not in d and "re" not in d


def test_linescore_empty_returns_empty():
    assert R.linescore_deep_fields({}) == {}
    assert R.linescore_deep_fields(None) == {}


def test_deep_state_for_ticker_end_to_end():
    ls = _linescore(3, "Top", True, 2, bases=("first", "third"), balls=0, strikes=2)
    deep = R.deep_state_for_ticker(
        _TICKER, candidates=[_AZTB], http_get=lambda url: ls)
    # 1st & 3rd (base_state 5), 2 outs -> bos = 5*3+2 = 17, re = 0.478.
    assert deep["game_pk"] == "822960"
    assert deep["base"] == 5 and deep["bos"] == 17 and deep["re"] == 0.478
    assert deep["count"] == "0-2"


def test_deep_state_unresolved_returns_empty():
    # Ticker resolves to no candidate -> {} (caller leaves the state shallow, never faked).
    assert R.deep_state_for_ticker(_TICKER, candidates=[], http_get=lambda u: {}) == {}


def test_deep_state_reuses_candidate_linescore_no_refetch():
    # live_games() now attaches the linescore to each candidate; deep_state_for_ticker MUST
    # reuse it (no redundant per-tick linescore GET) and fetch ONLY the boxscore.
    ls = _linescore(7, "Bottom", False, 1, bases=("second",), balls=1, strikes=1)
    cand = dict(_AZTB, linescore=ls)
    fetched = []
    deep = R.deep_state_for_ticker(
        _TICKER, candidates=[cand],
        http_get=lambda url: (fetched.append(url) or {}))
    assert deep["base"] == 2 and deep["bos"] == 7 and deep["re"] == 0.664  # from reused ls
    assert not any("linescore" in u for u in fetched)   # linescore NOT refetched
    assert all("boxscore" in u for u in fetched)         # only the boxscore is fetched


def test_make_tick_deep_fn_is_lazy_and_memoized():
    calls = {"cands": 0}

    def _cands():
        calls["cands"] += 1
        return [_AZTB]

    def _resolver(gid, *, candidates, http_get):
        return {"game_pk": "822960", "outs": 1} if candidates else {}

    deep_fn = R.make_tick_deep_fn(candidates_fn=_cands, resolver_fn=_resolver)
    assert calls["cands"] == 0           # LAZY: no fetch at construction
    assert deep_fn(_TICKER)["outs"] == 1
    assert deep_fn(_TICKER)["outs"] == 1
    assert calls["cands"] == 1           # candidates fetched ONCE, then memoized


def test_make_tick_deep_fn_never_raises():
    def _boom():
        raise RuntimeError("feed dead")

    deep_fn = R.make_tick_deep_fn(candidates_fn=_boom)
    assert deep_fn(_TICKER) == {}        # any error -> {} for that game, never raises


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    sys.exit(0)

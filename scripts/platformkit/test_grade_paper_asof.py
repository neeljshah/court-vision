"""Per-file tests for scripts.platformkit.grade_paper_asof (no network).

Covers: kbo/npb bridge routing + shaping, ESPN date-override plumbing, the bounded
oldest-first backlog pass (settles a prior-day open bet, respects max_bets, never
re-touches an already-settled row, sleeps only between distinct board fetches).

Run ONLY this file (full suite freezes the box):
    python -m pytest scripts/platformkit/test_grade_paper_asof.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.clv_ledger import record_bet
from scripts.platformkit.grade_paper_asof import (
    backfill_as_of,
    mlb_ticker_fallback_match,
    route_fetch,
    _candidate_dates,
)


# --------------------------------------------------------------------------- #
# route_fetch: kbo/npb bridge dispatch + shaping.
# --------------------------------------------------------------------------- #
def test_route_fetch_kbo_uses_bridge_not_espn(monkeypatch):
    calls = []

    def fake_live_states(sport, *, date=None, http_get=None):
        calls.append((sport, date))
        return [{"home": "KIA", "away": "NC", "home_score": 5, "away_score": 2,
                 "status": "final"}]

    monkeypatch.setattr("scripts.platformkit.grade_paper_asof._nk.live_states",
                        fake_live_states)
    out = route_fetch("kbo", date="2026-06-20")
    assert calls == [("kbo", __import__("datetime").date(2026, 6, 20))]
    assert out["status"] == "ok"
    g = out["games"][0]
    assert g["state"] == "final" and g["home"] == "KIA" and g["away"] == "NC"
    assert g["home_score"] == 5 and g["away_score"] == 2


def test_route_fetch_kbo_not_final_maps_to_pre(monkeypatch):
    monkeypatch.setattr(
        "scripts.platformkit.grade_paper_asof._nk.live_states",
        lambda sport, **kw: [{"home": "LG", "away": "SSG", "home_score": None,
                              "away_score": None, "status": "in_progress_or_scheduled"}])
    out = route_fetch("kbo")
    assert out["games"][0]["state"] == "pre"


def test_route_fetch_other_sport_goes_to_live_board(monkeypatch):
    seen = {}

    def fake_todays(sport, *, date=None, http_get=None, predictor_factory=None):
        seen["sport"] = sport
        seen["date"] = date
        return {"sport": sport, "status": "ok", "games": []}

    monkeypatch.setattr("scripts.platformkit.grade_paper_asof._lb.todays_live_games",
                        fake_todays)
    route_fetch("mlb", date="2026-06-28")
    assert seen == {"sport": "mlb", "date": "20260628"}


# --------------------------------------------------------------------------- #
# backfill_as_of: bounded oldest-first backlog pass.
# --------------------------------------------------------------------------- #
def _stale_bet(ledger, ts, sport="mlb", matchup="CIN @ NYM", side="home",
              bet_id=None):
    row = {"ts": ts, "sport": sport, "matchup": matchup, "side": side,
           "taken_book": "paper_book", "taken_decimal": 2.0, "model_prob": 0.55,
           "stake_units": 1.0, "status": "open", "executed": False,
           "market": "moneyline", "market_type": "moneyline",
           "bet_id": bet_id or f"{sport}|{matchup}|{side}|{ts}"}
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


def _game(home, home_abbr, away, away_abbr, hs, as_, state="post"):
    return {"home": home, "home_abbr": home_abbr, "away": away, "away_abbr": away_abbr,
            "state": state, "home_score": hs, "away_score": as_}


def test_backfill_settles_prior_day_bet_via_dated_board(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    _stale_bet(ledger, "2026-06-20T21:10:00+00:00")

    def fetch(sport, date):
        assert sport == "mlb" and date == "2026-06-20"
        return {"games": [_game("New York Mets", "NYM", "Cincinnati Reds", "CIN", 6, 3)]}

    out = backfill_as_of(ledger, today="2026-06-25", fetch=fetch, _sleep=lambda s: None)
    assert out["settled_now"] == 1 and out["still_pending"] == 0
    assert out["per_sport_settled"] == {"mlb": 1}
    rows = [json.loads(ln) for ln in ledger.read_text(encoding="utf-8").splitlines() if ln]
    settled = [r for r in rows if r.get("graded")]
    assert len(settled) == 1 and settled[0]["outcome"] == "win"


def test_backfill_never_retouches_already_settled_row(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    bet = _stale_bet(ledger, "2026-06-20T21:10:00+00:00")
    # Pre-existing settled twin (as if a prior run already graded it).
    twin = dict(bet, status="settled", graded=True, outcome="win",
               settle_key=bet["bet_id"])
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(twin) + "\n")

    calls = []

    def fetch(sport, date):
        calls.append((sport, date))
        return {"games": [_game("New York Mets", "NYM", "Cincinnati Reds", "CIN", 6, 3)]}

    out = backfill_as_of(ledger, today="2026-06-25", fetch=fetch, _sleep=lambda s: None)
    assert out["settled_now"] == 0
    assert calls == []  # already-settled bet never triggers a board fetch
    lines = [ln for ln in ledger.read_text(encoding="utf-8").splitlines() if ln]
    assert len(lines) == 2  # open row + the one pre-existing settled twin, untouched


def test_backfill_respects_max_bets_oldest_first(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    _stale_bet(ledger, "2026-06-21T00:00:00+00:00", matchup="LAD @ SFG", bet_id="a")
    _stale_bet(ledger, "2026-06-20T00:00:00+00:00", matchup="CIN @ NYM", bet_id="b")

    def fetch(sport, date):
        return {"games": []}  # nothing matches -> both stay pending, order still checked

    out = backfill_as_of(ledger, today="2026-06-25", max_bets=1, fetch=fetch,
                         _sleep=lambda s: None)
    assert out["backlog_total"] == 2 and out["attempted"] == 1
    assert out["still_pending"] == 1


def test_backfill_sleeps_only_between_distinct_boards(tmp_path):
    """2 bets, SAME (sport, ts-date), no match on either candidate date (empty board):
    each bet tries [ts-ET-date, ts-ET-date+1] -> 2 DISTINCT boards total (deduped
    across both bets, not 4), so exactly 1 politeness sleep fires (before the 2nd
    board). ts 00:00Z 06-20 = 20:00 ET 06-19, so the ET window is [06-19, 06-20]
    -- the OLD ts[:10] UTC window ([06-20, 06-21]) never fetched the most likely
    game date at all (audit finding 2026-07-12, evening-settle starvation)."""
    ledger = tmp_path / "clv_ledger.jsonl"
    _stale_bet(ledger, "2026-06-20T00:00:00+00:00", matchup="LAD @ SFG", bet_id="a")
    _stale_bet(ledger, "2026-06-20T00:01:00+00:00", matchup="CIN @ NYM", bet_id="b")
    sleeps = []
    fetched = []

    def fetch(sport, date):
        fetched.append((sport, date))
        return {"games": []}

    backfill_as_of(ledger, today="2026-06-25", fetch=fetch, _sleep=sleeps.append)
    assert fetched == [("mlb", "2026-06-19"), ("mlb", "2026-06-20")]
    assert sleeps == [1.0]


# --------------------------------------------------------------------------- #
# MLB team-alias gap (gap ledger, 36-row backlog): Kalshi shorthand matchup
# labels ("A's", "Chicago WS", "New York Y") vs the ticker-based fallback.
# --------------------------------------------------------------------------- #
def test_mlb_ticker_fallback_matches_kalshi_shorthand_label():
    bet = {"sport": "mlb", "matchup": "Chicago WS vs Cleveland",
           "bet_id": "pm|kalshi|KXMLBGAME-26JUL051400CWSCLE|home"}
    games = [_game("Cleveland Guardians", "CLE", "Chicago White Sox", "CHW", 6, 7)]
    g = mlb_ticker_fallback_match(bet, games)
    assert g is not None and g["home_abbr"] == "CLE" and g["away_abbr"] == "CHW"


def test_mlb_ticker_fallback_none_without_ticker():
    bet = {"sport": "mlb", "matchup": "Chicago WS vs Cleveland", "bet_id": "mlb|abc|home"}
    games = [_game("Cleveland Guardians", "CLE", "Chicago White Sox", "CHW", 6, 7)]
    assert mlb_ticker_fallback_match(bet, games) is None


def test_mlb_ticker_fallback_none_when_not_final():
    bet = {"sport": "mlb", "matchup": "Chicago WS vs Cleveland",
           "bet_id": "pm|kalshi|KXMLBGAME-26JUL051400CWSCLE|home"}
    games = [_game("Cleveland Guardians", "CLE", "Chicago White Sox", "CHW", 6, 7, state="pre")]
    assert mlb_ticker_fallback_match(bet, games) is None


def test_candidate_dates_prefers_mlb_ticker_date_over_ts():
    bet = {"sport": "mlb", "ts": "2026-07-05T02:35:02+00:00",
           "bet_id": "pm|kalshi|KXMLBGAME-26JUL071840NYYTB|away"}
    assert _candidate_dates(bet, today="2026-07-10") == ["2026-07-07"]


def test_backfill_settles_mlb_kalshi_shorthand_via_ticker(tmp_path):
    """The exact gap this lane closes: matchup='Chicago WS vs Cleveland' fails the
    plain token match, but the KXMLBGAME ticker in bet_id resolves it -- and its
    own embedded date (07-05) drives the board fetch, not the ts-based guess."""
    ledger = tmp_path / "clv_ledger.jsonl"
    _stale_bet(ledger, "2026-07-04T23:27:44+00:00", matchup="Chicago WS vs Cleveland",
              side="away", bet_id="pm|kalshi|KXMLBGAME-26JUL051400CWSCLE|away")

    def fetch(sport, date):
        assert sport == "mlb" and date == "2026-07-05"
        return {"games": [_game("Cleveland Guardians", "CLE", "Chicago White Sox", "CHW", 6, 7)]}

    out = backfill_as_of(ledger, today="2026-07-10", fetch=fetch, _sleep=lambda s: None)
    assert out["settled_now"] == 1 and out["still_pending"] == 0
    rows = [json.loads(ln) for ln in ledger.read_text(encoding="utf-8").splitlines() if ln]
    settled = [r for r in rows if r.get("graded")]
    assert len(settled) == 1 and settled[0]["outcome"] == "win"  # away (CHW) won 7-6


# --------------------------------------------------------------------------- #
# Wrong-settle fix (gap ledger review of 0889b481): the COL@SF trap -- 3 tickets
# dated 26JUL09/10/11 must NOT all bind to the identical 26JUL09 8-2 final.
# --------------------------------------------------------------------------- #
def test_mlb_ticker_fallback_rejects_wrong_date_board():
    """A ticket dated 26JUL11 must NOT settle against a same-teams final on a
    board queried for an EARLIER date, even though the team pairing matches --
    this is the exact proven live wrong-settle (COL@SF 3-date collision)."""
    bet = {"sport": "mlb", "matchup": "Colorado @ San Francisco",
           "bet_id": "pm|kalshi|KXMLBGAME-26JUL111400COLSF|home"}
    games = [_game("San Francisco Giants", "SF", "Colorado Rockies", "COL", 8, 2)]
    assert mlb_ticker_fallback_match(bet, games, board_date="2026-07-09") is None
    g = mlb_ticker_fallback_match(bet, games, board_date="2026-07-11")
    assert g is not None and g["home_abbr"] == "SF"


def test_mlb_ticker_fallback_doubleheader_gnum_picks_correct_game():
    """A G2 ticket must resolve to the SECOND same-pairing final, not the first."""
    bet = {"sport": "mlb", "matchup": "Colorado @ San Francisco",
           "bet_id": "pm|kalshi|KXMLBGAME-26JUL111400COLSFG2|home"}
    game1 = _game("San Francisco Giants", "SF", "Colorado Rockies", "COL", 3, 1)
    game2 = _game("San Francisco Giants", "SF", "Colorado Rockies", "COL", 8, 2)
    g = mlb_ticker_fallback_match(bet, [game1, game2], board_date="2026-07-11")
    assert g is game2


def test_mlb_ticker_fallback_ambiguous_same_pairing_no_gnum_skips():
    """2 finals for the same pairing on the same date, no G-suffix on the ticket:
    genuinely ambiguous -- honest skip, never a guessed first match."""
    bet = {"sport": "mlb", "matchup": "Colorado @ San Francisco",
           "bet_id": "pm|kalshi|KXMLBGAME-26JUL111400COLSF|home"}
    game1 = _game("San Francisco Giants", "SF", "Colorado Rockies", "COL", 3, 1)
    game2 = _game("San Francisco Giants", "SF", "Colorado Rockies", "COL", 8, 2)
    assert mlb_ticker_fallback_match(bet, [game1, game2], board_date="2026-07-11") is None


def test_backfill_skips_todays_bets(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    _stale_bet(ledger, "2026-06-25T00:00:00+00:00")  # ts == today -> not backlog

    def fetch(sport, date):
        raise AssertionError("should never fetch: no backlog bet")

    out = backfill_as_of(ledger, today="2026-06-25", fetch=fetch, _sleep=lambda s: None)
    assert out["backlog_total"] == 0 and out["attempted"] == 0

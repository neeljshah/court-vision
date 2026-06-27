"""Per-file tests for the pure season-aware schedule policy (A5/D3).

Asserts: settled-pending -> recalibrate; in-season-idle -> NO_CANDIDATE (honest idle);
off-season -> IDLE_OFFSEASON (positive, distinct from a dead feed); never emits a
ship/flag/real-money kind; deterministic for a fixed state; the priority ladder order.

Run: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
     tests/platformkit/autonomy/test_schedule_policy.py -q
"""
from __future__ import annotations

import datetime as dt

from scripts.platformkit.autonomy import schedule_policy as sp
from scripts.platformkit.autonomy.schedule_policy import SchedulePolicy
from scripts.platformkit.autonomy import work_queue as wq


def _jan():
    return dt.datetime(2026, 1, 15)  # NBA + soccer + tennis in season; MLB off


def _jul():
    return dt.datetime(2026, 7, 15)  # MLB + tennis in season; NBA + soccer off


def test_settled_pending_yields_recalibrate():
    pol = SchedulePolicy(sports=["nba"])
    d = pol.decide({"nba": {"settled_pending": 3}}, now=_jan())
    assert d.status == sp.TASK
    assert d.task is not None and d.task.kind == "recalibrate"
    assert d.task.sport == "nba"


def test_ingame_pending_yields_regate_when_no_settled():
    pol = SchedulePolicy(sports=["nba"])
    d = pol.decide({"nba": {"settled_pending": 0, "ingame_pending": 2}}, now=_jan())
    assert d.status == sp.TASK and d.task.kind == "regate_ingame"


def test_stale_corpus_yields_refresh():
    pol = SchedulePolicy(sports=["nba"], stale_corpus_days=7.0)
    d = pol.decide({"nba": {"corpus_age_days": 9.0}}, now=_jan())
    assert d.status == sp.TASK and d.task.kind == "refresh_corpora"
    # fresh corpus -> no task.
    d2 = pol.decide({"nba": {"corpus_age_days": 1.0}}, now=_jan())
    assert d2.status == sp.NO_CANDIDATE


def test_priority_ladder_order():
    # settled beats ingame beats stale-corpus, deterministically.
    pol = SchedulePolicy(sports=["nba"])
    st = {"nba": {"settled_pending": 1, "ingame_pending": 1, "corpus_age_days": 99.0}}
    assert pol.decide(st, now=_jan()).task.kind == "recalibrate"
    st["nba"]["settled_pending"] = 0
    assert pol.decide(st, now=_jan()).task.kind == "regate_ingame"
    st["nba"]["ingame_pending"] = 0
    assert pol.decide(st, now=_jan()).task.kind == "refresh_corpora"


def test_in_season_idle_is_no_candidate_not_offseason():
    pol = SchedulePolicy(sports=["nba"])
    d = pol.decide({"nba": {}}, now=_jan())  # in season, nothing pending
    assert d.status == sp.NO_CANDIDATE
    assert d.task is None
    assert d.sports["nba"] == "IN_SEASON"


def test_offseason_is_positive_distinct_idle():
    # MLB is out of season in January -> IDLE_OFFSEASON, NOT NO_CANDIDATE, NOT green.
    pol = SchedulePolicy(sports=["mlb"])
    d = pol.decide({"mlb": {"settled_pending": 5}}, now=_jan())
    assert d.status == sp.IDLE_OFFSEASON
    assert d.task is None
    assert d.sports["mlb"] == "OFFSEASON"
    # The offseason status is DISTINCT from the in-season honest-idle status.
    assert sp.IDLE_OFFSEASON != sp.NO_CANDIDATE


def test_dead_feed_vs_offseason_disambiguation():
    # In-season sport with no work surfaces NO_CANDIDATE (a dead feed lives here);
    # off-season sport surfaces IDLE_OFFSEASON. The two are never conflated.
    pol = SchedulePolicy(sports=["nba", "mlb"])
    d = pol.decide({"nba": {}, "mlb": {"settled_pending": 9}}, now=_jan())
    # NBA in-season-idle dominates as NO_CANDIDATE; MLB is classified OFFSEASON.
    assert d.status == sp.NO_CANDIDATE
    assert d.sports["nba"] == "IN_SEASON" and d.sports["mlb"] == "OFFSEASON"


def test_first_in_season_sport_with_work_wins_deterministically():
    pol = SchedulePolicy(sports=["nba", "tennis"])
    st = {"nba": {"settled_pending": 1}, "tennis": {"settled_pending": 1}}
    d1 = pol.decide(st, now=_jan())
    d2 = pol.decide(st, now=_jan())
    assert d1.task.sport == "nba" == d2.task.sport  # deterministic, order-stable


def test_never_emits_forbidden_kind_over_many_states():
    pol = SchedulePolicy()
    states = [
        {}, {"nba": {"settled_pending": 1}}, {"mlb": {"ingame_pending": 4}},
        {"soccer": {"corpus_age_days": 50.0}}, {"tennis": {"settled_pending": 2}},
    ]
    for now in (_jan(), _jul()):
        for st in states:
            d = pol.decide(st, now=now)
            if d.task is not None:
                assert d.task.kind in sp.MEASUREMENT_KINDS
                assert d.task.kind not in sp.FORBIDDEN_KINDS


def test_no_sports_configured_is_idle_all():
    pol = SchedulePolicy(sports=[])
    d = pol.decide({}, now=_jan())
    assert d.status == sp.IDLE_ALL and d.task is None


def test_policy_kinds_agree_with_queue_allowed_kinds():
    # No drift: every kind the policy may emit is enqueueable by the work queue.
    assert set(sp.MEASUREMENT_KINDS) == set(wq.ALLOWED_KINDS)


def test_is_in_season_helper():
    assert sp.is_in_season("nba", 1) is True
    assert sp.is_in_season("mlb", 1) is False
    assert sp.is_in_season("mlb", 7) is True
    # custom window override is honored.
    assert sp.is_in_season("xx", 6, {"xx": (6,)}) is True

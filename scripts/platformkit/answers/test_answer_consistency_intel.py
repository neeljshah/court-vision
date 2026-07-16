"""LANE G -- consistency battery for the wave-3 intel categories (injury_report,
news_context, schedule_context, scouting_report, comparables, matchup_preview,
prediction_winprob). Same guarantee as test_answer_consistency_nba.py: every
category must produce the SAME receipt fields whether resolved directly via
resolver_registry.resolve or rendered through contract_client.answer (the
deterministic "LLM following docs/AI_CONSUMER_CONTRACT.md" stand-in). Both call
the identical resolver, so this catches the client-formatting layer dropping,
re-rounding, or substituting a field relative to the oracle.

Real data on this box is thin for some categories (a fresh clone has no
edge_engine fact stores / no predict_matchup corpus). The battery is
status-agnostic: an `ok` envelope must have its receipt fields quoted verbatim
in the render; any fail-closed status (no_data / refused / not_supported /
ambiguous) must render with the matching prefix. Either way the two paths agree.

as_of note: comparables / matchup_preview / prediction_winprob stamp as_of at
call time (now()), so two independent resolve() calls legitimately differ --
those cases assert source_artifact + receipt fields but NOT cross-call as_of
equality (which would be a test artifact, not a real inconsistency).

Run: python -m pytest scripts/platformkit/answers/test_answer_consistency_intel.py -q
"""
from __future__ import annotations

import unicodedata

from scripts.platformkit.answers import contract_client as CC
from scripts.platformkit.answers import resolver_registry as R

_PREFIX = {"no_data": "NO_DATA", "refused": "REFUSED",
           "not_supported": "NOT_SUPPORTED", "ambiguous": "AMBIGUOUS"}


def _ascii(s) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")


def _agree(query: str, sport: str, ok_fields: tuple[str, ...], *, stable_as_of: bool = True, **kwargs):
    """direct-resolve == contract_client render for one query. Returns the
    direct envelope so a caller can add category-specific assertions."""
    direct = R.resolve(query, sport, **kwargs)
    rendered = _ascii(CC.answer(query, sport, **kwargs))
    st = direct["status"]
    if st == "ok":
        assert _ascii(direct["source_artifact"]) in rendered, (
            f"{query}: source_artifact {direct['source_artifact']!r} missing from render {rendered!r}")
        if stable_as_of:
            assert str(direct["as_of"]) in rendered, (
                f"{query}: as_of {direct['as_of']!r} missing from render {rendered!r}")
        for k in ok_fields:
            assert k in direct and direct[k] is not None, f"{query}: envelope missing '{k}'"
            assert _ascii(direct[k]) in rendered, (
                f"{query}: field {k}={direct[k]!r} missing from client render {rendered!r}")
    else:
        assert _PREFIX[st] in rendered, (
            f"{query}: status {st} not rendered with prefix {_PREFIX[st]!r} in {rendered!r}")
    return direct


def test_injury_report_agrees():
    _agree("injury report for New York Yankees", "mlb", ("matched_entity",))


def test_news_context_agrees():
    _agree("news context for New York Yankees", "mlb", ("matched_entity",))


def test_schedule_context_agrees():
    d = _agree("schedule context for LAL", "nba", ("team",), date="2025-11-01")
    if d["status"] == "ok":
        # games_in_last_7 is a computed integer -- it too must survive the render verbatim
        assert str(d["games_in_last_7"]) in _ascii(CC.answer("schedule context for LAL", "nba", date="2025-11-01"))


def test_scouting_report_agrees():
    _agree("scouting report for Trae Young", "nba", ("player",))


def test_comparables_agrees():
    # as_of is now()-stamped -- skip cross-call as_of equality (see module note)
    d = _agree("who is comparable to Trae Young", "nba", ("player",), stable_as_of=False)
    if d["status"] == "ok":
        rendered = _ascii(CC.answer("who is comparable to Trae Young", "nba"))
        for nbr in d["neighbors"]:
            assert _ascii(nbr["entity_name"]) in rendered


def test_matchup_preview_agrees():
    # matchup_preview always returns ok (blocks fail-close individually); as_of is now()
    d = _agree("preview NYY vs BOS", "mlb", ("home", "away"), stable_as_of=False)
    assert d["status"] == "ok" and d["home"] == "NYY" and d["away"] == "BOS"


def test_prediction_winprob_agrees():
    # rewired: prediction_winprob now dispatches winprob_dispatch (was not_supported)
    d = _agree("win probability NYY vs BOS", "mlb", ("home", "away"), stable_as_of=False)
    assert d["category"] == "winprob"  # envelope carries winprob_dispatch's own category


def test_classify_routes_new_categories_without_shadowing_existing():
    """The new keyword checks must route their own queries AND leave every
    pre-wave-3 category winning its own keywords (mechanism/concept especially)."""
    assert R.classify("injury report for New York Yankees") == "injury_report"
    assert R.classify("news context for the Lakers") == "news_context"
    assert R.classify("schedule context for LAL") == "schedule_context"
    assert R.classify("scouting report for Trae Young") == "scouting_report"
    assert R.classify("who is comparable to Trae Young") == "comparables"
    assert R.classify("preview NYY vs BOS") == "matchup_preview"
    # existing categories unchanged
    assert R.classify("best gravity") == "concept_rating"
    assert R.classify("Trae Young vs LaMelo Ball on gravity") == "concept_rating"
    assert R.classify("compare Trae Young and LaMelo Ball") == "concept_rating"
    assert R.classify("why is LaMelo Ball good at gravity") == "concept_rating"
    assert R.classify("final score of BOS vs PHI") == "historical_result"
    assert R.classify("what is the calibration brier score for nba") == "calibration_number"
    assert R.classify("win probability NYY vs BOS") == "prediction_winprob"
    assert R.classify("Trae Young gravity") == "player_stat"

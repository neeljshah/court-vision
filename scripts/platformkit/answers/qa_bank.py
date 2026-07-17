"""scripts.platformkit.answers.qa_bank -- the ANSWER-QUALITY REGRESSION BANK.

A DECLARED (data-only) bank of graded questions over
scripts.platformkit.answers.resolver_registry.resolve(), one entry per
(category, sport) combo across the registry's 12-category grid
(injury_report, news_context, schedule_context, scouting_report, comparables,
matchup_preview, prediction_winprob, calibration_number, ranking,
historical_result, mechanism_effect, system_map) x 5 sports (nba, mlb, wnba,
tennis, soccer) = 60 entries, PLUS 5 verified_claims rows (the 13th category,
the RESOLVER BRIDGE: provenance-by-claim_id + family discovery over the
auto-discovered intel_claims store -- 2 from the original bridge wave, 2 more
from wave-2/3 covering nba_venue_split provenance + a no-sport-token family
listing that surfaces line_history_consensus, 1 more from the light lane
covering nba_rest_adjusted_form provenance) and 3 depth-wave-1 rows (below
the grid, ids wnba_ranking_zone_context / mlb_mechanism_effect_injury_recency /
tennis_ranking_playstyle_fit) covering the new claim families, and 2
prediction_quality rows (the 14th category, 2026-07-17: fail-closed readout
of the pod-sprint prediction_eval artifact) -- 70, PLUS 4 more rows from the
2026-07-17 pod coverage-stress gap report (schedule_context interrogative
lead-in + article/code-resolution regressions, a prediction_quality word
-order classify() regression, and a mechanism_effect->claims-bridge grounding
row) -- 74 total.

Every `expect` block was GROUNDED by actually running the question once
through resolve() in this repo on 2026-07-17 (one long-lived process,
sport-grouped, see scratchpad probe script -- not committed, throwaway
harness). A correct `no_data`/`not_supported`/`ambiguous` IS the honest
current status for several rows (thin fixtures on a fresh box, sports not
wired for a category, etc.) -- qa_runner asserts the observed status stays in
`status_one_of`, not that everything resolves `ok`. If reality drifts (a
store gets built, a sport gets wired), UPDATE the expectation here to match
the new verified truth -- never weaken the runner to paper over a real
regression.

Includes the audit's named regression cases, each tagged in its `note`:
  - id nba_scouting_report: "scout report for Luka Doncik" (misspelled,
    gap-2/gap-5 lead-in-strip + ambiguous-name-not-swallowed regression)
  - id nba_schedule_context: "back to back for the Lakers" (gap-6 lead-in
    strip regression)
  - id nba_comparables: "players comparable to Steph Curry" (gap-3 nickname
    fuzzy-match regression)
  - id tennis_comparables: "players comparable to Roger Federer" (gap-1
    string entity_id CRASH regression -- tennis ids are slugs, not ints)

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    tests/platformkit/answers/test_qa_bank.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class QAExpect(TypedDict, total=False):
    category: str
    status_one_of: List[str]
    receipt_required: bool
    must_contain_keys: List[str]


class QAEntry(TypedDict):
    id: str
    question: str
    sport: str
    expect: QAExpect
    tier: str  # "SMOKE" | "FULL"


def _e(cat: str, sp: str, q: str, status: str, tier: str, keys: List[str] | None = None,
       note: str = "") -> QAEntry:
    return {
        "id": f"{sp}_{cat}",
        "question": q,
        "sport": sp,
        "expect": {
            "category": cat,
            "status_one_of": [status],
            "receipt_required": status == "ok",
            "must_contain_keys": keys or [],
        },
        "tier": tier,
        "note": note,
    }


QA_BANK: List[QAEntry] = [
    # -- injury_report ---------------------------------------------------
    _e("injury_report", "nba", "injury report for Lakers", "no_data", "SMOKE"),
    _e("injury_report", "mlb", "injury report for Yankees", "ok", "SMOKE",
       ["matched_entity", "rows", "as_of"]),
    _e("injury_report", "wnba", "injury report for Las Vegas Aces", "ok", "FULL",
       ["matched_entity", "rows", "as_of"]),
    _e("injury_report", "tennis", "injury report for Roger Federer", "no_data", "FULL"),
    _e("injury_report", "soccer", "injury report for Manchester City WFC", "no_data", "FULL"),

    # -- news_context -----------------------------------------------------
    _e("news_context", "nba", "news context for Lakers", "no_data", "FULL"),
    _e("news_context", "mlb", "news context for Yankees", "ok", "SMOKE",
       ["matched_entity", "rows", "as_of"]),
    _e("news_context", "wnba", "news context for Las Vegas Aces", "no_data", "FULL"),
    _e("news_context", "tennis", "news context for Roger Federer", "no_data", "FULL"),
    _e("news_context", "soccer", "news context for Manchester City WFC", "no_data", "FULL"),

    # -- schedule_context ---------------------------------------------------
    _e("schedule_context", "nba", "back to back for the Lakers", "ok", "SMOKE",
       ["rest_days", "is_b2b", "games_in_last_7"],
       note="regression: gap-6 lead-in strip for 'back to back for X' phrasing"),
    _e("schedule_context", "mlb", "schedule context for Yankees", "ok", "FULL",
       ["rest_days", "is_b2b", "games_in_last_7"],
       note="regression: 2026-07-17 pod coverage-stress gap -- 'Yankees' was never resolved to the "
            "calendar's own code (mlb had no free-text team-name resolution at all); now ok via "
            "team_resolver.canonical (was no_data)"),
    _e("schedule_context", "wnba", "schedule context for Las Vegas Aces", "not_supported", "FULL"),
    _e("schedule_context", "tennis", "schedule context for Roger Federer", "not_supported", "FULL"),
    _e("schedule_context", "soccer", "schedule context for Manchester City WFC", "not_supported", "FULL"),

    # -- scouting_report ------------------------------------------------
    _e("scouting_report", "nba", "scout report for Luka Doncik", "ambiguous", "SMOKE",
       ["candidates"],
       note="regression: gap-2/gap-5 -- misspelled name + 'scout report for' lead-in must "
            "surface AMBIGUOUS with candidates, never a false no_data"),
    _e("scouting_report", "mlb", "scouting report for Aaron Judge", "ok", "SMOKE",
       ["concept_axes", "raw_attributes", "shooting_facet"]),
    _e("scouting_report", "wnba", "scouting report for A'ja Wilson", "ok", "FULL",
       ["concept_axes", "raw_attributes", "shooting_facet"]),
    _e("scouting_report", "tennis", "scouting report for Roger Federer", "ok", "FULL",
       ["concept_axes", "raw_attributes", "shooting_facet"]),
    _e("scouting_report", "soccer", "scouting report for Erling Haaland", "no_data", "FULL"),

    # -- comparables --------------------------------------------------------
    _e("comparables", "nba", "players comparable to Steph Curry", "ok", "SMOKE",
       ["neighbors", "entity_id", "k"],
       note="regression: gap-3 -- nickname 'Steph Curry' must resolve via the shared "
            "ask.py fuzzy matcher, not comparables' own stricter one"),
    _e("comparables", "mlb", "players comparable to Aaron Judge", "ok", "FULL",
       ["neighbors", "entity_id", "k"]),
    _e("comparables", "wnba", "players comparable to A'ja Wilson", "ok", "FULL",
       ["neighbors", "entity_id", "k"]),
    _e("comparables", "tennis", "players comparable to Roger Federer", "ok", "SMOKE",
       ["neighbors", "entity_id", "k"],
       note="regression: gap-1 -- tennis entity_id is a string slug ('agassi_a'); "
            "must NOT crash on int(entity_id)"),
    _e("comparables", "soccer", "players comparable to Erling Haaland", "no_data", "FULL"),

    # -- matchup_preview ------------------------------------------------
    _e("matchup_preview", "nba", "preview Lakers vs Celtics", "ok", "FULL",
       ["blocks", "blocks_ok", "blocks_absent", "home", "away"]),
    _e("matchup_preview", "mlb", "preview Yankees vs Red Sox", "ok", "FULL",
       ["blocks", "blocks_ok", "blocks_absent", "home", "away"]),
    _e("matchup_preview", "wnba", "preview Las Vegas Aces vs New York Liberty", "ok", "FULL",
       ["blocks", "blocks_ok", "blocks_absent", "home", "away"]),
    _e("matchup_preview", "tennis", "preview Roger Federer vs Novak Djokovic", "ok", "FULL",
       ["blocks", "blocks_ok", "blocks_absent", "home", "away"]),
    _e("matchup_preview", "soccer", "preview Manchester City WFC vs Arsenal", "ok", "FULL",
       ["blocks", "blocks_ok", "blocks_absent", "home", "away"]),

    # -- prediction_winprob -----------------------------------------------
    _e("prediction_winprob", "nba", "win probability Lakers vs Celtics", "ok", "FULL",
       ["p_home_win", "pregame", "home", "away"]),
    _e("prediction_winprob", "mlb", "win probability Yankees vs Red Sox", "ok", "FULL",
       ["p_home_win", "pregame", "home", "away"]),
    _e("prediction_winprob", "wnba", "win probability Las Vegas Aces vs New York Liberty",
       "ok", "FULL", ["p_home_win", "pregame", "home", "away"]),
    _e("prediction_winprob", "tennis", "win probability Roger Federer vs Novak Djokovic",
       "ok", "FULL", ["p_home_win", "pregame", "home", "away"]),
    _e("prediction_winprob", "soccer", "win probability Manchester City WFC vs Arsenal",
       "ok", "FULL", ["p_home_win", "pregame", "home", "away"]),

    # -- calibration_number -------------------------------------------------
    _e("calibration_number", "nba", "what is the calibration brier score for nba", "ok", "SMOKE",
       ["baseline_brier", "improved_brier", "baseline_ece", "improved_ece"]),
    _e("calibration_number", "mlb", "what is the calibration brier score for mlb", "ok", "FULL",
       ["baseline_brier", "improved_brier", "baseline_ece", "improved_ece"]),
    _e("calibration_number", "wnba", "what is the calibration brier score for wnba", "no_data", "SMOKE"),
    _e("calibration_number", "tennis", "what is the calibration brier score for tennis", "ok", "FULL",
       ["baseline_brier", "improved_brier", "baseline_ece", "improved_ece"]),
    _e("calibration_number", "soccer", "what is the calibration brier score for soccer", "ok", "FULL",
       ["baseline_brier", "improved_brier", "baseline_ece", "improved_ece"]),

    # -- ranking --------------------------------------------------------
    _e("ranking", "nba", "top 5 assist leaders", "not_supported", "SMOKE", ["available"]),
    _e("ranking", "mlb", "top 5 assist leaders", "not_supported", "FULL", ["available"]),
    _e("ranking", "wnba", "top 5 assist leaders", "not_supported", "FULL", ["available"]),
    _e("ranking", "tennis", "top 5 assist leaders", "not_supported", "FULL", ["available"]),
    _e("ranking", "soccer", "top 5 assist leaders", "not_supported", "FULL", ["available"]),

    # -- historical_result --------------------------------------------------
    _e("historical_result", "nba", "final score of Lakers vs Celtics", "no_data", "SMOKE"),
    _e("historical_result", "mlb", "final score of Yankees vs Red Sox", "no_data", "FULL"),
    _e("historical_result", "wnba", "final score of Las Vegas Aces vs New York Liberty",
       "not_supported", "FULL"),
    _e("historical_result", "tennis", "final score of Roger Federer vs Novak Djokovic",
       "not_supported", "FULL"),
    _e("historical_result", "soccer", "final score of Manchester City WFC vs Arsenal",
       "not_supported", "FULL"),

    # -- mechanism_effect -------------------------------------------------
    _e("mechanism_effect", "nba", "what affects gravity", "not_supported", "SMOKE"),
    _e("mechanism_effect", "mlb", "what affects gravity", "not_supported", "FULL"),
    _e("mechanism_effect", "wnba", "what affects gravity", "not_supported", "FULL"),
    _e("mechanism_effect", "tennis", "what affects gravity", "not_supported", "FULL"),
    _e("mechanism_effect", "soccer", "what affects gravity", "not_supported", "FULL"),

    # -- system_map -----------------------------------------------------
    _e("system_map", "nba", "system map", "ok", "SMOKE", ["n_nodes", "n_edges", "nodes"]),
    _e("system_map", "mlb", "system map", "ok", "FULL", ["n_nodes", "n_edges", "nodes"]),
    _e("system_map", "wnba", "system map", "ok", "FULL", ["n_nodes", "n_edges", "nodes"]),
    _e("system_map", "tennis", "system map", "ok", "FULL", ["n_nodes", "n_edges", "nodes"]),
    _e("system_map", "soccer", "system map", "ok", "SMOKE", ["n_nodes", "n_edges", "nodes"]),

    # -- verified_claims (RESOLVER BRIDGE, 2026-07-17) --------------------
    # The two capabilities of the new category: provenance-by-claim_id (wrap
    # ask()) and family discovery. Both reach the auto-discovered intel_claims
    # store through resolve() -- the surface qa_runner actually calls -- which
    # the depth-wave-1 rows above documented as a known coverage gap now closed.
    _e("verified_claims", "wnba",
       "show the evidence for wnba_zone_context_zone_rim_efg_full_2026", "ok", "FULL",
       ["claim_id", "validator_verdict", "source_artifact"],
       note="bridge: provenance for a real VERIFIED wnba_zone_context claim_id via ask()"),
    _e("verified_claims", "tennis",
       "what claim families exist for tennis?", "ok", "FULL",
       ["families", "n_families", "source_artifact"],
       note="bridge: family discovery -- cheap per-store validation summaries, sport parsed from query"),
    _e("verified_claims", "nba",
       "show the evidence for nba_venue_split_home_minus_away_ppg_espn_boxscores_2023_24_to_2025_26",
       "ok", "FULL", ["claim_id", "validator_verdict", "source_artifact"],
       note="wave-2: provenance for a real VERIFIED nba_venue_split claim_id (DEN-altitude "
            "home-minus-away PPG sanity) via ask()"),
    _e("verified_claims", "soccer",
       "what claim families exist?", "ok", "FULL",
       ["families", "n_families", "source_artifact"],
       note="wave-3: family discovery, no sport token in the query -> lists all 77 families "
            "including line_history_consensus_claims (soccer+intl VERIFIED, tennis single-book "
            "reject) -- proves the bridge surfaces newest families without a per-sport query"),
]

# id collides with the "nba_venue_split" verified_claims row above (both are
# sport=nba, category=verified_claims, and _e()'s id is f"{sp}_{cat}") --
# appended separately with an explicit unique id, same pattern as the
# depth-wave-1 rows below.
QA_BANK.append({
    "id": "nba_rest_adjusted_form_verified_claims",
    "question": "show the evidence for nba_rest_adjusted_form_short_minus_long_rest_ppg_espn_boxscores_2023_24_to_2025_26",
    "sport": "nba",
    "expect": {"category": "verified_claims", "status_one_of": ["ok"], "receipt_required": True,
               "must_contain_keys": ["claim_id", "validator_verdict", "source_artifact"]},
    "tier": "FULL",
    "note": "light-lane: provenance for a real VERIFIED nba_rest_adjusted_form claim_id "
            "(short-rest-minus-long-rest PPG split) via ask()",
})

# -- depth-wave-1 claim families (2026-07-17) -----------------------------
# wnba_zone_context_claims / mlb_injury_recency_claims / tennis_playstyle_fit_claims
# live in data/cache/intel_claims/*.jsonl and are proven reachable, with
# receipts, through scripts.platformkit.intel_query.ask.ask() (auto-discovered
# by its filename-pairing convention -- verified for real on 2026-07-17:
# `ask("How do you know? Show the evidence for <claim_id>.")` -> answerable:True
# for all 3 families' claim_ids). resolver_registry.resolve() -- the ONLY
# surface qa_runner actually calls -- does NOT yet route to that store: its
# mechanism_effect resolver reads domains/<sport>/knowledge/validation_ledger.jsonl
# (a different store, unrelated hypothesis names) and wnba isn't even wired
# into _LEDGER_PATHS. The 3 rows below exercise the CLOSEST real resolve()
# reachable surface for each family (same underlying attribute for wnba's
# zone_rim_efg via the ranking/leaderboard path; an honest not_supported for
# mlb's evidence phrasing; the real ambiguous multi-attribute collision for
# tennis's "surface tilt") and record the true status -- this is a known
# resolver_registry coverage gap, not a bug in the new claim families
# themselves (all 3 are VERIFIED, n_mismatch=0, served correctly by ask()).
QA_BANK.append({
    "id": "wnba_ranking_zone_context",
    "question": "zone_rim_efg leaders",
    "sport": "wnba",
    "expect": {"category": "ranking", "status_one_of": ["ok"], "receipt_required": True,
               "must_contain_keys": ["attribute", "rows", "source_artifact"]},
    "tier": "FULL",
    "note": "depth-wave-1 wnba_zone_context_claims: same underlying zone_rim_efg attribute "
            "the claims family full-pop-ranks, reached here via the profiles/leaderboard path "
            "(not the intel_claims store itself -- that store is reachable via "
            "intel_query.ask.ask(), verified answerable:true separately, not yet wired into "
            "resolver_registry)",
})
QA_BANK.append({
    "id": "mlb_mechanism_effect_injury_recency",
    "question": "what does the evidence say about mlb_injury_recency_days_since_latest",
    "sport": "mlb",
    "expect": {"category": "mechanism_effect", "status_one_of": ["not_supported"], "receipt_required": False,
               "must_contain_keys": []},
    "tier": "FULL",
    "note": "depth-wave-1 mlb_injury_recency_claims: honest not_supported -- resolver_registry's "
            "mechanism_effect only matches domains/mlb/knowledge/validation_ledger.jsonl hypothesis "
            "names, a different store than data/cache/intel_claims/mlb_injury_recency_claims.jsonl. "
            "The claim IS answerable:true through intel_query.ask.ask() (verified separately) -- "
            "resolver_registry just doesn't route to that store yet, a known coverage gap.",
})
QA_BANK.append({
    "id": "tennis_ranking_playstyle_fit",
    "question": "surface tilt leaders",
    "sport": "tennis",
    "expect": {"category": "ranking", "status_one_of": ["ambiguous"], "receipt_required": False,
               "must_contain_keys": ["candidates"]},
    "tier": "FULL",
    "note": "depth-wave-1 tennis_playstyle_fit_claims: real ambiguous collision against the "
            "profiles registry's own surface_splits_{return,serve}_{Clay,Grass,Hard} attributes "
            "(a different store than the claim family's grass_wr-clay_wr formula in "
            "data/cache/intel_claims/tennis_playstyle_fit_claims.jsonl, which IS answerable:true "
            "through intel_query.ask.ask(), verified separately).",
})

QA_BANK.append({
    "id": "prediction_quality_readout",
    "question": "how good are the predictions?",
    "sport": "nba",
    "expect": {"category": "prediction_quality",
               "status_one_of": ["ok", "no_data"], "receipt_required": False,
               "must_contain_keys": []},
    "tier": "FULL",
    "note": "fail-closed readout of data/cache/prediction_eval/prediction_eval.json (written by "
            "pod_sprint.prediction_eval). no_data is the honest answer until the artifact is "
            "generated on this box; ok quotes the OOS scoreboard + eval-gate receipt verbatim.",
})
QA_BANK.append({
    "id": "prediction_quality_sport_filter",
    "question": "prediction quality for mlb",
    "sport": "mlb",
    "expect": {"category": "prediction_quality",
               "status_one_of": ["ok", "no_data"], "receipt_required": False,
               "must_contain_keys": []},
    "tier": "FULL",
    "note": "sport filter comes from the query text (sport_in_query), not resolve()'s sport "
            "default -- a bare quality question returns every sport's row.",
})

# -- 2026-07-17 pod coverage-stress gap report (5 answer-layer defects) ---
# Each row below was GROUNDED post-fix by actually running the question
# through resolver_registry.resolve() in this repo (see the defect-fix
# commit); a correct status that DIDN'T change (the catcher-framing row) is
# recorded honestly, not upgraded to a status the fix doesn't actually reach.
QA_BANK.append({
    "id": "nba_schedule_context_interrogative_lead_in",
    "question": "How many rest days do the Bucks have before their next game?",
    "sport": "nba",
    "expect": {"category": "schedule_context", "status_one_of": ["ok"], "receipt_required": True,
               "must_contain_keys": ["rest_days", "is_b2b", "games_in_last_7"]},
    "tier": "FULL",
    "note": "defect-1: an interrogative wrapper ('how many rest days do the X have...') left the "
            "ENTIRE question as the team string -- _LEAD_RE only matched a lead-in anchored at "
            "position 0. Now stripped via a new interrogative lead-in alternative plus a trailing "
            "-clause cut (was ok/no_data -- the whole sentence never matched a calendar row).",
})
QA_BANK.append({
    "id": "mlb_schedule_context_article_and_code",
    "question": "rest days for the Astros",
    "sport": "mlb",
    "expect": {"category": "schedule_context", "status_one_of": ["ok"], "receipt_required": True,
               "must_contain_keys": ["rest_days", "is_b2b", "games_in_last_7"]},
    "tier": "FULL",
    "note": "defect-1: the leading article strip was nba-only (schedule_context_resolver's 'the' "
            "regex only ran inside the nba branch), and mlb had zero free-text team-name -> "
            "calendar-code resolution -- 'the Astros' now resolves to code HOU via "
            "team_resolver.canonical (was no_data, team='the Astros').",
})
QA_BANK.append({
    "id": "wnba_prediction_quality_word_order",
    "question": "how good are the WNBA predictions",
    "sport": "wnba",
    "expect": {"category": "prediction_quality", "status_one_of": ["ok", "no_data"], "receipt_required": False,
               "must_contain_keys": []},
    "tier": "FULL",
    "note": "defect-2: the sport token inserted mid-phrase ('how good are the WNBA predictions') "
            "defeated the literal 'how good are the predictions' string match, so the bare "
            "'predict' substring in _PREDICTION_KEYWORDS won first -> prediction_winprob. classify() "
            "now also fires prediction_quality whenever a query names both 'how good' and a "
            "'predict*' token, in either order. no_data is the honest status until "
            "prediction_eval.json is generated on this box (was category=prediction_winprob).",
})
QA_BANK.append({
    "id": "mlb_catcher_framing_mechanism_effect",
    "question": "what does the evidence say about catcher framing runs saved",
    "sport": "mlb",
    "expect": {"category": "mechanism_effect", "status_one_of": ["not_supported"], "receipt_required": False,
               "must_contain_keys": []},
    "tier": "FULL",
    "note": "defect-3: resolve() now falls back to claims_resolver.resolve() (the VERIFIED-claims "
            "bridge) whenever mechanism_effect returns not_supported/no_data -- correctness proven "
            "via a monkeypatched unit test. Grounded here for real: this EXACT phrasing stays "
            "honestly not_supported even with the bridge wired, because intel_query.ask's family "
            "classifier needs a 'top N' shape or an explicit claim_id/'how do you know' phrasing, "
            "and free-text 'what does the evidence say about X' matches neither -- a separate, "
            "out-of-scope gap in ask()'s NL matching, not in this fallback. The catcher_framing "
            "family IS reachable (verified live: 'top 10 catcher framing' -> answerable), just not "
            "through this literal sentence. Status unchanged by the fix; recorded honestly.",
})

CATEGORIES: List[str] = sorted({e["expect"]["category"] for e in QA_BANK})
SPORTS: List[str] = sorted({e["sport"] for e in QA_BANK})


def by_tier(tier: str) -> List[QAEntry]:
    """SMOKE entries (~15, no-subprocess-cost categories only) or FULL (all 67)."""
    if tier == "FULL":
        return list(QA_BANK)
    return [e for e in QA_BANK if e["tier"] == tier]

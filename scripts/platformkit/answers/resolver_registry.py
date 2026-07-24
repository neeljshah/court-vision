"""LANE D -- canonical resolver registry: every supported question TYPE maps
to exactly ONE resolver (source artifact + computation rule + units/rounding
+ as-of stamp). An unregistered question type returns NOT_SUPPORTED --
never improvised. This is the top of the answer-engine stack; it dispatches
to (never re-implements) the systems that already exist:

    player_stat / rating_attribute -> scripts.platformkit.profiles.ask (single
        attribute row: raw_value is the fact, rating_2k is presentation-only)
    concept_rating   -> scripts.platformkit.answers.contracts (scouting
        composite: superlative/comparison/explanation/fit)
    prediction_winprob -> scripts/platformkit/predict_matchup.py, invoked as a
        subprocess (never imported here -- contracts.py's own guard test
        proves the concept engine stays decoupled from forecast engines, and
        this module keeps the same separation)
    calibration_number -> the pinned scoreboard artifact
        vault/_Organized/_Index/_Calibration_Scoreboard.md (parsed, not
        recomputed live -- recomputation is calibration-report's job)
    historical_result -> data/domains/<sport>/{linescores,games}.parquet
        (final score / W-L, read directly, no derived number)
    mechanism_effect  -> domains/<sport>/knowledge/validation_ledger.jsonl
        ("does mechanism X hold up locally" -- verbatim ledger row(s):
        verdict/effect/n/p/corpus/note, LOCAL-only framing baked into the
        answer, never improvised for an unregistered mechanism)
    analytics_attribution / analytics_claim_survival / analytics_verification /
    analytics_contradictions -> scripts.platformkit.analytics_verify.answers
        (LANE E; fail-closed over data/cache/analytics_verify/*.json --
        no_data if the artifact is absent, refused if it isn't stamped
        edge_claimed:false or is older than the staleness bound)
    system_map -> scripts.platformkit.analytics_verify.answers.system_map
        (LANE F; the declared, disk-verified dataflow graph -- "how does the
        system work" / "what produces X" / "what consumes Y", same fail-closed
        gate as the other analytics_verify categories)
    injury_report / news_context -> scripts.platformkit.answers.edge_facts_resolver
        (fail-closed over data/cache/edge_engine/*_facts_<sport>.jsonl -- verbatim
        rows, absent store -> no_data, >7d-stale newest row -> refused)
    schedule_context -> scripts.platformkit.answers.schedule_context_resolver
        (rest/b2b/density computed off the public games calendar -- descriptive only)
    scouting_report  -> scripts.platformkit.intel_query.compose_scout (multi-axis
        descriptive VECTOR: concept ratings + shooting facet + raw attrs, never combined)
    comparables      -> scripts.platformkit.intel_query.compose_comparables
        (K nearest players by RMS Euclidean over shared attribute percentiles)
    matchup_preview  -> scripts.platformkit.intel_query.compose_matchup (fan-out of
        win_prob + team profiles + style + injuries + schedule, each quoted verbatim)
    prediction_winprob -> scripts.platformkit.answers.winprob_dispatch (subprocess
        over predict_matchup.py; authors no new number, quotes the probability verbatim)
    edge_language     -> always REFUSED (see .claude/rules/no-edge-claims.md)
    atlas_card        -> scripts.platformkit.answers.atlas_resolver (name-normalized
        entity lookup across every built analytics_showcase atlas manifest --
        card_path + key_numbers + floors quoted verbatim, never recomputed)

Every resolve() call returns one envelope shape:
    {status: "ok"|"refused"|"not_supported"|"no_data",
     category, sport, source_artifact, as_of, ...category-specific fields}
"pinned" categories name a MTIME as_of; the answer is only as fresh as that file.
"""
from __future__ import annotations

import difflib
import json
import os
import re
from datetime import datetime, timezone

import pandas as pd

from scripts.platformkit.analytics_verify import answers as _analytics
from scripts.platformkit.answers import atlas_resolver as _atlas
from scripts.platformkit.answers import claims_resolver as _claims
from scripts.platformkit.answers import conditional_winprob_resolver as _conditional_winprob
from scripts.platformkit.answers import contracts as _contracts
from scripts.platformkit.answers import edge_facts_resolver as _edge_facts
from scripts.platformkit.answers import effect_graph as _eg
from scripts.platformkit.answers import h2h_history_resolver as _h2h_history
from scripts.platformkit.answers import leaderboard_resolver as _lb
from scripts.platformkit.answers import player_compare as _pc
from scripts.platformkit.answers import schedule_context_resolver as _schedule
from scripts.platformkit.answers import streaks_resolver as _streaks
from scripts.platformkit.answers import winprob_dispatch as _winprob
from scripts.platformkit.answers.registry_loader import SPORTS as _CONCEPT_SPORTS
from scripts.platformkit.intel_query import compose_comparables as _comparables
from scripts.platformkit.intel_query import compose_matchup as _matchup
from scripts.platformkit.intel_query import compose_scout as _scout
from scripts.platformkit.profiles import ask as _ask

# ---------------------------------------------------------------------------
# Retracted-number / edge-language guard (binding list, .claude/rules/no-edge-claims.md)
# ---------------------------------------------------------------------------
RETRACTED_NUMBERS = ("18.38", "0.119", "+54%", "54%", "78.11", "8.94", "54.57")
EDGE_KEYWORDS = ("edge", "roi", "beat the market", "beat the close", "profit",
                 "positive ev", "+ev", "bankroll", "win rate over market")


def _word_boundary_hit(text: str, keyword: str) -> bool:
    """True if `keyword` occurs in `text` as a whole word/phrase, not merely
    as a substring of a longer word (e.g. "edge" must not fire on "ledger",
    "ece" must not fire on "receipt"). A trailing '*' marks a deliberate stem
    match (e.g. "calibrat*" matches calibration/calibrated/calibrating) --
    only its left edge is boundary-checked."""
    stem = keyword.endswith("*")
    kw = keyword[:-1] if stem else keyword
    left = r"(?<![A-Za-z0-9])" if kw[0].isalnum() else ""
    right = "" if stem else (r"(?![A-Za-z0-9])" if kw[-1].isalnum() else "")
    return re.search(left + re.escape(kw) + right, text) is not None


def is_edge_language(text: str) -> str | None:
    """Returns the matched forbidden token, or None. Checked BEFORE
    classification so an edge-flavored question never reaches a resolver."""
    low = text.lower()
    for tok in RETRACTED_NUMBERS:
        if tok in low:
            return tok
    for tok in EDGE_KEYWORDS:
        if _word_boundary_hit(low, tok):
            return tok
    return None


# ---------------------------------------------------------------------------
# The registry: category name -> resolver metadata (deliverable 1)
# ---------------------------------------------------------------------------
RESOLVERS: dict[str, dict] = {
    "player_stat": {
        "resolver": "scripts.platformkit.profiles.ask.answer_lookup",
        "source_artifact": "data/cache/profiles/<sport>_{player,team,lineup}_profiles.parquet",
        "computation": "raw_value column for the fuzzy-matched entity+attribute+window row",
        "units": "attribute-native (see attribute_registry.py per sport)", "rounding": "as stored, no rounding",
    },
    "rating_attribute": {
        "resolver": "scripts.platformkit.profiles.ask.answer_lookup",
        "source_artifact": "data/cache/profiles/<sport>_{player,team,lineup}_profiles.parquet",
        "computation": "percentile + rating_2k (25 + percentile*0.74) for the same matched row",
        "units": "percentile 0-100; rating_2k 25-99 (presentation-only, never causal/predictive)",
        "rounding": "2 decimals",
    },
    "concept_rating": {
        "resolver": "scripts.platformkit.answers.contracts.answer_question",
        "source_artifact": "derived from the profiles parquet via domains/<sport>/concepts/concept_registry.py",
        "computation": "status-rank x n-shrinkage weighted composite across a concept's declared signals",
        "units": "composite score 0-100 (percentile-weighted, not a raw unit)", "rounding": "2 decimals",
    },
    "prediction_winprob": {
        "resolver": "scripts/platformkit/predict_matchup.py (subprocess CLI)",
        "source_artifact": "domains/<sport>/predictor.py via scripts.platformkit.predictor_jd._build_predictor",
        "computation": "calibrated pregame probability; in-game adds the validated repricer given a live score state",
        "units": "probability 0-1", "rounding": "4 decimals",
    },
    "calibration_number": {
        "resolver": "resolver_registry.calibration_number (parses the pinned scoreboard)",
        "source_artifact": "vault/_Organized/_Index/_Calibration_Scoreboard.md",
        "computation": "per-sport Brier/ECE baseline vs improved, from the last calibration-report run",
        "units": "Brier score / ECE, both 0-1 (lower is better calibrated)", "rounding": "5 decimals as printed",
    },
    "historical_result": {
        "resolver": "resolver_registry.historical_result",
        "source_artifact": "data/domains/basketball_nba/linescores.parquet | data/domains/mlb/games.parquet",
        "computation": "final score read directly off the boxscore/linescore row for the matched game",
        "units": "points (NBA) / runs (MLB), integers", "rounding": "none -- integer score",
    },
    "mechanism_effect": {
        "resolver": "resolver_registry.mechanism_effect",
        "source_artifact": "domains/<sport>/knowledge/validation_ledger.jsonl",
        "computation": "verbatim lookup of the matched hypothesis row(s) -- verdict/effect/n/p/corpus/note, "
                        "as written by the mechanism validators; never recomputed, never improvised",
        "units": "effect size + n + p as stored (sport/spec-native, see each row's 'note' for what was measured)",
        "rounding": "none -- verbatim from the ledger row",
    },
    "edge_language": {
        "resolver": None,
        "source_artifact": ".claude/rules/no-edge-claims.md",
        "computation": "ALWAYS REFUSED -- no resolver computes a dollar edge/ROI/beat-the-market number here",
        "units": "n/a", "rounding": "n/a",
    },
    "ranking": {
        "resolver": "scripts.platformkit.answers.leaderboard_resolver.resolve_query",
        "source_artifact": "data/cache/profiles/<sport>_{player,team,lineup}_profiles.parquet",
        "computation": "top-N by ONE registered attribute's raw_value, min_n volume floor on top of the "
                        "attribute's own baked-in floor, deterministic (raw_value,entity_id) tie-break -- a "
                        "fuzzy category word that matches 0 or 2+ attributes is REFUSED with candidates, never guessed",
        "units": "attribute-native (see attribute_registry.py per sport)", "rounding": "as stored, no rounding",
    },
    "analytics_attribution": {
        "resolver": "scripts.platformkit.analytics_verify.answers.attribution",
        "source_artifact": "data/cache/analytics_verify/attribution_rollup.json",
        "computation": "verbatim by_family[family] / by_card[card_id] CLV-attribution receipt -- never recomputed",
        "units": "receipt-native (mean/median CLV pct, beat-close pct, counts, as stored)",
        "rounding": "none -- verbatim from artifact",
    },
    "analytics_claim_survival": {
        "resolver": "scripts.platformkit.analytics_verify.answers.claim_survival",
        "source_artifact": "data/cache/analytics_verify/claim_survival.json",
        "computation": "verbatim card-decay scoreboard -- verdict counts + 7d/30d/60d survival fractions",
        "units": "counts + fractions, as stored", "rounding": "none -- verbatim from artifact",
    },
    "analytics_verification": {
        "resolver": "scripts.platformkit.analytics_verify.answers.verification",
        "source_artifact": "data/cache/analytics_verify/sentinel_report.json",
        "computation": "verbatim sentinel re-derivation check(s) -- served_value vs recomputed_value + verdict",
        "units": "stat-native served/recomputed values + verdict enum", "rounding": "none -- verbatim from artifact",
    },
    "analytics_contradictions": {
        "resolver": "scripts.platformkit.analytics_verify.answers.contradictions",
        "source_artifact": "data/cache/analytics_verify/contradiction_report.json",
        "computation": "verbatim conflict rows from the cross-claim consistency scan, optionally filtered by family",
        "units": "n/a -- structured conflict records", "rounding": "none -- verbatim from artifact",
    },
    "system_map": {
        "resolver": "scripts.platformkit.analytics_verify.answers.system_map",
        "source_artifact": "data/cache/analytics_verify/system_map.json",
        "computation": "verbatim node/edge lookup on the declared, disk-verified dataflow graph "
                        "(scripts/platformkit/analytics_verify/system_map.py); whole-graph summary if no node given",
        "units": "n/a -- structured graph nodes/edges", "rounding": "none -- verbatim from artifact",
    },
    "injury_report": {
        "resolver": "scripts.platformkit.answers.edge_facts_resolver.injury_report",
        "source_artifact": "data/cache/edge_engine/injury_facts_<sport>.jsonl",
        "computation": "newest-first injury-status rows for a team/player, verbatim off the fact store "
                        "(fail-closed: absent store -> no_data, newest row older than 7d -> refused)",
        "units": "status/detail/report_date strings, as stored", "rounding": "none -- verbatim from artifact",
    },
    "news_context": {
        "resolver": "scripts.platformkit.answers.edge_facts_resolver.news_context",
        "source_artifact": "data/cache/edge_engine/news_facts_<sport>.jsonl",
        "computation": "newest-first news items mentioning a team/player, verbatim off the fact store "
                        "(same 7d staleness gate as injury_report)",
        "units": "headline/url/published strings, as stored", "rounding": "none -- verbatim from artifact",
    },
    "schedule_context": {
        "resolver": "scripts.platformkit.answers.schedule_context_resolver.resolve",
        "source_artifact": "data/domains/basketball_nba/linescores.parquet | data/domains/mlb/games.parquet",
        "computation": "rest_days / back-to-back / games-in-last-7 computed directly off the public games "
                        "calendar, plus VERIFIED nba_schedule_claims rows -- descriptive schedule physics only",
        "units": "days (rest_days) + game counts, integers", "rounding": "none -- integer counts",
    },
    "scouting_report": {
        "resolver": "scripts.platformkit.intel_query.compose_scout.compose_scout",
        "source_artifact": "data/cache/profiles/<sport>_player_profiles.parquet",
        "computation": "multi-axis descriptive scouting VECTOR (per-concept rating+percentile, shooting facet, "
                        "raw attribute percentiles) -- axes are NEVER combined into one score",
        "units": "per-axis composite 0-100 + percentiles", "rounding": "2 decimals (composite), 1 (percentile)",
    },
    "comparables": {
        "resolver": "scripts.platformkit.intel_query.compose_comparables.compose_comparables",
        "source_artifact": "data/cache/profiles/<sport>_player_profiles.parquet",
        "computation": "K nearest players by RMS Euclidean over shared attribute percentiles "
                        "(>=5 shared-attribute floor) -- descriptive 'similar profile', never a projection",
        "units": "RMS percentile-point distance", "rounding": "4 decimals",
    },
    "verified_claims": {
        "resolver": "scripts.platformkit.answers.claims_resolver.resolve",
        "source_artifact": "data/cache/intel_claims/*.jsonl (+ *_validation.json), via intel_query.ask.ask()",
        "computation": "wraps the auto-discovering, fail-closed VERIFIED-claims engine (ask()) -- authors no "
                        "new number: quotes the claim_id + ranking excerpt + caveats + validator verdict "
                        "verbatim; 'what claim families exist' lists each store's cheap validation summary",
        "units": "claim-native (ranking rows/caveats as stored)", "rounding": "none -- verbatim from the claim row",
    },
    "prediction_quality": {
        "resolver": "scripts.platformkit.answers.prediction_quality_resolver.resolve",
        "source_artifact": "data/cache/prediction_eval/prediction_eval.json",
        "computation": "quotes the fail-closed prediction-eval artifact verbatim: OOS leak-free scoreboard "
                        "(Brier/RMSE vs tuned baseline / naive mean) + eval-gate receipt; artifact absent or "
                        "blocked -> no_data, never recomputed here",
        "units": "Brier (binary) / RMSE (expected-score), as stored", "rounding": "none -- verbatim",
    },
    "player_comparison": {
        "resolver": "scripts.platformkit.answers.player_compare.compare",
        "source_artifact": "data/cache/profiles/<sport>_player_profiles.parquet",
        "computation": "reuses profiles/ask.py's fuzzy attribute matcher on the leftover query tokens; if a "
                        "metric resolves, returns both entities' raw_value + which is higher; if none resolves, "
                        "a declared default shared-attribute side-by-side (intersection, capped) -- never a "
                        "single-sided guess, and both sides must be the SAME sport",
        "units": "attribute-native per row (see attribute_registry.py per sport)", "rounding": "4 decimals",
    },
    "matchup_preview": {
        "resolver": "scripts.platformkit.intel_query.compose_matchup.compose_matchup",
        "source_artifact": "scripts/platformkit/intel_query/compose_matchup.py (fan-out over shipped resolvers)",
        "computation": "assembles win_prob + team profiles + style_matchup + injuries + schedule context, each "
                        "quoted verbatim under its own block; a block's no_data never fails the overall preview",
        "units": "per-block native (see each block's own envelope)", "rounding": "none -- verbatim from blocks",
    },
    "h2h_history": {
        "resolver": "scripts.platformkit.answers.h2h_history_resolver.resolve",
        "source_artifact": "data/domains/basketball_nba/linescores.parquet | data/domains/mlb/games.parquet | "
                            "data/domains/soccer/matches.parquet | data/domains/tennis/atlas_h2h.parquet",
        "computation": "series aggregate over every completed meeting between a team/player PAIR -- games played, "
                        "W/L(/D) split, mean+cumulative point/run/goal differential (home- and pair-perspective), "
                        "last-5 form, and (tennis) a per-surface split; complements historical_result (ONE game's "
                        "score) and matchup_preview's h2h/head-to-head route (the predictive fan-out), zero rows "
                        "-> no_data, never fabricated",
        "units": "games/wins native counts; differential in points(NBA)/runs(MLB)/goals(soccer)",
        "rounding": "differential mean 2 decimals, cumulative integer",
    },
    "conditional_winprob": {
        "resolver": "scripts.platformkit.answers.conditional_winprob_resolver.resolve",
        "source_artifact": "data/domains/basketball_nba/games.parquet | data/domains/mlb/games.parquet | "
                            "data/domains/soccer/matches.parquet",
        "computation": "descriptive P(home win) split by rest bucket (b2b vs non-b2b, plus a b2b_or_1d/2-3d/4d_plus "
                        "table) computed directly off the public games calendar -- NOT a conditional path inside "
                        "predict_matchup.py (it has none); n + Wilson 95% CI per cell so a thin split is visible, "
                        "calibration language only, never a market edge or an invented conditional probability",
        "units": "probability 0-1 + integer n per cell", "rounding": "4 decimals",
    },
    "streaks": {
        "resolver": "scripts.platformkit.answers.streaks_resolver.resolve",
        "source_artifact": "data/domains/basketball_nba/linescores.parquet | data/domains/mlb/games.parquet | "
                            "data/domains/soccer/matches.parquet",
        "computation": "per-team season game-log streaks off the public games calendar -- longest win streak, "
                        "longest loss streak, and current (trailing) streak, scoped to one season (as_of's season "
                        "or the most recent on file, leak-free truncation to games before as_of); descriptive only",
        "units": "consecutive-game counts (integers); draws break both streaks", "rounding": "none -- integer counts",
    },
    "atlas_card": {
        "resolver": "scripts.platformkit.answers.atlas_resolver.resolve",
        "source_artifact": "scripts/platformkit/analytics_showcase/out/atlas_*_manifest.json",
        "computation": "name-normalized entity lookup across every built atlas manifest -- returns "
                        "card_path + key_numbers + floors verbatim from the matched entry, never "
                        "recomputed; entity absent from every manifest -> no_data, never fuzzy-invented",
        "units": "manifest-native key_numbers (see each atlas_*.py builder for its own units)",
        "rounding": "none -- verbatim from the manifest entry",
    },
}

# "sharpest" (2026-07-18, coverage_stress Family D): a bare superlative
# adjective with no "best" token ("who is the sharpest shooter?") was falling
# through every classify() branch to the default player_stat shape (an
# honest but wrong "no_entity" refusal -- "sharpest shooter" isn't a player
# name). Added alongside "best" rather than a new branch: same superlative
# question shape, same concept_rating->leaderboard-fallback handling below.
_CONCEPT_KEYWORDS = ("best", "sharpest", "who has", "vs ", " versus ", "why is", "fit team", "does ", "compare")
_PREDICTION_KEYWORDS = ("win probability", "who wins", "will win", "predict", "forecast", "project the",
                        "spread", "moneyline", "odds for")
_CALIBRATION_KEYWORDS = ("brier", "ece", "calibrat*")
_PREDICTION_QUALITY_KEYWORDS = ("prediction quality", "how good are the predictions", "prediction eval",
                                "oos readout", "oos scoreboard", "vs the close", "versus the close")
_HISTORICAL_KEYWORDS = ("final score", "what happened", "box score", "result of", "score of the game",
                        "who won on", "final of")
# h2h_history (Family 1, NEW) -- a SERIES aggregate ("historical/all-time
# record", "run/goal/point differential"), distinct from historical_result's
# ONE-game score above and from matchup_preview's bare "h2h"/"head-to-head"
# preview route below. Checked right after historical_result (specific
# phrasing, no token overlap with either) and BEFORE _MATCHUP_PREVIEW_KEYWORDS
# so a compound phrase like "head-to-head goal differential" is intercepted
# here, not lost to the predictive preview -- matchup_preview keeps every
# bare h2h/head-to-head query that names no differential/historical/series
# token (never stolen).
_H2H_HISTORY_KEYWORDS = ("run differential", "goal differential", "point differential",
                         "historical h2h", "historical head-to-head", "historical head to head",
                         "all-time record", "all time record", "head-to-head record", "h2h record",
                         "leads the series", "series record", "historical record")
# streaks (NEW) -- per-team season win/loss streak off the games calendar.
# The word "streak" appears in no other keyword list in this file (grepped), so
# this is unambiguous; checked right after h2h_history (both are descriptive
# game-log lookups) and BEFORE is_ranking_query's "longest"/"most" cues so
# "longest win streak" reaches the streaks resolver, not the leaderboard.
_STREAK_KEYWORDS = ("streak", "win streak", "winning streak", "losing streak",
                    "loss streak", "won in a row", "lost in a row", "games in a row")
# conditional_winprob (Family 2, NEW) -- descriptive rest-conditioned win-rate
# delta ("how does win prob change on a back-to-back/short rest"). Checked
# BEFORE _PREDICTION_KEYWORDS (a literal "win probability" naming a rest
# condition must not fall to the single point-forecast prediction_winprob
# route) and therefore also before _SCHEDULE_KEYWORDS's bare "back-to-back"/
# "b2b"/"rest days" tokens (checked much later) -- a per-team rest-days
# LOOKUP ("rest days for the Bucks") still routes to schedule_context
# unaffected, since none of ITS phrasings appear here.
# "on a b2b"/"on a back-to-back" are ALSO the existing, documented per-team
# schedule_context shape ("Are the Lakers ON a back-to-back tonight?" --
# see _TRAIL_RE's own docstring example below) -- those two phrases only
# count as conditional_winprob when paired with an explicit win-rate/
# probability signal word; unpaired, they stay the unchanged schedule lookup.
_CONDITIONAL_KEYWORDS = ("on short rest", "on rest", "rest help")
_CONDITIONAL_AMBIGUOUS_KEYWORDS = ("on a b2b", "on a back-to-back", "on a back to back")
_CONDITIONAL_SIGNAL_KEYWORDS = ("win prob", "win rate", "does win", "home win")
_MECHANISM_KEYWORDS = ("evidence", "mechanism", "hypothesis", "folklore",
                       "hold up", "does the data support", "is it true that")
_ANALYTICS_ATTRIBUTION_KEYWORDS = ("attribution", "clv attribution", "link method", "join rate")
_ANALYTICS_SURVIVAL_KEYWORDS = ("claim survival", "card decay", "decayed card", "survival rate")
_ANALYTICS_VERIFICATION_KEYWORDS = ("sentinel", "verification check", "discrepant", "recomputed value")
_ANALYTICS_CONTRADICTION_KEYWORDS = ("contradiction", "conflicting claim", "inconsistent claim")
_SYSTEM_MAP_KEYWORDS = ("system map", "how does the system", "what produces", "what consumes",
                        "dataflow", "data flow")
# --- intel categories (wave 3). Keyed on words no earlier check uses so they
# never shadow (and are never shadowed by) the existing specific categories.
# matchup_preview/comparables sit BEFORE concept_rating in classify() because a
# preview query ("preview X vs Y") also contains concept's generic "vs " token
# -- but "preview"/"matchup"/"comparable" appear in no concept keyword, so a
# real concept question ("X vs Y on gravity") still falls through to concept.
_INJURY_KEYWORDS = ("injury report", "injury status", "injuries for", "injuries of", "is injured", "hurt list",
                    "out tonight",
                    # 2026-07-18 coverage_stress extension: real bank phrasings naming
                    # "injur*" in a shape none of the phrases above catch ("documented
                    # injuries", "injury history", "injury designation", "due to
                    # injury") were falling through to the player_stat default shape
                    # (an honest but avoidable no_data -- these never name a real
                    # registered attribute either).
                    "documented injuries", "injury history", "injury designation", "due to injury")
# "Is <Name> injured [right now]?" -- the name sits BETWEEN "is" and "injured",
# so the plain substring check above (which needs the literal phrase "is
# injured" adjacent) never fires on real phrasing. Captures the name so
# resolve() can pass it as player= (a personal name, never a team) instead of
# the team= extraction the older "injury report for <team>" lead-in uses.
_INJURY_IS_RE = re.compile(r"\bis\s+(.+?)\s+injured\b", re.I)
# Same "is <Name> ..." shape, different tail ("Is Sabrina Ionescu currently
# dealing with any documented injuries?", "Is Caitlin Clark listed with any
# injury designation right now?" -- real bank phrasing, 2026-07-18). Gated on
# an explicit injur* token elsewhere in the query so it never steals an
# unrelated "is X currently the MVP"-shaped question.
_INJURY_IS_BROAD_RE = re.compile(
    r"\bis\s+(.+?)\s+(?:currently\s+dealing\s+with|listed\s+with|dealing\s+with)\b", re.I)
_NEWS_KEYWORDS = ("news context", "latest news", "news about", "news for", "recent news")
_SCHEDULE_KEYWORDS = ("schedule context", "rest days", "back to back", "back-to-back", "b2b",
                      "days of rest", "schedule for",
                      # Family 3 extension (home/road split) -- schedule_split_extend keeps
                      # this ONE category (schedule_context), just a wider keyword net; the
                      # split-specific sub-phrases below double as the resolve()-time switch
                      # (_SCHEDULE_SPLIT_KEYWORDS) between rest/b2b vs home/road split.
                      "home road split", "home/road split", "home-road balance", "home road balance",
                      "second half of the season", "home stand", "road trip", "remaining schedule",
                      "home games in the second half", "road games in the second half",
                      "home-heavy", "home heavy", "road-heavy", "road heavy")
# Sub-phrases of _SCHEDULE_KEYWORDS above that mean "home/road split", not
# "rest/b2b" -- resolve()'s schedule_context branch checks this list to pick
# schedule_context_resolver.home_road_split() over its plain resolve().
_SCHEDULE_SPLIT_KEYWORDS = ("home road split", "home/road split", "home-road balance", "home road balance",
                            "second half of the season", "home stand", "road trip", "remaining schedule",
                            "home games in the second half", "road games in the second half",
                            "home-heavy", "home heavy", "road-heavy", "road heavy")
_SCOUT_KEYWORDS = ("scouting report", "scout report", "scouting")
_COMPARABLES_KEYWORDS = ("comparable", "comparables", "similar players", "similar to", "player comp")
_MATCHUP_PREVIEW_KEYWORDS = ("preview", "matchup preview", "matchup between", "game preview",
                             "head-to-head", "head to head", "h2h")
# "what affects Y" / "what does X affect" -- effect-graph queries (LANE C5),
# routed through the SAME mechanism_effect category (verbatim graph edges are
# just another ledger-backed receipt, not a new resolver family).
_AFFECTS_RE = re.compile(r"^\s*what affects\s+(.+?)\s*\??\s*$", re.I)
_WHAT_DOES_X_AFFECT_RE = re.compile(r"^\s*what does\s+(.+?)\s+affect\s*\??\s*$", re.I)
# --- verified_claims (RESOLVER BRIDGE): reach the auto-discovered VERIFIED
# claim families (intel_query.ask). Two triggers, both conservative:
#  1. provenance BY an explicit claim_id -- placed BEFORE mechanism_effect
#     because bare "evidence" is a mechanism keyword; gating on a snake_case
#     claim_id token means prose mechanism queries ("evidence about clutch
#     usage compression") are NEVER intercepted (they carry no claim_id).
#  2. discovery/family words -- placed at the END so it never shadows an
#     earlier specific category; "claim(s)"/"claim family" appear in no other
#     keyword set (verified via the full classify regression battery).
_CLAIM_ID_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9-]+){2,}\b", re.I)
_CLAIM_PROVENANCE_RE = re.compile(
    r"\b(how do you know|show (?:me )?(?:the )?evidence|prove|provenance|verified claim)\b", re.I)
_VERIFIED_CLAIMS_KEYWORDS = ("verified claim", "claim family", "claim families", "list claim")
_CLAIM_WORD_RE = re.compile(r"\bclaims?\b", re.I)
# Referee/official vocabulary -> verified_claims (the nba_referee_crew_ft
# family is the ONLY referee data surface). Checked before is_ranking_query
# so "top officials by ..." reaches the claims store instead of the
# leaderboard resolver. Singular "official" deliberately excluded ("official
# injury report" must keep routing to injury_report).
_REFEREE_RE = re.compile(r"\b(referees?|refs|officials|officiating|officiated|crew chief)\b", re.I)
# 2026-07-19 merge -- 3 new claim families (shooter_composite_v2_asof_approx,
# nba_context_shooting_defadj, nba_lineup_context) whose obvious phrasings were
# swallowed by is_ranking_query/concept_rating's generic "best"/"leaders"
# checks below BEFORE ever reaching the verified_claims/ask() engine that
# actually has the answer (a no_data/not_supported false gap, not missing
# data). Checked before both -- deliberately narrow (specific new-family
# phrases only, not a bare "best"/"top" catch-all) so it does NOT re-route
# "top 5 gravity" or "top shooters" (both already correctly answered by the
# ranking/leaderboard_resolver profile-attribute composite -- a real, shipped,
# DIFFERENT mechanism from the intel_claims store; see
# test_leaderboard_resolver.py's test_live_top5_gravity_via_resolve_entrypoint
# and test_live_top_shooters_resolves_composite_never_improvised).
_CLAIMS_REROUTE_RE = re.compile(
    r"\bbest shooters?\b|\bshooter composite\b|\bbest shooter ranking\b|"
    r"\bdefense[- ]adjusted (?:true shooting|ts)\b|"
    r"\bon[- ]off net rating\b|\bon/off impact\b",
    re.I)


def classify(query: str) -> str | None:
    """category name, or None if no rule matches (-> NOT_SUPPORTED). Checked
    in priority order: edge language first (a refusal always wins), then
    prediction/calibration/historical (specific phrasing), then concept vs.
    plain stat (concept needs an explicit shape word; a bare "<entity>
    <attribute>" query is player_stat/rating_attribute, resolved by ask.py's
    own fuzzy matcher, not by this classifier)."""
    if is_edge_language(query):
        return "edge_language"
    low = query.lower()
    if any(_word_boundary_hit(low, k) for k in _CALIBRATION_KEYWORDS):
        return "calibration_number"
    # before _PREDICTION_KEYWORDS: "prediction quality" must not be swallowed
    # by the bare "predict" substring -> prediction_winprob. The literal
    # phrase list above misses word-order variants ("how good are the WNBA
    # predictions?") -- catch any query naming both "how good" and a
    # "predict*" token, regardless of what sits between them.
    if any(k in low for k in _PREDICTION_QUALITY_KEYWORDS) or ("how good" in low and "predict" in low):
        return "prediction_quality"
    if any(k in low for k in _CONDITIONAL_KEYWORDS) or (
            any(k in low for k in _CONDITIONAL_AMBIGUOUS_KEYWORDS)
            and any(k in low for k in _CONDITIONAL_SIGNAL_KEYWORDS)):
        return "conditional_winprob"
    if any(k in low for k in _PREDICTION_KEYWORDS):
        return "prediction_winprob"
    if any(k in low for k in _HISTORICAL_KEYWORDS):
        return "historical_result"
    if any(k in low for k in _H2H_HISTORY_KEYWORDS):
        return "h2h_history"
    if any(k in low for k in _STREAK_KEYWORDS):
        return "streaks"
    if _REFEREE_RE.search(low):
        return "verified_claims"
    if _CLAIMS_REROUTE_RE.search(low):
        return "verified_claims"
    if _lb.is_ranking_query(low):
        return "ranking"
    # atlas_card (NEW) -- "card for <entity>" / "show <entity> atlas": a
    # dedicated regex shape (atlas_resolver.is_atlas_card_query), zero token
    # overlap with any keyword list in this file (grepped) so this placement
    # is safe -- kept next to `ranking` since both are single-entity lookups
    # dispatched to their own resolver module.
    if _atlas.is_atlas_card_query(low):
        return "atlas_card"
    # generalized reroute (2026-07-18), AFTER the ranking route so the
    # leaderboard resolver keeps every phrasing it already serves: a
    # ranking-cue question whose metric phrase resolves through ask_index's
    # synonym dict belongs to the claims path -- shape-guess buckets
    # (schedule/concept/player_stat) were swallowing new family metrics
    # ('most b2b resilient players' -> schedule_context).
    # 'best' is deliberately absent from the cue list: "best X" must stay a
    # concept superlative (ANSWER_RULES.md); a concept miss falls back to
    # the claims path post-hoc in resolve() instead.
    # curated_only=True (fix 2026-07-19): extract_metric_synonym's plain
    # name-derived fallback (metric_names.py) matches ANY >=4-char metric-
    # name word ('gravity', 'spacing', 'usage', ...) -- over-broad for a
    # bare cue-word gate, so it was stealing comparables/scouting/concept
    # questions into verified_claims (which can't serve them -> lost to
    # no_data). Restricted to the hand-curated dict (+ shooter alias) hits
    # only. The _SCOUT/_COMPARABLES guard below is belt-and-suspenders for
    # the same failure mode if a future curated alias ever overlaps their
    # keyword shapes.
    if re.search(r"\b(which|most|top|who are|leaders?|specialists?)\b", low):
        is_scout_or_comparables = (any(k in low for k in _SCOUT_KEYWORDS)
                                    or any(k in low for k in _COMPARABLES_KEYWORDS))
        if not is_scout_or_comparables:
            from scripts.platformkit.intel_query.ask_index import extract_metric_synonym
            if extract_metric_synonym(low, curated_only=True) is not None:
                return "verified_claims"
    if any(k in low for k in _ANALYTICS_ATTRIBUTION_KEYWORDS):
        return "analytics_attribution"
    if any(k in low for k in _ANALYTICS_SURVIVAL_KEYWORDS):
        return "analytics_claim_survival"
    if any(k in low for k in _ANALYTICS_VERIFICATION_KEYWORDS):
        return "analytics_verification"
    if any(k in low for k in _ANALYTICS_CONTRADICTION_KEYWORDS):
        return "analytics_contradictions"
    if any(k in low for k in _SYSTEM_MAP_KEYWORDS):
        return "system_map"
    # verified_claims trigger 1: provenance naming an explicit claim_id -- must
    # win over mechanism_effect's bare "evidence" keyword (a prose mechanism
    # query has no claim_id token, so this never diverts one).
    if _CLAIM_PROVENANCE_RE.search(low) and _CLAIM_ID_RE.search(low):
        return "verified_claims"
    if any(k in low for k in _MECHANISM_KEYWORDS) or _AFFECTS_RE.match(low) or _WHAT_DOES_X_AFFECT_RE.match(low):
        return "mechanism_effect"
    if any(k in low for k in _INJURY_KEYWORDS) or _INJURY_IS_RE.search(low):
        return "injury_report"
    if any(k in low for k in _NEWS_KEYWORDS):
        return "news_context"
    if any(k in low for k in _SCHEDULE_KEYWORDS):
        return "schedule_context"
    if any(k in low for k in _SCOUT_KEYWORDS):
        return "scouting_report"
    if any(k in low for k in _COMPARABLES_KEYWORDS):
        return "comparables"
    # player_comparison (2026-07-18): a comparison SHAPE ('vs'/'better than'/
    # 'stack up'/'compared to'/'A and B matched up'/...) naming two entities
    # that BOTH resolve as PLAYERS via the same profiles machinery winprob's
    # sport-inference uses. Checked BEFORE _MATCHUP_PREVIEW_KEYWORDS because
    # 'head-to-head'/'matchup between' also describe a two-PLAYER question
    # (the entity-kind check inside is_two_player_comparison is what actually
    # keeps team questions safe: "Lakers vs Celtics head-to-head" still
    # resolves both names as TEAMS -> False -> falls through to
    # matchup_preview unchanged). Guarded against `_CONCEPT_KEYWORDS` so it
    # never shadows concept_rating's existing "vs "/"does "/"compare" route
    # (e.g. "Trae Young vs LaMelo Ball on gravity" is a named-CONCEPT
    # comparison, not a raw-attribute one -- qa_bank/test_answer_quality_nba.py
    # cover it). A concept_rating MISS still reaches this composer via the
    # bridge in resolve()'s concept_rating branch below.
    if not any(k in low for k in _CONCEPT_KEYWORDS) and _pc.is_two_player_comparison(query):
        return "player_comparison"
    if any(k in low for k in _MATCHUP_PREVIEW_KEYWORDS):
        return "matchup_preview"
    # verified_claims trigger 2: discovery/family words (end of chain, after
    # every specific category -- the family-ish fallback for a claim question
    # nothing else matched, routed to ask() which is itself fail-closed).
    if any(k in low for k in _VERIFIED_CLAIMS_KEYWORDS) or _CLAIM_WORD_RE.search(low):
        return "verified_claims"
    if any(k in low for k in _CONCEPT_KEYWORDS):
        return "concept_rating"
    if "rating" in low or "percentile" in low or "2k" in low:
        return "rating_attribute"
    return "player_stat"  # default shape: "<entity> <attribute>" fact lookup


# ---------------------------------------------------------------------------
# Resolvers not already owned by another module
# ---------------------------------------------------------------------------
_SCOREBOARD_PATH = os.path.join("vault", "_Organized", "_Index", "_Calibration_Scoreboard.md")
_SCOREBOARD_ROW_RE = re.compile(
    r"^\|\s*(?P<sport>\w+)\s*\|\s*(?P<n>[\d,]+)\s*\|\s*(?P<base_brier>[\d.]+)\s*\|\s*"
    r"(?P<imp_brier>[\d.]+)\s*\|\s*(?P<d_brier>[+-]?[\d.]+)\s*\|\s*(?P<base_ece>[\d.]+)\s*\|\s*"
    r"(?P<imp_ece>[\d.]+)\s*\|\s*(?P<d_ece>[+-]?[\d.]+)\s*\|\s*(?P<method>[^|]+)\|\s*$",
    re.MULTILINE,
)


def calibration_number(sport: str) -> dict:
    """Parses the pinned scoreboard row for `sport` -- never recomputes.
    Absent artifact (fresh clone; vault/ is gitignored) -> honest no_data."""
    if not os.path.exists(_SCOREBOARD_PATH):
        return {"status": "no_data", "category": "calibration_number", "sport": sport,
                "source_artifact": _SCOREBOARD_PATH, "note": "scoreboard not built in this clone"}
    text = open(_SCOREBOARD_PATH, encoding="utf-8").read()
    as_of = datetime.fromtimestamp(os.path.getmtime(_SCOREBOARD_PATH), tz=timezone.utc).isoformat()
    for m in _SCOREBOARD_ROW_RE.finditer(text):
        if m.group("sport").lower() == sport.lower():
            return {"status": "ok", "category": "calibration_number", "sport": sport,
                     "source_artifact": _SCOREBOARD_PATH, "as_of": as_of,
                     "n": int(m.group("n").replace(",", "")),
                     "baseline_brier": float(m.group("base_brier")), "improved_brier": float(m.group("imp_brier")),
                     "baseline_ece": float(m.group("base_ece")), "improved_ece": float(m.group("imp_ece")),
                     "method": m.group("method").strip()}
    return {"status": "no_data", "category": "calibration_number", "sport": sport,
            "source_artifact": _SCOREBOARD_PATH, "note": f"no row for sport '{sport}' in current scoreboard"}


_HIST_PATHS = {
    "nba": ("data/domains/basketball_nba/linescores.parquet", "home_abbr", "away_abbr"),
    "mlb": ("data/domains/mlb/games.parquet", "home_team", "away_team"),
}


def historical_result(sport: str, team: str, opponent: str | None = None, date: str | None = None) -> dict:
    """Final score for one real game, read directly off the boxscore/linescore
    parquet -- zero-row honesty: no match -> no_data, never fabricated."""
    cfg = _HIST_PATHS.get(sport)
    if cfg is None:
        return {"status": "not_supported", "category": "historical_result", "sport": sport,
                "note": f"historical_result not wired for sport '{sport}'"}
    path, home_col, away_col = cfg
    if not os.path.exists(path):
        return {"status": "no_data", "category": "historical_result", "sport": sport, "source_artifact": path}
    df = pd.read_parquet(path)
    mask = (df[home_col] == team) | (df[away_col] == team)
    if opponent:
        mask &= (df[home_col] == opponent) | (df[away_col] == opponent)
    if date:
        mask &= df["date"].astype(str).str.startswith(date)
    hits = df[mask]
    if hits.empty:
        return {"status": "no_data", "category": "historical_result", "sport": sport, "source_artifact": path,
                "note": f"zero rows matched team={team!r} opponent={opponent!r} date={date!r} -- refusing, not guessing"}
    row = hits.sort_values("date").iloc[-1]
    as_of = str(row["date"])
    if sport == "nba":
        home_score = int(row[[c for c in df.columns if c.startswith("home_q")]].sum())
        away_score = int(row[[c for c in df.columns if c.startswith("away_q")]].sum())
    else:
        home_score, away_score = int(row["home_runs"]), int(row["away_runs"])
    return {"status": "ok", "category": "historical_result", "sport": sport, "source_artifact": path, "as_of": as_of,
            "home_team": row[home_col], "away_team": row[away_col],
            "home_score": home_score, "away_score": away_score,
            "winner": row[home_col] if home_score > away_score else row[away_col]}


_LEDGER_PATHS = {
    "nba": "domains/basketball_nba/knowledge/validation_ledger.jsonl",
    "mlb": "domains/mlb/knowledge/validation_ledger.jsonl",
    "soccer": "domains/soccer/knowledge/validation_ledger.jsonl",
    "tennis": "domains/tennis/knowledge/validation_ledger.jsonl",
}
# words that show up in a free-text question but never in a hypothesis name --
# stripped before matching so phrasing doesn't defeat the token-subset test.
_MECH_FILLER = {"what", "does", "the", "evidence", "say", "about", "is", "there", "for", "on",
                "local", "data", "support", "it", "true", "that", "hold", "up", "locally",
                "mechanism", "hypothesis", "folklore", "of", "a", "an", "in", "does"}


def _mech_tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in _MECH_FILLER}


def _load_ledger(sport: str) -> list[dict]:
    """Fresh read every call -- a concurrent validation lane appends to these
    files live, so no row count or content is ever cached."""
    path = _LEDGER_PATHS.get(sport)
    if path is None or not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def effect_graph_query(sport: str, target: str, direction: str) -> dict:
    """'what affects <Y>' (direction="to") / 'what does <X> affect'
    (direction="from") -- verbatim edges from the pinned LANE C5 effect graph
    (scripts/platformkit/answers/effect_graph.py), never recomputed here."""
    graph = _eg.load_graph()
    if graph is None:
        return {"status": "no_data", "category": "mechanism_effect", "sport": sport,
                "source_artifact": _eg._OUT_PATH, "note": "effect graph not built in this clone"}
    hits = _eg.query_edges(sport, _mech_tokens(target), direction=direction, graph=graph)
    if not hits:
        return {"status": "not_supported", "category": "mechanism_effect", "sport": sport,
                "source_artifact": _eg._OUT_PATH,
                "note": f"no graph edge found for '{target}' ({direction}) in sport '{sport}'"}
    return {"status": "ok", "category": "mechanism_effect", "sport": sport,
            "source_artifact": _eg._OUT_PATH, "as_of": graph["as_of"], "query": target,
            "edges": [{"from": e["from"], "to": e["to"], "status": e["status"], "effect": e["effect"],
                       "n": e["n"], "p": e.get("p"), "corpus": e.get("corpus"), "artifact": e["artifact"],
                       "note": e.get("note", "")} for e in hits],
            "framing": "LOCAL single-corpus finding(s) -- not a market-beating or causal claim"}


def mechanism_effect(sport: str, mechanism: str) -> dict:
    """Matches free text / a mechanism name against the DISTINCT hypothesis
    names in this sport's validation ledger -- never against model memory.
    Multiple ledger rows for the SAME hypothesis (re-tested across corpora,
    e.g. tennis's 4-corpus rows) are all returned together, verbatim, under
    one answer. Multiple DIFFERENT matching hypotheses -> ambiguous with the
    candidate list (ask.py's existing convention). No match -> not_supported,
    never improvised. "what affects Y" / "what does X affect" queries are
    graph lookups (effect_graph_query), handled before the hypothesis-name
    match below."""
    m = _AFFECTS_RE.match(mechanism)
    if m:
        return effect_graph_query(sport, m.group(1), "to")
    m = _WHAT_DOES_X_AFFECT_RE.match(mechanism)
    if m:
        return effect_graph_query(sport, m.group(1), "from")
    path = _LEDGER_PATHS.get(sport)
    if path is None:
        return {"status": "not_supported", "category": "mechanism_effect", "sport": sport,
                "note": f"mechanism_effect not wired for sport '{sport}'. Available: {sorted(_LEDGER_PATHS)}"}
    rows = _load_ledger(sport)
    if not rows:
        return {"status": "no_data", "category": "mechanism_effect", "sport": sport, "source_artifact": path}
    by_name: dict[str, list[dict]] = {}
    for r in rows:
        by_name.setdefault(r["hypothesis"], []).append(r)
    names = sorted(by_name)
    key = mechanism.strip().lower().replace(" ", "_")
    if key in by_name:
        matches = [key]
    else:
        q_tokens = _mech_tokens(mechanism)
        matches = [n for n in names if q_tokens and q_tokens <= _mech_tokens(n)]
        if not matches:
            matches = difflib.get_close_matches(key, names, n=5, cutoff=0.6)
    if not matches:
        return {"status": "not_supported", "category": "mechanism_effect", "sport": sport,
                "note": f"no mechanism matched '{mechanism}' in {path}. Registered hypotheses: {names}"}
    if len(matches) > 1:
        return {"status": "ambiguous", "category": "mechanism_effect", "sport": sport, "candidates": matches}
    name = matches[0]
    as_of = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc).isoformat()
    findings = [{"verdict": r["verdict"], "effect_local": r["effect"], "n": r["n"], "p": r.get("p"),
                 "corpus": r["corpus"], "note": r["note"]} for r in by_name[name]]
    return {"status": "ok", "category": "mechanism_effect", "sport": sport, "source_artifact": path,
            "as_of": as_of, "hypothesis": name, "findings": findings,
            "framing": "LOCAL single-corpus finding(s) -- not a market-beating or causal claim"}


# ---------------------------------------------------------------------------
# Bare-superlative -> raw-attribute leaderboard bridge (coverage_stress
# Family D): "who is the best/sharpest free throw shooter" names no
# registered CONCEPT (concept_rating's answer_question errors), but the
# residual phrase after the lead-in IS a real registered attribute (ft_pct)
# -- a top-1 leaderboard answers it instead of an honest-but-avoidable
# no_data. Mirrors the existing concept-miss->claims / concept-miss->
# player_compare fallback pattern in resolve()'s concept_rating branch.
_SUPERLATIVE_LEAD_RE = re.compile(
    r"^\s*(?:who\s+(?:is|are|has|shoots?|leads?)\s+(?:the\s+)?|"
    r"what\s+is\s+(?:the\s+)?|which\s+player\s+(?:is|shoots?)\s+(?:the\s+)?)?"
    r"(?:best|sharpest|highest|lowest)\s+(?:from\s+(?:the\s+)?)?", re.I)
_SUPERLATIVE_TRAIL_RE = re.compile(r"\s+in\s+the\s+(?:nba|league)\s*$", re.I)


def _superlative_category(query: str) -> str | None:
    m = _SUPERLATIVE_LEAD_RE.search(query.lower())
    if not m:
        return None
    residual = query[m.end():].strip().strip("?").strip()
    residual = _SUPERLATIVE_TRAIL_RE.sub("", residual).strip()
    return residual or None


# ---------------------------------------------------------------------------
# Free-text entity extraction for the intel categories (wave 3). The classifier
# only routes; these strip the lead-in phrase so `resolve("scouting report for
# Trae Young")` finds "Trae Young". Explicit player=/team=/home=/away= kwargs
# always win over extraction (the consistency battery passes them for
# determinism). ponytail: regex lead-strip, not an NER model -- upgrade only if
# a real query phrasing slips past it.
# ---------------------------------------------------------------------------
_LEAD_RE = re.compile(
    r"^\s*(?:"
    r"scouting report(?: (?:for|on))?|scout report(?: (?:for|on))?|scouting|"
    r"who (?:is|are) comparable to|(?:players? )?comparables?(?: (?:for|to))?|comparable to|"
    r"similar(?: players?)? to|player comps?(?: (?:for|to))?|"
    r"injury report(?: (?:for|on))?|injury status(?: (?:for|of))?|injuries(?: (?:for|of))?|"
    r"news context(?: (?:for|about|on))?|latest news(?: (?:for|about|on))?|"
    r"recent news(?: (?:for|about|on))?|news(?: (?:for|about|on))?|"
    r"schedule context(?: for)?|schedule(?: for)?|rest days(?: for)?|"
    r"how many (?:rest days|back[- ]to[- ]back games|home games(?: in the (?:first|second) half)?|"
    r"road games(?: in the (?:first|second) half)?) do(?:es)?(?: the)?|"
    r"back[- ]to[- ]back(?: for)?|b2b(?: for)?|days of rest(?: for)?|are(?: the)?|"
    r"home[- /]road split(?: for)?|home stand(?: for)?|road trip(?: for)?|remaining schedule(?: for)?|"
    r"historical h2h(?: (?:run|goal|point) differential)?(?: (?:for|between))?|"
    r"historical head[- ]to[- ]head(?: record)?(?: (?:for|between))?|"
    r"(?:historical|all[- ]time|series) record(?: (?:for|between))?|"
    r"head[- ]to[- ]head record(?: (?:for|between))?|h2h record(?: (?:for|between))?|"
    r"(?:run|goal|point) differential(?: (?:for|between))?|"
    r"matchup preview(?: for)?|game preview(?: for)?|preview|"
    r"win probability(?: (?:for|of))?|win prob(?: (?:for|of))?|who wins"
    r")\s+", re.I)
# Interrogative wrapper ("What's the injury report for the Celtics?", "What
# is the schedule context for the Bucks?") sits BEFORE the whole _LEAD_RE
# alternation (which is anchored at position 0), so a real lead-in phrase
# ("injury report for") never gets a chance to match -- found live 2026-07-18
# in coverage_stress (the WHOLE raw query fell through to team=, an honest
# but avoidable no_data). Stripped first, unconditionally; a query that
# doesn't start with this wrapper is untouched.
_INTERROGATIVE_WRAP_RE = re.compile(r"^\s*what(?:'s|s|\s+is|\s+are)?\s+(?:the\s+)?", re.I)
_VS_RE = re.compile(r"\s+(?:vs\.?|versus|@|at)\s+", re.I)
# Interrogative wrapper questions ("How many rest days do the Bucks HAVE
# before their next game?", "Are the Lakers ON a back-to-back tonight?") leave
# a trailing verb/preposition clause behind after _LEAD_RE strips the front --
# cut at the first such filler word (word-boundary, so it never fires inside
# a real name like "Boston" or "Orlando"). Applied AFTER the lead-in strip,
# same ponytail regex-not-NER discipline as _LEAD_RE above.
_TRAIL_RE = re.compile(r"\s+(?:have|has|do|does|is|are|on)\b.*$", re.I)


def _entity_from_query(query: str) -> str:
    """Strip a leading interrogative wrapper, a known lead-in phrase, a
    trailing interrogative clause, and a leading article -- the remainder is
    the team/player. Returns the trimmed query unchanged if nothing matched."""
    unwrapped = _INTERROGATIVE_WRAP_RE.sub("", query, count=1)
    stripped = _LEAD_RE.sub("", unwrapped, count=1).strip().strip("?").strip()
    stripped = _TRAIL_RE.sub("", stripped).strip()
    return re.sub(r"^the\s+", "", stripped, flags=re.I)


_BETWEEN_RE = re.compile(r"\bbetween\s+(.+?)\s+and\s+(.+?)\s*[.?!]*\s*$", re.I)
# "when the Astros play the Dodgers" / "Lakers host the Celtics" -- verb-form
# matchup phrasing with no vs/@/between separator (found live 2026-07-18)
_PLAYS_RE = re.compile(
    r"\b(?:when\s+|if\s+)?(?:the\s+)?([A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*)?)\s+"
    r"(?:plays?|hosts?|faces?|meets?|takes?\s+on)\s+(?:the\s+)?"
    r"([A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*)?)\s*[.?!]*\s*$")


def _injury_player_from_query(query: str) -> str | None:
    """Player name for an 'is X injured [right now]' phrasing (or the broader
    'is X currently dealing with .../listed with ...' shape) -- this always
    names a PERSON, never a team, so it feeds injury_report's player= kwarg
    directly (unlike the older 'injury report for <team>' lead-in, which
    _entity_from_query/_LEAD_RE strips into team=)."""
    m = _INJURY_IS_RE.search(query)
    if not m and "injur" in query.lower():
        m = _INJURY_IS_BROAD_RE.search(query)
    if not m:
        return None
    return re.sub(r"^\s*the\s+", "", m.group(1).strip(), flags=re.I)


def _split_matchup(text: str) -> tuple[str | None, str | None]:
    """Parse 'HOME vs AWAY' / 'AWAY @ HOME' -> (home, away). '@'/'at' means the
    first team is the visitor (away @ home); 'vs'/'versus' keeps first as home.
    Also parses 'between HOME and AWAY' (the '_LEAD_RE' strip on "who wins ..."
    leaves this shape untouched -- real bank phrasing, e.g. "who wins between
    Ashleigh Barty and Mirra Andreeva", never uses vs/versus/@/at)."""
    m = _VS_RE.search(text)
    if not m:
        m2 = _BETWEEN_RE.search(text)
        if m2:
            left, right = m2.group(1).strip(), m2.group(2).strip()
            if left and right:
                return left, right
        m3 = _PLAYS_RE.search(text)
        if m3:
            left, right = m3.group(1).strip(), m3.group(2).strip()
            if left and right:
                return left, right
        return None, None
    left, right = text[:m.start()].strip(), text[m.end():].strip()
    if not left or not right:
        return None, None
    if m.group().strip().lower() in ("@", "at"):
        return right, left
    return left, right


def _matchup_teams(query: str, kwargs: dict) -> tuple[str | None, str | None]:
    home, away = kwargs.get("home"), kwargs.get("away")
    if not (home and away):
        h, a = _split_matchup(_entity_from_query(query))
        if not (h and a):
            # lead-in strip can mangle unusual phrasings ('What is the
            # head-to-head record between X and Y?' -> 'What'); the raw
            # query still parses via the between/vs patterns
            h, a = _split_matchup(query)
        home, away = home or h, away or a
    return home, away


def _infer_sport_from_entities(home: str, away: str) -> str | None:
    """Best-effort sport inference for a matchup query with no reliable sport
    context (e.g. 'who wins between Ashleigh Barty and Mirra Andreeva' -- no
    sport TOKEN in the text), reusing the SAME entity-name matching machinery
    profiles/ask.py's player_stat resolver already uses (load_profiles +
    _match_entities) -- never a new NER/model. Returns the one sport BOTH
    names resolve to; None if either name is unmatched or the two names
    resolve to different sports (an honest 'don't know', never a guess)."""
    df = _ask.load_profiles()
    if df.empty:
        return None

    def _sports_for(name: str) -> set[str]:
        tokens = _ask._norm(name).split()
        _, hits = _ask._match_entities(df, tokens)
        return {sp for _, _, sp in hits}

    common = _sports_for(home) & _sports_for(away)
    return next(iter(common)) if len(common) == 1 else None


# ---------------------------------------------------------------------------
# Compound-question splitter (conservative -- marker list, not NLP). Splits
# ONLY on an explicit conjunction marker; a query with none of these markers
# (including a combined-conditional like "combined win probability if both X
# and Y are out", which names no marker below) is untouched and falls through
# to normal single-question classify()/dispatch, honest no_data included.
# ---------------------------------------------------------------------------
_COMPOUND_PREFIX_RE = re.compile(r"^\s*(?:ok\s+)?two things\s*[-:]*\s*", re.I)
_COMPOUND_NUMBERED_RE = re.compile(
    r"^\s*(?:1[\.\):]|first[,:])\s*(.+?)\s*(?:2[\.\):]|second[,:])\s*(.+)$", re.I)
_COMPOUND_MARKERS = (" and also ", "; also ", ";also ")


def _split_compound(query: str) -> list[str] | None:
    """None if `query` names no explicit conjunction marker (the common
    case -- untouched). Else the 2 (or more, for a numbered list) parts,
    each resolved independently by resolve()'s caller."""
    q = (query or "").strip()
    m = _COMPOUND_NUMBERED_RE.match(q)
    if m:
        return [m.group(1).strip(" ,"), m.group(2).strip(" ,")]
    q2 = _COMPOUND_PREFIX_RE.sub("", q, count=1)
    low = q2.lower()
    for marker in _COMPOUND_MARKERS:
        idx = low.find(marker)
        if idx != -1:
            part1, part2 = q2[:idx].strip(" ,-"), q2[idx + len(marker):].strip(" ,-")
            if part1 and part2:
                return [part1, part2]
    return None


# ---------------------------------------------------------------------------
# Single dispatch entrypoint
# ---------------------------------------------------------------------------
def resolve(query: str, sport: str = "nba", category: str | None = None, **kwargs) -> dict:
    """The one function every consumer (human, CLI, or an LLM following
    docs/AI_CONSUMER_CONTRACT.md) calls. Never improvises past a registered
    resolver; an unclassified or unregistered category is NOT_SUPPORTED."""
    if category is None:
        parts = _split_compound(query)
        if parts is not None:
            sub_envelopes = [resolve(p, sport, **kwargs) for p in parts]
            overall = "ok" if any(e.get("status") == "ok" for e in sub_envelopes) else sub_envelopes[0]["status"]
            return {"status": overall, "category": "compound_question", "sport": sport,
                    "query": query, "parts": sub_envelopes}
    cat = category or classify(query)
    if cat is None or cat not in RESOLVERS:
        return {"status": "not_supported", "category": cat, "query": query,
                "note": f"no resolver registered for this question type. Registered: {sorted(RESOLVERS)}"}
    meta = RESOLVERS[cat]
    if cat == "edge_language":
        return {"status": "refused", "category": cat, "query": query, "source_artifact": meta["source_artifact"],
                "note": "edge/ROI/retracted-number language is out of scope for this engine -- "
                        "see .claude/rules/no-edge-claims.md"}
    if cat == "calibration_number":
        return calibration_number(sport)
    if cat == "historical_result":
        return historical_result(sport, kwargs.get("team", ""), kwargs.get("opponent"), kwargs.get("date"))
    if cat == "h2h_history":
        team_a = kwargs.get("team_a") or kwargs.get("home")
        team_b = kwargs.get("team_b") or kwargs.get("away")
        if not (team_a and team_b):
            team_a, team_b = _matchup_teams(query, kwargs)
        if not (team_a and team_b):
            return {"status": "no_data", "category": "h2h_history", "sport": sport,
                    "note": "could not parse two teams from query -- pass team_a=/team_b= or 'TEAM_A vs TEAM_B'"}
        return _h2h_history.resolve(sport, team_a, team_b, as_of=kwargs.get("as_of") or kwargs.get("date"))
    if cat == "streaks":
        team = kwargs.get("team") or _streaks.parse_team(query)
        if not team:
            return {"status": "no_data", "category": "streaks", "sport": sport,
                    "note": "could not parse a team from query -- pass team= explicitly"}
        return _streaks.resolve(sport, team, as_of=kwargs.get("as_of") or kwargs.get("date"))
    if cat == "conditional_winprob":
        return _conditional_winprob.resolve(sport, as_of=kwargs.get("as_of") or kwargs.get("date"),
                                            team=kwargs.get("team"))
    if cat == "mechanism_effect":
        result = mechanism_effect(sport, kwargs.get("mechanism") or query)
        # RESOLVER BRIDGE fallback: the validation-ledger hypothesis match can
        # miss a real, VERIFIED claim family that answers the same question
        # under a different name (e.g. no ledger hypothesis mentions "runs
        # saved", but the catcher_framing claim family may). Only tried on a
        # miss, and only replaces the envelope if the bridge itself lands ok
        # -- a claims no_data/not_supported never overrides the honest
        # mechanism envelope (still the more specific of two refusals).
        if result["status"] in ("not_supported", "no_data"):
            bridged = _claims.resolve(query, sport, **kwargs)
            if bridged.get("status") == "ok":
                return {**bridged,
                        "note": "mechanism ledger had no match; answered from the VERIFIED claims store"}
        return result
    if cat == "verified_claims":
        return _claims.resolve(query, sport, **kwargs)
    if cat == "prediction_quality":
        from scripts.platformkit.answers import prediction_quality_resolver as _pq
        return _pq.resolve(kwargs.get("sport_filter") or _pq.sport_in_query(query))
    if cat == "analytics_attribution":
        return _analytics.attribution(sport, kwargs.get("family"), kwargs.get("card_id"))
    if cat == "analytics_claim_survival":
        return _analytics.claim_survival(sport)
    if cat == "analytics_verification":
        return _analytics.verification(sport, kwargs.get("stat"))
    if cat == "analytics_contradictions":
        return _analytics.contradictions(sport, kwargs.get("family"))
    if cat == "system_map":
        return _analytics.system_map(sport, kwargs.get("node"), query)
    if cat == "injury_report":
        player = kwargs.get("player") or _injury_player_from_query(query)
        team = kwargs.get("team") if player else (kwargs.get("team") or _entity_from_query(query))
        result = _edge_facts.injury_report(sport, team=team, player=player)
        # A lead-in like "injury status for <Name>"/"injury report for <Name>"
        # names a PLAYER as often as a TEAM ("injury status for Tommy Pham"),
        # but _entity_from_query always feeds the extraction into team= first
        # (found live 2026-07-18: real bank phrasing). A team-lookup miss on
        # an entity nobody passed explicitly as team= is retried once as a
        # player -- never overrides a caller's own explicit team=.
        if (result["status"] == "no_data" and team and not player and not kwargs.get("team")):
            retry = _edge_facts.injury_report(sport, player=team)
            if retry["status"] == "ok":
                return retry
        # A resolved PLAYER name (real phrasing, "is X injured") that matched
        # zero rows in a STORE THAT EXISTS is an honest "not currently listed"
        # answer, not a failure -- distinct from an absent store (real
        # no_data) or an unresolvable name (player is None -> untouched below).
        if result["status"] == "no_data" and player and _edge_facts.FS.path_for("injury", sport).is_file():
            as_of = datetime.fromtimestamp(
                _edge_facts.FS.path_for("injury", sport).stat().st_mtime, tz=timezone.utc).isoformat()
            return {"status": "ok", "category": result["category"], "sport": sport,
                    "source_artifact": result["source_artifact"], "as_of": as_of, "player": player,
                    "note": f"{player} not found on the current injury report as of {as_of}"}
        return result
    if cat == "news_context":
        team = kwargs.get("team") or _entity_from_query(query)
        player_kw = kwargs.get("player")
        result = _edge_facts.news_context(sport, team=team, player=player_kw)
        # Same team/player ambiguity as injury_report above ("latest news
        # about Aaron Judge" extracts a PERSON into team=) -- retry once as
        # player on a team-lookup miss, never overriding an explicit team=.
        if (result["status"] == "no_data" and team and not player_kw and not kwargs.get("team")):
            retry = _edge_facts.news_context(sport, player=team)
            if retry["status"] == "ok":
                return retry
        return result
    if cat == "schedule_context":
        team = kwargs.get("team") or _entity_from_query(query)
        if any(k in query.lower() for k in _SCHEDULE_SPLIT_KEYWORDS):
            return _schedule.home_road_split(sport, team, kwargs.get("date"))
        env = _schedule.resolve(sport, team, date=kwargs.get("date"))
        if env.get("status") in ("no_data", "not_supported"):
            # season-aggregate rest attributes (avg_rest_days, b2b_rate) live
            # in the profiles, not the live calendar -- 'Aces average rest
            # days this season' must not dead-end when the calendar resolver
            # can't serve the sport (found live 2026-07-18)
            r = _ask.answer_lookup(query, sport, kwargs.get("window"))
            if r.get("status") == "ok":
                return {"status": "ok", "category": "player_stat", "sport": sport, **{
                    k: v for k, v in r.items() if k != "status"}}
        return env
    if cat == "scouting_report":
        return _scout.compose_scout(sport, kwargs.get("player") or _entity_from_query(query),
                                    kind=kwargs.get("kind", "player"), top_n=kwargs.get("top_n", 8))
    if cat == "comparables":
        return _comparables.compose_comparables(sport, kwargs.get("player") or _entity_from_query(query),
                                                k=kwargs.get("k", 5))
    if cat == "player_comparison":
        return _pc.compare(query, sport, **kwargs)
    if cat == "matchup_preview":
        home, away = _matchup_teams(query, kwargs)
        if not (home and away):
            return {"status": "no_data", "category": "matchup_preview", "sport": sport,
                    "note": "could not parse home/away from query -- pass home=/away= or 'HOME vs AWAY'"}
        return _matchup.compose_matchup(sport, home, away, date=kwargs.get("date"))
    if cat == "ranking":
        env = _lb.resolve_query(sport, query, top_n=kwargs.get("top_n"), min_n=kwargs.get("min_n", 0.0),
                                 window=kwargs.get("window"), kind=kwargs.get("kind"),
                                 ascending=kwargs.get("ascending", False), category=kwargs.get("attribute"),
                                 team=kwargs.get("team"))
        if env.get("status") in ("no_data", "not_supported", "ambiguous"):
            # leaderboard miss OR fuzzy tie + resolvable claims metric -> the
            # claims path answers instead ('bp saved pct asof leaders' tied
            # several profile attrs while the exact metric is a VERIFIED
            # claim; 'top 5 assist leaders': profiles have no
            # assist attribute but ast_per_game is a VERIFIED claim,
            # found 2026-07-18). Claims-path miss keeps the leaderboard
            # envelope (its 'available' listing is the more useful refusal).
            from scripts.platformkit.intel_query.ask_index import extract_metric_synonym
            if extract_metric_synonym(query.lower()) is not None:
                claims_env = _claims.resolve(query, sport=sport)
                if claims_env.get("status") == "ok":
                    return claims_env
        return env
    if cat == "atlas_card":
        entity = kwargs.get("entity") or _atlas.parse_entity(query)
        if not entity:
            return {"status": "no_data", "category": cat, "sport": sport,
                    "source_artifact": _atlas._OUT_DIR_REL,
                    "note": "could not parse an entity from query -- pass entity= explicitly"}
        return _atlas.resolve(entity, sport_filter=kwargs.get("sport_filter"))
    if cat == "prediction_winprob":
        home, away = _matchup_teams(query, kwargs)
        if not (home and away):
            return {"status": "no_data", "category": cat, "sport": sport,
                    "note": "could not parse home/away from query -- pass home=/away= or 'HOME vs AWAY'"}
        # A query with no sport TOKEN ("who wins between Ashleigh Barty and
        # Mirra Andreeva") relies entirely on the caller's `sport` kwarg,
        # which defaults to "nba" -- wrong for a tennis/soccer matchup. Infer
        # from the entity names (same machinery player_stat lookups use) and
        # PREFER it when it resolves unambiguously; an inconclusive/conflicting
        # inference (no profile data in this clone, or a genuinely unmatched
        # name) falls back to the caller's own `sport`, never forced to
        # no_data -- that would break every already-correct explicit-sport call.
        dispatch_sport = _infer_sport_from_entities(home, away) or sport
        return _winprob.dispatch(dispatch_sport, home, away, ingame_state=kwargs.get("ingame_state"))
    if cat in ("player_stat", "rating_attribute"):
        if sport not in _ask.SPORTS:
            return {"status": "not_supported", "category": cat, "sport": sport,
                    "note": f"sport not wired for profile lookups. Available: {_ask.SPORTS}"}
        r = _ask.answer_lookup(query, sport, kwargs.get("window"))
        if r["status"] != "ok":
            return {"status": "no_data" if r["status"] in ("no_entity", "no_attribute", "no_data") else r["status"],
                     "category": cat, "sport": sport, "detail": r}
        row = r["row"]
        return {"status": "ok", "category": cat, "sport": sport,
                 "source_artifact": str(row["sources"]), "as_of": str(row["window"]),
                 "entity_name": row["entity_name"], "attribute": row["attribute"],
                 "raw_value": row["raw_value"], "percentile": round(float(row["percentile"]), 2),
                 "rating_2k": round(float(row["rating_2k"]), 2), "n": round(float(row["n"]), 1),
                 "status_label": row["status"]}
    if cat == "concept_rating":
        if sport not in _CONCEPT_SPORTS:
            return {"status": "not_supported", "category": cat, "sport": sport,
                    "note": f"no concept registry for sport '{sport}'. Available: {sorted(_CONCEPT_SPORTS)}"}
        result = _contracts.answer_question(query, sport, kwargs.get("window"), kwargs.get("concept"),
                                             kwargs.get("kind", "player"))
        if "error" in result:
            # concept miss + resolvable claims metric -> claims path (same
            # post-miss pattern as the ranking route: 'best hitters against
            # high velocity' is a claims metric, not a concept). Claims miss
            # keeps the concept refusal envelope.
            from scripts.platformkit.intel_query.ask_index import extract_metric_synonym
            if extract_metric_synonym(query.lower()) is not None:
                claims_env = _claims.resolve(query, sport=sport)
                if claims_env.get("status") == "ok":
                    return claims_env
            # concept miss + a real two-player comparison shape ('vs '/'does '
            # /'compare' already routed here via _CONCEPT_KEYWORDS, but the
            # query names no registered CONCEPT -- e.g. "X vs Y -- who carries
            # higher three-point volume") -> the raw-attribute composer
            # answers instead. A composer no_data keeps this concept refusal
            # (the more specific of the two honest envelopes).
            if _pc.is_two_player_comparison(query):
                cmp_env = _pc.compare(query, sport=sport, **kwargs)
                if cmp_env.get("status") == "ok":
                    return cmp_env
            # concept miss + a bare superlative naming no CONCEPT but a real
            # registered ATTRIBUTE ("who is the best free throw shooter") ->
            # top-1 leaderboard. A leaderboard miss (not_supported/no_data/
            # ambiguous) keeps this concept refusal (still the more specific
            # of the two honest envelopes).
            cat_text = _superlative_category(query)
            if cat_text:
                lb_env = _lb.leaderboard(sport, cat_text, top_n=kwargs.get("top_n", 1))
                if lb_env.get("status") == "ok":
                    return lb_env
            return {"status": "no_data", "category": cat, "sport": sport, "note": result["error"]}
        return {"status": "ok", "category": cat, "sport": sport,
                 "source_artifact": f"domains/{ 'basketball_nba' if sport=='nba' else sport }/concepts/concept_registry.py",
                 "as_of": result.get("window"), **result}
    return {"status": "not_supported", "category": cat, "note": "unreachable -- category registered but undispatched"}

"""Lazy per-family `.index.jsonl` routing for ask.py's TOP_N fast path
(spec sec 4 SERVING AT SCALE, LANE L-D).

Split out of ask.py to respect the <=300 LOC/file rail (ask.py was already
552 lines before this lane touched it -- same precedent as
claims_validator.py -> claims_validator_batch.py). ask.py imports
`index_top_n_lookup` and calls it BEFORE its own `load_verified_claims()`
full-load path; a None return means "the index path cannot answer this
question," and the caller must fall through to the existing full-load
behavior unchanged -- this module never decides "unanswerable" itself.

Never weakens VERIFIED-only: an index line with verdict != VERIFIED is
skipped exactly as `load_verified_claims` already skips non-VERIFIED rows.

BUG FIX (routing/metric-matching, no data missing): "top 5 nba players by
free throw percentage" was answering with metric=team_pts_per_game -- a
TEAM claim -- because (a) families.classify's fixed alias dict has no
synonym for "free throw percentage" so metric_hints comes back empty, and
an empty metric_hints skips ALL metric filtering (every VERIFIED ranking
claim in the corpus becomes a candidate), and (b) nothing ever checked
that the question said "players" while the winning claim's entity_key was
"team". `_extract_metric_synonym` + `_question_entity_type` +
`_entity_key_type` close both gaps as DATA (a synonym dict + an entity_key
classifier), applied identically in both the fast (index) path here and
the slow (full-load) path in ask.py's `_filter_by_hints`.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from scripts.platformkit.intel_query.claims_index import discover_families, is_index_fresh

VERIFIED = "VERIFIED"

ENTITY_TYPE_PLAYER = "player"
ENTITY_TYPE_TEAM = "team"
ENTITY_TYPE_OFFICIAL = "official"

# Natural-language metric synonyms -> the REAL metric name used in
# criteria.metric across data/cache/intel_claims/*.jsonl. Enumerated from
# the actual dims that exist (nba_player_box_rate, nba_shooting_claims,
# nba_team_box_rate) rather than guessed -- see the fix's diagnosis for the
# `python -c` dump this was built from. Longest-alias-wins matching (see
# `_extract_metric_synonym`) so e.g. "free throw percentage" (-> ft_pct-
# shaped) is never shadowed by a shorter, unrelated substring.
# ponytail: hand-maintained alias dict -- a NEW metric dim needs an alias
# entry here to be answerable by natural phrasing; unaliased phrasings
# honestly refuse (UNANSWERABLE), never mis-answer. Safe failure mode.
_METRIC_SYNONYMS: dict[str, str] = {
    # player free-throw RELIABILITY (nba_shooting_claims) -- there is no
    # player-level metric literally named ft_pct; ft_reliability IS the
    # player free-throw-percentage claim (values are the made/attempt
    # rate, e.g. 0.95 = 95%).
    "free throw percentage": "ft_reliability",
    "free-throw percentage": "ft_reliability",
    "free throw pct": "ft_reliability",
    "free-throw pct": "ft_reliability",
    "ft%": "ft_reliability",
    "ft pct": "ft_reliability",
    "ft_pct": "ft_reliability",
    "free throw reliability": "ft_reliability",
    # team free-throw pct (nba_team_box_rate) -- distinct metric, distinct
    # entity_key=team; only reachable when the question says "team(s)".
    "team free throw percentage": "team_ft_pct",
    "team ft%": "team_ft_pct",
    # obvious box-rate synonyms (nba_player_box_rate / nba_team_box_rate)
    "points per game": "pts_per_game",
    "ppg": "pts_per_game",
    "assists per game": "ast_per_game",
    "apg": "ast_per_game",
    "assist to turnover": "ast_to_tov",
    "rebounds per game": "reb_per_game",
    "rpg": "reb_per_game",
    "offensive rebounds per game": "oreb_per_game",
    "defensive rebounds per game": "dreb_per_game",
    "steals per game": "stl_per_game",
    "spg": "stl_per_game",
    "blocks per game": "blk_per_game",
    "bpg": "blk_per_game",
    "turnovers per game": "tov_per_game",
    "personal fouls per game": "pf_per_game",
    "fouls per game": "pf_per_game",
    "minutes per game": "min_per_game",
    "field goal attempts per game": "fga_per_game",
    "free throw attempts per game": "fta_per_game",
    "plus minus": "plus_minus_per_game",
    "plus-minus": "plus_minus_per_game",
    "team points per game": "team_pts_per_game",
    "team rebounds per game": "team_reb_per_game",
    "team assists per game": "team_ast_per_game",
    "team turnovers per game": "team_tov_per_game",
    "team field goal percentage": "team_fg_pct",
    "team fg%": "team_fg_pct",
    "team 3 point percentage": "team_fg3_pct",
    "team three point percentage": "team_fg3_pct",
    "team true shooting": "team_ts_pct",
    # venue-split families (2026-07-17): idiom aliases; literal metric names
    # ("gf diff", "home minus away ppg") already route via the name-derived
    # fallback in metric_names.py.
    "home advantage": "winrate_diff",            # soccer_team_venue_split
    "home court advantage": "home_minus_away_ppg",  # nba_venue_split
    "venue split": "home_minus_away_ppg",
    # shooter quality (2026-07-17): RETARGETED shooter_quality_v1 ->
    # shooter_composite_v2. Both are VERIFIED; v1 is TS%/eFG%/FT%-flavored
    # (efficiency-heavy pillars) and still puts Durant/LaVine/Powell top-3 --
    # efficient FINISHERS, not volume 3-point shooters, a metric trap for
    # "who is the best shooter". v2 (shooter_composite_v2_claims.jsonl) is
    # the basketball-smart multi-axis answer: percentile-weighted volume
    # (fg3a_per_game) + efficiency (fg3_pct) + difficulty (pullup_combined_
    # freq, unassisted_share_3pm) + gravity_score + ft_reliability, frozen
    # weights, over a fg3a_per_game>=4.0 qualified pool -- so it is the one
    # this alias now routes to for the natural "best shooter" question. v1
    # stays on disk/VERIFIED (untouched) for anyone asking for it by its
    # literal metric name.
    "best shooter": "shooter_composite_v2",
    "best shooters": "shooter_composite_v2",
    "shooter quality": "shooter_composite_v2",
    "shooting quality": "shooter_composite_v2",
    # scorer quality (nba_quality_claims, 2026-07-17): VERIFIED,
    # weights declared+frozen pre-scoring. Deliberately NOT the "canonical
    # shooter" naive_comp -- that eFG-flavored composite ranks rim-running
    # centers (Allen/Gafford/Hayes) on top, which is a metric trap, not an
    # answer to "who is the best shooter". Unchanged by the shooter
    # retarget above -- "scorer" is a distinct question from "shooter".
    "best scorer": "scorer_quality_v1",
    "best scorers": "scorer_quality_v1",
    "scorer quality": "scorer_quality_v1",
    # 2026-07-19 merge -- 3 new claim families with zero NL aliases (coverage
    # gap: resolve()/ask() returned no_data/not_supported on the obvious
    # phrasing even though the metric exists and is VERIFIED). shooter alias
    # phrases are handled by _SHOOTER_ALIAS_RE below (season-token-aware --
    # see extract_metric_synonym), not this dict, so they are NOT duplicated
    # here.
    "defense adjusted true shooting": "def_adj_ts_pct",
    "defense-adjusted ts": "def_adj_ts_pct",
    "def adj ts": "def_adj_ts_pct",
    "shoot better against weak defenses": "ts_pct_weak_minus_tough",
    "weak vs tough defense split": "ts_pct_weak_minus_tough",
    "weak versus tough defense split": "ts_pct_weak_minus_tough",
    "weak vs tough defense": "fg3_pct_weak_minus_tough",
    "scheme sensitive scorers": "scheme_ts_pct_best_minus_worst",
    "ts swing by scheme": "scheme_ts_pct_best_minus_worst",
    "usage when trailing vs leading": "trailing_fga_pg_minus_leading_fga_pg",
    "usage when trailing versus leading": "trailing_fga_pg_minus_leading_fga_pg",
    "shot volume collapse when leading": "trailing_fga_pg_minus_leading_fga_pg",
    "on off net rating": "net_rating_delta",
    "on-off net rating": "net_rating_delta",
    "on/off impact": "net_rating_delta",
    "teammates shoot better with him on": "teammate_efg_lift",
    "gravity proxy": "gravity_proxy",
    "rim protection on off": "rim_protection_delta",
    "rim protection on-off": "rim_protection_delta",
    "best spacing lineup": "spacing_mean_dist",
    # mlb_batter_context (batter xwOBA context splits)
    "vs velocity": "vs_velocity_delta",
    "against high velocity": "vs_velocity_delta",
    "vs breaking balls": "vs_pitch_type_delta",
    "platoon split": "context_platoon_delta",
    "crushes fastballs": "vs_pitch_type_delta",
    "crush fastballs": "vs_pitch_type_delta",
    # nba_rest_context (2026-07-18): schedule/fatigue-conditioned player
    # splits -- "b2b drop"/"back to back efficiency"/"rest split" all route
    # to the headline TS%-drop metric; "b2b resilient" is the DISTINCT
    # pts-per-36 delta metric (smallest/most-positive change = most resilient).
    "b2b drop": "b2b_ts_drop",
    "back to back efficiency": "b2b_ts_drop",
    "rest split": "b2b_ts_drop",
    "b2b resilient": "b2b_pts36_delta",
    # kalshi_sportsbook_prob_gap (2026-07-18): market-level descriptive family
    "assist leaders": "ast_per_game",
    "kalshi vs sportsbook": "mean_abs_gap",
    "kalshi sportsbook gap": "mean_abs_gap",
    "prediction market vs sportsbook": "mean_abs_gap",
    # nba_teammate_context (2026-07-18): teammate-effects family -- "who
    # lifts whom". Added as a SEPARATE end-of-dict block per merge-conflict
    # convention (multiple concurrent lanes append aliases here).
    "best duos": "pair_lift",
    "pair lift": "pair_lift",
    "plays better with": "pair_lift",
    "teammate effect": "pair_lift",
    "gravity teammate": "gravity_teammate_delta",
}

# Shooter-composite family (2026-07-19): "best shooters"/"top shooters"/
# "shooter composite"/"best shooter ranking" all name the SAME question, but
# the family now has TWO VERIFIED metric variants -- the frozen-window
# shooter_composite_v2 and the season-to-date shooter_composite_v2_asof_approx
# added in the same merge. A season token ("this season", "2025-26") in the
# question means the asker wants the CURRENT, in-progress season -- route
# those to the asof variant; everything else keeps the pre-existing
# shooter_composite_v2 behavior unchanged (checked BEFORE the plain dict
# loop so this one family gets the conditional pick; every other alias above
# is a fixed, unconditional string).
_SHOOTER_ALIAS_RE = re.compile(
    r"\bbest shooters?\b|\btop shooters?\b|\bshooter composite\b|\bbest shooter ranking\b|"
    r"\bshooter quality\b|\bshooting quality\b", re.IGNORECASE)
_SEASON_TOKEN_RE = re.compile(r"\bthis season\b|\b2025-26\b|\b2025_26\b|\b2025-2026\b", re.IGNORECASE)

# A claim's criteria.entity_key NAME already tells you its entity type --
# every team-shaped family observed in data/cache/intel_claims/ names its
# key as "team" or a "team_"-prefixed word-piece (team, team_posgroup,
# team_lo, team_hi), and every player/person-shaped family does not
# (player_id, pid, batter, catcher_id, umpire_id, official_id, p1_id,
# p2_id). Matching the word-piece rather than an exhaustive hand-
# maintained set means a new family lands correctly the moment its rows
# declare entity_key using the same team_* / *_id naming every existing
# family already follows.
_PLAYERS_WORD_RE = re.compile(r"\bplayers?\b", re.IGNORECASE)
_TEAMS_WORD_RE = re.compile(r"\bteams?\b", re.IGNORECASE)
# Officials/referees are a THIRD entity domain (probe regression 2026-07-19:
# "top officials by fta per game" was answered by nba_player_box_rate --
# officials are not players). Token set mirrors resolver_registry._REFEREE_RE
# (singular "official" deliberately excluded there to protect "official
# injury report"; same here). entity_key alone cannot distinguish an
# official store (nba_referee_crew_ft uses generic "entity_id"), so the
# gate below checks the CLAIM ID for referee vocabulary instead.
_OFFICIALS_WORD_RE = re.compile(
    r"\b(referees?|refs|officials|officiating|officiated|crew chief)\b", re.IGNORECASE)
_OFFICIAL_FAMILY_RE = re.compile(r"referee|official|umpire|crew_chief", re.IGNORECASE)


def _entity_key_type(entity_key: Any) -> str:
    """Classify a claim's criteria.entity_key as ENTITY_TYPE_TEAM or
    ENTITY_TYPE_PLAYER. A pair-keyed entity_key (list, e.g. [p1_id, p2_id]
    or [team_lo, team_hi]) is classified by its first element's name --
    the same team/not-team word-piece check applies element-wise."""
    if isinstance(entity_key, list):
        entity_key = entity_key[0] if entity_key else None
    pieces = str(entity_key or "").lower().split("_")
    return ENTITY_TYPE_TEAM if "team" in pieces else ENTITY_TYPE_PLAYER


def question_entity_type(text: str) -> str | None:
    """"players"/"player", "teams"/"team", or referee/officials vocabulary
    in the question text -> the entity type the answer MUST be. None if the
    question names none (or names several, ambiguously) -- callers must not
    filter by entity type in that case, only when it is unambiguous.
    Officials win outright when present: "top officials by fta per game"
    contains no player/team token, and a query mixing officials with
    players/teams is about officiating context, not a player leaderboard."""
    text = text or ""
    if _OFFICIALS_WORD_RE.search(text):
        return ENTITY_TYPE_OFFICIAL
    has_players = bool(_PLAYERS_WORD_RE.search(text))
    has_teams = bool(_TEAMS_WORD_RE.search(text))
    if has_players and not has_teams:
        return ENTITY_TYPE_PLAYER
    if has_teams and not has_players:
        return ENTITY_TYPE_TEAM
    return None


def entity_key_matches(entity_key: Any, entity_type: str | None, claim_id: str = "") -> bool:
    """True if entity_type is None (question named no entity type, so every
    row passes) or the row classifies as entity_type. Takes the raw
    entity_key VALUE (not a row) so one function works for both the flat
    index-sidecar shape (top-level "entity_key") and the full claim-row
    shape (nested under "criteria") -- callers pass whichever they have.

    ENTITY_TYPE_OFFICIAL is decided by `claim_id` (referee/official/umpire
    vocabulary in the id), because official stores use a generic entity_key
    ("entity_id") that classifies as player -- an officials question must
    NEVER be answered by a player/team row, and this claim_id gate is what
    stops a player-metric match ("fta per game") from winning it.
    # ponytail: player/team questions do not symmetrically exclude official
    # rows (metric names never collide there today); add the reverse gate
    # only if a real collision shows up."""
    if entity_type is None:
        return True
    if entity_type == ENTITY_TYPE_OFFICIAL:
        return bool(_OFFICIAL_FAMILY_RE.search(str(claim_id)))
    return _entity_key_type(entity_key) == entity_type


def extract_metric_synonym(text: str) -> str | None:
    """Longest-alias-match lookup into _METRIC_SYNONYMS: never
    first-keyword-wins -- e.g. "team free throw percentage" must resolve to
    team_ft_pct, not the shorter "free throw percentage" -> ft_reliability
    alias that is also a substring of it. Falls back to the name-derived
    metric map (metric_names.py, 2026-07-17: closes the 337-unaliased-
    metrics gap -- saying a metric's literal name now routes) when no hand
    alias matches. Returns the REAL metric name, or None."""
    lower = (text or "").lower()
    if _SHOOTER_ALIAS_RE.search(lower):
        return "shooter_composite_v2_asof_approx" if _SEASON_TOKEN_RE.search(lower) else "shooter_composite_v2"
    best_alias_len = -1
    best_metric: str | None = None
    for alias, metric in _METRIC_SYNONYMS.items():
        if alias in lower and len(alias) > best_alias_len:
            best_alias_len = len(alias)
            best_metric = metric
    if best_metric is not None:
        return best_metric
    from scripts.platformkit.intel_query.metric_names import (
        DEFAULT_CLAIMS_DIR, metric_from_name)
    return metric_from_name(text, DEFAULT_CLAIMS_DIR)


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def seek_claim_row(claims_path: Path, byte_offset: int) -> dict[str, Any] | None:
    """Read exactly ONE line at byte_offset from claims_path. None on any
    I/O trouble (missing file, offset past EOF after a concurrent rewrite,
    malformed JSON) -- caller must fall back to full load, never crash."""
    try:
        with open(claims_path, "rb") as f:
            f.seek(byte_offset)
            line = f.readline()
        return json.loads(line)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def index_top_n_lookup(parsed, claims_dir: Path, repo_root: Path) -> dict[str, Any] | None:
    """Spec sec 4 fast path: route via each family's small `.index.jsonl`
    instead of `load_verified_claims`'s full O(all-claims) parse. Returns
    the SAME winning claim ROW `load_verified_claims` + `_answer_top_n`
    would have picked (kind=ranking, VERIFIED, most-recent computed_at
    among metric/window-matching candidates), or None if the index path
    cannot answer -- callers must then fall back to the full-load path,
    never treat None as "unanswerable" themselves.

    A family is skipped (not treated as an error) when: no fresh index
    exists for it (is_index_fresh False covers missing/stale/malformed),
    or no VERIFIED index line matches the question's hints. Skipping is
    fail-open PER FAMILY, matching load_verified_claims' own per-store
    fail-open convention -- one stale/missing index never blocks another
    family's fresh index from answering.

    Entity-type + metric-synonym gate (bug fix): a synonym resolved from
    parsed.raw (e.g. "free throw percentage" -> ft_reliability) is honored
    ALONGSIDE metric_hints, not instead of it -- either one matching is
    enough. entity_type is resolved once from parsed.raw and used to
    reject any row whose entity_key classifies as the OTHER entity type
    (a "players" question can never be answered by a team-shaped row, and
    vice versa), closing the exact gap that let team_pts_per_game win a
    "top 5 nba players" question.
    """
    metric_synonym = extract_metric_synonym(parsed.raw)
    entity_type = question_entity_type(parsed.raw)
    allowed_metrics = set(parsed.metric_hints)
    if metric_synonym is not None:
        allowed_metrics.add(metric_synonym)
    if not allowed_metrics:
        # UNANSWERABLE-over-wrong-answer: a top-N question whose metric
        # resolved to NOTHING (no families.py alias, no synonym) must never
        # be answered by whatever claim is most recent. Fall through to the
        # slow path, which refuses with the honest unanswerable reason.
        return None
    best_row: dict[str, Any] | None = None
    best_claims_path: Path | None = None
    best_computed_at = ""
    for family in discover_families(claims_dir):
        if not is_index_fresh(family, claims_dir):
            continue
        index_path = claims_dir / f"{family}.index.jsonl"
        claims_path = claims_dir / f"{family}.jsonl"
        try:
            with open(index_path, "r", encoding="ascii", errors="strict") as f:
                index_lines = f.readlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line in index_lines:
            line = line.strip()
            if not line:
                continue
            try:
                idx_row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if idx_row.get("verdict") != VERIFIED:
                continue
            if idx_row.get("metric") not in allowed_metrics:
                continue
            if parsed.window_hint and idx_row.get("window") != parsed.window_hint:
                continue
            if not entity_key_matches(idx_row.get("entity_key"), entity_type, idx_row.get("claim_id", "")):
                continue
            computed_at = idx_row.get("computed_at") or ""
            if computed_at <= best_computed_at:
                continue
            candidate_row = seek_claim_row(claims_path, idx_row.get("byte_offset", 0))
            if candidate_row is None or candidate_row.get("kind") != "ranking":
                continue
            best_row, best_claims_path, best_computed_at = candidate_row, claims_path, computed_at
    if best_row is None:
        return None
    return dict(
        best_row,
        _validator_source=_display_path(claims_dir / f"{best_claims_path.stem}_validation.json", repo_root),
        _producer_source=_display_path(best_claims_path, repo_root),
    )


def _ascii_fold(name: str) -> str:
    """Diacritic-insensitive fold -- duplicated (not imported) from ask.py's
    `_ascii_name`, which the entity-name comparison below must match
    exactly; ask.py imports THIS module, so importing back would cycle."""
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def index_entity_lookup(parsed, name_key: str, claims_dir: Path, repo_root: Path) -> list[dict[str, Any]]:
    """Entity-lookup fast path (2026-07-16 memory fix): same verdict /
    metric / window / entity_type pre-filter as index_top_n_lookup, read
    entirely from the small `.index.jsonl` sidecar -- but SEEKS+READS every
    surviving candidate (not just the most-recent one), since an entity
    lookup wants every VERIFIED ranking claim the entity appears in, not
    one winner.

    Root cause fixed: entity_lookup's only path used to be
    `load_verified_claims`, which materializes every VERIFIED row of every
    store into a dict for the life of the call. For nba_player_box_rate
    (2.8GB / 59,710 rows, each row a ~44KB full-league ranking blob) that
    is multi-GB resident just to answer a single-player question. Here
    each candidate row is read, checked for `name_key`, and DISCARDED
    immediately if it is not a hit -- peak memory is O(1) row plus the
    small hit list, never the whole store.

    Only scans families with a FRESH index (`is_index_fresh`); a stale or
    missing index contributes NO rows here for that family -- the caller
    (ask.py) must full-load exactly that family from CLAIM_SOURCE_PAIRS as
    the residual, the same fallback contract index_top_n_lookup already
    established.

    Per-(metric, window) dedup within a family (self-critique after a real-
    corpus RSS run still hit ~2GB): a `kind=ranking` claim IS the full
    leaderboard for one (metric, window) -- there is only one true ordering,
    so every VERIFIED claim_id sharing that pair is the SAME leaderboard,
    individually re-validated once per contained entity (confirmed by
    content-hash equality on 5 sampled nba_player_box_rate rows sharing a
    (metric, window), 2026-07-16). nba_player_box_rate alone carries up to
    457 VERIFIED claim_ids per (metric, window) group -- without this dedup
    a common player (in every metric's leaderboard) accumulates hundreds of
    byte-identical ~44KB rows PER metric across dozens of metrics/windows,
    which is exactly what re-inflated peak RSS past 2GB on an unhinted
    query. Reading (and keeping, if a hit) only the FIRST VERIFIED row per
    (metric, window) is content-equivalent to reading every duplicate."""
    metric_synonym = extract_metric_synonym(parsed.raw)
    entity_type = question_entity_type(parsed.raw)
    allowed_metrics = set(parsed.metric_hints)
    if metric_synonym is not None:
        allowed_metrics.add(metric_synonym)
    hits: list[dict[str, Any]] = []
    for family in discover_families(claims_dir):
        if not is_index_fresh(family, claims_dir):
            continue
        index_path = claims_dir / f"{family}.index.jsonl"
        claims_path = claims_dir / f"{family}.jsonl"
        try:
            with open(index_path, "r", encoding="ascii", errors="strict") as f:
                index_lines = f.readlines()
        except (OSError, UnicodeDecodeError):
            continue
        seen_groups: set[tuple[Any, Any]] = set()
        for line in index_lines:
            line = line.strip()
            if not line:
                continue
            try:
                idx_row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if idx_row.get("verdict") != VERIFIED:
                continue
            if allowed_metrics and idx_row.get("metric") not in allowed_metrics:
                continue
            if parsed.window_hint and idx_row.get("window") != parsed.window_hint:
                continue
            if not entity_key_matches(idx_row.get("entity_key"), entity_type, idx_row.get("claim_id", "")):
                continue
            group = (idx_row.get("metric"), idx_row.get("window"))
            if group in seen_groups:
                continue  # duplicate leaderboard -- already read (or ruled out) for this family
            seen_groups.add(group)
            row = seek_claim_row(claims_path, idx_row.get("byte_offset", 0))
            if row is None or row.get("kind") != "ranking":
                continue
            # Same NAME-KEYED fallback chain as ask_families._answer_entity_lookup
            # (probe regression 2026-07-19: the referee family has a fresh index,
            # so THIS check -- not the slow path's -- decided the answer, and it
            # still only looked at player_name, dropping entity_id-as-name rows).
            if not any(
                _ascii_fold(str(r.get("player_name") or r.get("entity_name") or r.get("entity_id") or "")
                            ).strip().lower() == name_key
                for r in row.get("ranking", [])
            ):
                continue  # discarded here -- never retained past this check
            hits.append(dict(
                row,
                _validator_source=_display_path(claims_dir / f"{family}_validation.json", repo_root),
                _producer_source=_display_path(claims_path, repo_root),
            ))
    return hits

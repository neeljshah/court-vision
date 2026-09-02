"""scripts.platformkit.soccer_event_asof -- StatsBomb event-grain FEASIBILITY
CENSUS for the eleven event-grain soccer mechanisms (gap S65).

WHY THIS IS A CENSUS AND NOT A FEATURE BUILDER. S53 left eleven of the fifteen
soccer mechanisms NOT_TESTABLE because their ingredient (score state, shot type,
PPDA, goal-kick height, tactical shift, substitution minute, possession id,
play_pattern) lives at StatsBomb event grain and nowhere at match grain. The
event grain DOES exist on disk (data/cache/statsbomb/events, 4,235 match files,
13 GB) and every one of those ingredients is present in it -- verified by reading
one Premier League 2015/16 file: Shot.shot.type.name, Pass.pass.height.name on
pass.type.name == "Goal Kick", Substitution.minute, Tactical Shift, play_pattern,
possession, Pressure/Duel/Interception for PPDA.

What is NOT present is OVERLAP. This module measures it, exactly, and the answer
closes the gap at its limit rather than at a fix:

  StatsBomb matches in the six corpus leagues, inside the spine's date range: 1,815
  ... joining the 25,834-row gate spine on (date, league, home, away):        1,740
  ... of those, inside the 16,322-row SCORED frame (the close-joined states):   160

  coverage of any event-grain as-of column, against the scored frame: 160/16,322
  = 0.009803, against mechanism_close_effect.MIN_COVERAGE = 0.25.

The 1,740 joins are validated independently of the name crosswalk: StatsBomb's
own scoreline reproduces the spine's over-2.5 label on 1,740 / 1,740 = 1.000000,
and the 1,740 rows are 1,740 distinct event_ids and 1,740 distinct match_ids.

The bar is 25x away and is NEVER lowered (contract B10 / Q3). Restricting the
scored frame to the covered rows would be exactly the circular metric B1 forbids.
So no event-grain feature parquet is built here, no event JSON is parsed, and no
column is joined onto the spine: a column that cannot clear the bar is dead
weight on the corpus, and S22's tally cannot move.

The overlap is a calendar fact, not a name-matching artifact: StatsBomb's full
league seasons are 2015/16 (Premier League, La Liga, Serie A, Ligue 1) while the
soccer close only starts 2019-08-02, so the four full seasons contribute ZERO
scored rows. The 160 come from five partial single-team seasons (La Liga
2019/20 and 2020/21 = Barcelona's matches, Ligue 1 2021/22 and 2022/23 = Paris
Saint-Germain's, Bundesliga 2023/24 = Bayer Leverkusen's).

LICENCE: docs/evidence/harness/LICENCE_statsbomb_open_data.md. Research and
analysis are permitted with attribution; commercial exploitation of the data or
of any analysis derived from it is forbidden (User Agreement 1.2.2), and the data
may not be redistributed (1.2.1) -- so nothing under data/cache/statsbomb is ever
committed and no derived column may ship into a commercial product.

DESCRIPTIVE_ONLY. Calibration language only; nothing scored, promoted or charged.

CLI: python -m scripts.platformkit.soccer_event_asof
"""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_CORPUS = REPO_ROOT / "data/cache/combo/gate_corpus_soccer.parquet"
SB_META = REPO_ROOT / "data/cache/statsbomb/match_meta_full.parquet"
CENSUS_OUT = REPO_ROOT / "docs/evidence/harness/S65_soccer_event_asof_census.json"

# StatsBomb competition-name prefix -> football-data.co.uk div code (corpus_unit).
LEAGUES = {"Serie_A": "I1", "La_Liga": "SP1", "Premier_League": "E0",
           "Ligue_1": "F1", "1__Bundesliga": "D1"}

# The eleven mechanisms S53 left NOT_TESTABLE for want of event grain, and the
# StatsBomb field that would carry each one. Every field was confirmed present in
# a real event file; only the overlap is missing.
EVENT_GRAIN_INGREDIENTS = {
    "team_time_score_state_conditioned_shot_model": "score state from goal events + minute",
    "first_goal_timing_predicts_final_result": "minute of the first Shot with outcome Goal",
    "leading_team_defensive_shell": "score state + shots per minute",
    "set_piece_vs_open_play_shot_conversion": "shot.type.name",
    "pressing_intensity_ppda_proxy": "opponent Pass count / own Pressure+Duel+Interception",
    "goalkeeper_distribution_style": "pass.height.name where pass.type.name == Goal Kick",
    "formation_change_mid_match_impact": "Tactical Shift event",
    "first_substitution_timing": "Substitution.minute",
    "trailing_team_shot_rate_vs_tied": "score state + shots per minute",
    "xg_additivity_shot_rebound_clusters": "possession id + shot.statsbomb_xg",
    "defensive_block_depth_counterattack_share": "play_pattern + defensive-action location",
}

# Names fuzzy matching cannot reach: a different club word order, an accent the
# gate slug drops, or a near-collision (Hertha Berlin matches union_berlin at a
# higher ratio than hertha). Wrong here = a silently WRONG join, so it is manual.
MANUAL_TEAMS = {
    "Athletic Club": "ath_bilbao",
    "Deportivo Alaves": "alaves",
    "Borussia Monchengladbach": "m_gladbach",
    "FSV Mainz 05": "mainz",
    "Hertha Berlin": "hertha",
    "Paris Saint-Germain": "paris_sg",
    "Stade Brestois": "brest",
    "Stade Malherbe Caen": "caen",
}

_STOPWORDS = {"fc", "cf", "ac", "ssc", "us", "ss", "sc", "calcio", "club",
              "de", "cd", "rc", "if", "afc"}


def _ascii(text: str) -> str:
    """Accent-stripped lowercase words; the two corpora spell clubs differently."""
    flat = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", flat.lower()).strip()


def _key(name: str) -> str:
    tokens = [t for t in _ascii(name).split() if t not in _STOPWORDS]
    return " ".join(tokens) or _ascii(name)


def load_gate_spine() -> pd.DataFrame:
    """The 25,834-row spine, with the home/away slugs parsed out of event_id.

    event_id is `YYYYMMDD-<div>-<home_slug>-<away_slug>`; the slugs themselves
    contain no '-' (underscores instead), so a 3-way split is exact.
    """
    spine = pd.read_parquet(GATE_CORPUS, columns=["event_id", "corpus_unit", "event_date"])
    head = spine["event_id"].str.split("-", n=2, expand=True)
    pair = head[2].str.split("-", n=1, expand=True)
    spine["home_slug"], spine["away_slug"] = pair[0], pair[1]
    if spine["away_slug"].isna().any():
        raise ValueError("unparsable event_id in the soccer gate spine")
    return spine


def load_statsbomb_meta(spine: pd.DataFrame) -> pd.DataFrame:
    """StatsBomb matches in the six corpus leagues, inside the spine's dates."""
    meta = pd.read_parquet(SB_META)
    meta["corpus_unit"] = meta["competition"].map(
        lambda comp: next((unit for prefix, unit in LEAGUES.items()
                           if comp.startswith(prefix + "_1") or comp.startswith(prefix + "_2")),
                          None))
    meta = meta[meta["corpus_unit"].notna()].copy()
    meta["match_date"] = pd.to_datetime(meta["match_date"])
    return meta[meta["match_date"] >= spine["event_date"].min()].reset_index(drop=True)


def build_crosswalk(spine: pd.DataFrame, meta: pd.DataFrame) -> tuple[dict, list]:
    """(unit, StatsBomb team) -> gate slug. Returns (crosswalk, unmapped names).

    Unmapped names are RETURNED, never dropped silently -- an unmapped club is a
    match that vanishes from the overlap count, which is the number this whole
    census rests on.
    """
    crosswalk, unmapped = {}, []
    for unit in sorted(meta["corpus_unit"].unique()):
        rows = spine[spine["corpus_unit"] == unit]
        slugs = sorted(set(rows["home_slug"]) | set(rows["away_slug"]))
        by_key = {_key(slug.replace("_", " ")): slug for slug in slugs}
        sb_rows = meta[meta["corpus_unit"] == unit]
        for name in sorted(set(sb_rows["home_team"]) | set(sb_rows["away_team"])):
            manual = MANUAL_TEAMS.get(name) or MANUAL_TEAMS.get(_ascii(name).title())
            if manual is None:
                for raw, slug in MANUAL_TEAMS.items():
                    if _key(raw) == _key(name):
                        manual = slug
                        break
            if manual is not None:
                crosswalk[(unit, name)] = manual
                continue
            close = difflib.get_close_matches(_key(name), list(by_key), n=1, cutoff=0.62)
            if close:
                crosswalk[(unit, name)] = by_key[close[0]]
            else:
                unmapped.append((unit, name))
    return crosswalk, unmapped


def overlap(spine: pd.DataFrame, meta: pd.DataFrame, crosswalk: dict) -> pd.DataFrame:
    """StatsBomb matches joined to spine rows on (date, unit, home, away).

    Date-EXACT and orientation-preserving on purpose: a tolerance window or an
    unordered team pair would both manufacture overlap that is not there.
    """
    sb = meta.copy()
    sb["home_slug"] = [crosswalk.get((u, n)) for u, n in zip(sb["corpus_unit"], sb["home_team"])]
    sb["away_slug"] = [crosswalk.get((u, n)) for u, n in zip(sb["corpus_unit"], sb["away_team"])]
    joined = sb.merge(spine, left_on=["match_date", "corpus_unit", "home_slug", "away_slug"],
                      right_on=["event_date", "corpus_unit", "home_slug", "away_slug"],
                      how="left")
    return joined[joined["event_id"].notna()].copy()


def scored_event_ids() -> set:
    """event_ids of the close-joined states -- the frame coverage is measured on."""
    from scripts.platformkit.eval_gate import close_join
    return {str(state["game_id"])
            for state in close_join.gate_corpus_states("soccer", "2015-01-01", "2026-12-31")}


def census() -> dict:
    """Every denominator behind the S65 CLOSED AT LIMIT verdict, in one dict."""
    from scripts.platformkit.analytics_showcase.mechanism_close_effect import MIN_COVERAGE

    spine = load_gate_spine()
    meta = load_statsbomb_meta(spine)
    crosswalk, unmapped = build_crosswalk(spine, meta)
    joined = overlap(spine, meta, crosswalk)
    scored = scored_event_ids()
    in_scored = joined[joined["event_id"].astype(str).isin(scored)]
    ceiling = len(in_scored) / len(scored) if scored else 0.0
    # Independent of the name crosswalk: a mispaired join would break this.
    labels = joined.merge(pd.read_parquet(GATE_CORPUS, columns=["event_id", "y"]), on="event_id")
    sb_over = ((labels["home_score"] + labels["away_score"]) >= 3).astype(float)
    agreement = float((sb_over == labels["y"]).mean()) if len(labels) else 0.0
    return {
        "label": "DESCRIPTIVE_ONLY",
        "gap": "S65",
        "licence": "docs/evidence/harness/LICENCE_statsbomb_open_data.md",
        "verdict": "CLOSED AT LIMIT",
        "n_spine_rows": int(len(spine)),
        "n_scored_rows": len(scored),
        "n_statsbomb_in_league_in_window": int(len(meta)),
        "n_unmapped_team_names": len(unmapped),
        "unmapped_team_names": [f"{unit}:{name}" for unit, name in unmapped],
        "n_overlap_spine": int(len(joined)),
        "n_overlap_spine_distinct_event_ids": int(joined["event_id"].nunique()),
        "n_overlap_spine_distinct_match_ids": int(joined["match_id"].nunique()),
        "join_label_agreement": round(agreement, 6),
        "overlap_spine_share": round(len(joined) / len(spine), 6),
        "overlap_spine_by_unit": joined["corpus_unit"].value_counts().to_dict(),
        "n_overlap_scored": int(len(in_scored)),
        "coverage_ceiling_scored": round(ceiling, 6),
        "coverage_ceiling_by_unit": in_scored["corpus_unit"].value_counts().to_dict(),
        "coverage_ceiling_by_competition": in_scored["competition"].value_counts().to_dict(),
        "min_coverage_bar": MIN_COVERAGE,
        "bar_shortfall_factor": round(MIN_COVERAGE / ceiling, 1) if ceiling else None,
        "bar_moved": False,
        "event_grain_ingredients_present_but_unusable": EVENT_GRAIN_INGREDIENTS,
        "why": "StatsBomb's full league seasons are 2015/16; the soccer close starts "
               "2019-08-02, so the four full seasons contribute 0 scored rows and only "
               "three partial single-team seasons remain.",
    }


def main(argv: list[str] | None = None) -> int:
    result = census()
    CENSUS_OUT.parent.mkdir(parents=True, exist_ok=True)
    CENSUS_OUT.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="ascii")
    print("StatsBomb in-league matches inside the spine window: %d"
          % result["n_statsbomb_in_league_in_window"])
    print("unmapped team names: %d %s" % (result["n_unmapped_team_names"],
                                          result["unmapped_team_names"]))
    print("join validated: statsbomb scoreline reproduces the spine over-2.5 label on "
          "%d / %d = %.6f" % (result["n_overlap_spine"], result["n_overlap_spine"],
                              result["join_label_agreement"]))
    print("overlap with the %d-row spine:   %d (%.6f) %s"
          % (result["n_spine_rows"], result["n_overlap_spine"],
             result["overlap_spine_share"], result["overlap_spine_by_unit"]))
    print("overlap with the %d-row SCORED frame: %d (%.6f) %s"
          % (result["n_scored_rows"], result["n_overlap_scored"],
             result["coverage_ceiling_scored"], result["coverage_ceiling_by_unit"]))
    print("MIN_COVERAGE bar %.2f -- short by a factor of %s; bar NOT moved"
          % (result["min_coverage_bar"], result["bar_shortfall_factor"]))
    print("verdict:", result["verdict"], "-- wrote", CENSUS_OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

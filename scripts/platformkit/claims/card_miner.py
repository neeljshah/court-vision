"""scripts.platformkit.claims.card_miner -- seed real hypothesis cards.

STEP 0 (done, reported here rather than re-run every import): searched for
the sources the seeding brief named, in priority order:

  1. matchup_report.py "predictive_candidates" w/ status=UNVALIDATED_CANDIDATE,
     applied_to_model=false -- NOT FOUND. No file named matchup_report.py and
     no "predictive_candidates" / "UNVALIDATED_CANDIDATE" string anywhere
     under scripts/ or data/ (grep across both, 0 hits). This source is
     EMPTY -- no filler card was invented to compensate.
  2. data/cache/profiles/TEAM_REPORTS.json -- FOUND. 30-team dossier with
     offensive_identity / defensive_identity / strengths_weaknesses blocks
     (pace_identity, spacing_z, transition_share, rim_fg_pct_allowed,
     paint_protection_score, opp_tov_pct_forced, perimeter_denial_score, ...).
     Real, differentiated, per-team fields -- used below.
  3. The named pre-registered experiment (matchup prior x realized-vs-
     expected deviation, midQ1/endQ1) -- hardcoded as card #1 per the brief.

Everything mined here is a STYLE-MISMATCH CLASS (e.g. "team weak on X faces
opponent strong on the thing X exploits"), each with its own written
mechanism, evaluable pregame from the two teams' TEAM_REPORTS.json fields --
not a per-game-instance card (that instantiation is Phase 3's job).
"""
from __future__ import annotations

from typing import Any

SOURCE1_STATUS = "EMPTY: no matchup_report.py / predictive_candidates found under scripts/ or data/"

# One pre-registered experiment (card #1, REQUIRED first).
CARD_1_PREREGISTERED: dict[str, Any] = {
    "claim": (
        "In the midQ1-endQ1 window, when the PREGAME matchup-fit prior "
        "(scheme/pace mismatch) agrees in direction with the realized "
        "score-margin deviation from the pregame-expected margin, that "
        "deviation is more likely signal than noise -- i.e. it should move "
        "the live win-probability MORE than a naive score-only re-pricer moves it."
    ),
    "condition": {
        "scope": "ingame",
        "window": "midQ1_to_endQ1",
        "trigger": (
            "quarter == 1 and clock_seconds_elapsed >= 360 "
            "and abs(margin_deviation_asof) >= 4"
        ),
        "entity": "game",
    },
    "mechanism": (
        "The NBA in-game player-profile conditioning experiment (closed "
        "2026-07-05, REJECT at n=74) tested STATIC per-player profile "
        "conditioning alone and found no edge. It never tested the cross "
        "term: PREGAME matchup prior (style/pace fit) x REALIZED deviation "
        "from that same prior's implied margin, restricted to the earliest "
        "window before variance narrows. A live re-pricer that only reads "
        "the box score treats a 4-point Q1 swing as pure noise regardless "
        "of whether it matches or fights the pregame matchup read; if the "
        "matchup prior predicted that swing's direction, the market's "
        "naive re-pricer is slower to react than it should be. This is the "
        "prescribed-but-unrun cross-term experiment from that NULL result."
    ),
    "expected_sign": "+",
    "expected_magnitude": "calibration-scale (leak-free Brier delta), not a $ edge; PROVISIONAL until graded",
    "source": "matchup-head NULL prescribed experiment (memory: project_nba_ingame_profile_closed_2026_07_05)",
}


def _pregame_style_cards() -> list[dict[str, Any]]:
    """9 style-mismatch cards grounded in real TEAM_REPORTS.json fields.

    Each trigger uses only pregame-prior fields (percentile diffs between
    the two teams' static season-to-date identity, known before tip) that
    are already in card_registry.ALLOWED_TRIGGER_FIELDS.
    """
    return [
        {
            "claim": "A team in the bottom transition-defense quartile facing a top-quartile transition-share opponent gives up more than the pregame line prices for pace-adjusted defensive rating.",
            "condition": {"scope": "pregame", "trigger": "def_transition_pctile_home <= 0.25 and opp_transition_share_pctile_away >= 0.75", "entity": "game"},
            "mechanism": "TEAM_REPORTS.json defensive_identity.opp_transition_pg and offensive_identity.transition_share are both static season-to-date identity fields; pregame market ratings are efficiency-marginal averages that do not condition on which specific opponent style each team faces, so a transition-heavy attacker against a transition-leaky defense is a stylistic mismatch the average-based line underweights.",
            "expected_sign": "-",
            "expected_magnitude": "small (a few points of pace-adjusted def_rtg), calibration-scale",
        },
        {
            "claim": "A team with poor floor-spacing (bottom quartile spacing_z) facing an opponent with strong perimeter-denial defense underperforms its pregame-implied half-court efficiency.",
            "condition": {"scope": "pregame", "trigger": "spacing_pctile_home <= 0.25 and opp_perimeter_denial_pctile_away >= 0.75", "entity": "game"},
            "mechanism": "offensive_identity.spacing_z and defensive_identity.scheme_axes.perimeter_denial_score are both real, differentiated per-team fields; poor spacing compresses driving/passing lanes that a strong perimeter-denial scheme is specifically built to exploit, a style interaction not captured by aggregate efficiency ratings.",
            "expected_sign": "-",
            "expected_magnitude": "small, half-court eFG% shift",
        },
        {
            "claim": "A team with weak rim protection (bottom-quartile paint_protection_score) facing an opponent with a high rim-scoring frequency concedes more paint points than its pregame def_rtg implies.",
            "condition": {"scope": "pregame", "trigger": "paint_protection_pctile_home <= 0.25 and opp_rim_freq_pctile_away >= 0.75", "entity": "game"},
            "mechanism": "defensive_identity.scheme_axes.paint_protection_score and rim_freq_faced are direct per-team fields; a rim-attacking opponent specifically stresses the exact weakness the aggregate def_rtg averages away across all opponent shot profiles.",
            "expected_sign": "-",
            "expected_magnitude": "small, rim-fg-pct-allowed shift",
        },
        {
            "claim": "A FAST pace-identity team facing an opponent with a strong pace_control_score (bottom-quartile pace) plays fewer total possessions than the pregame total implies.",
            "condition": {"scope": "pregame", "trigger": "pace_identity_home_fast and opp_pace_control_pctile_away >= 0.75", "entity": "game"},
            "mechanism": "offensive_identity.pace_identity and defensive_identity.scheme_axes.pace_control_score are both real fields; a strong pace-control defense is specifically designed to drag a fast team down, and the pregame total is typically an average-of-two-paces figure that does not fully discount for one team's demonstrated ability to impose its pace on opponents.",
            "expected_sign": "-",
            "expected_magnitude": "small, total-possessions shift",
        },
        {
            "claim": "A team strong on offensive rebounding (top-quartile oreb) facing an opponent weak on defensive rebounding grabs more second-chance possessions than the pregame rebounding-neutral line assumes.",
            "condition": {"scope": "pregame", "trigger": "oreb_pctile_home >= 0.75 and opp_dreb_pctile_away <= 0.25", "entity": "game"},
            "mechanism": "rebounding block fields in TEAM_REPORTS.json (oreb_pct / dreb_pct) are real per-team differentiators; oreb strength vs dreb weakness is a direct, mechanical mismatch (extra shot attempts), not an average-blended effect.",
            "expected_sign": "+",
            "expected_magnitude": "small, extra-possessions shift",
        },
        {
            "claim": "A team that forces turnovers at a high rate (top-quartile opp_tov_pct_forced) facing a high-turnover-rate opponent generates more live-ball transition chances than the pregame line prices.",
            "condition": {"scope": "pregame", "trigger": "tov_forced_pctile_home >= 0.75 and opp_tov_rate_pctile_away >= 0.75", "entity": "game"},
            "mechanism": "defensive_identity.opp_tov_pct_forced (forcing team) crossed with the opponent's own turnover rate is a real two-sided field pair; both teams' identity metrics compound in the SAME direction here, an interaction pregame averaging treats as independent.",
            "expected_sign": "+",
            "expected_magnitude": "small, transition-possessions shift",
        },
        {
            "claim": "A team with strong closeout defense (top-quartile closeout_score) facing a spot-up-heavy 3PA-rate opponent suppresses that opponent's 3PA rate below its season average.",
            "condition": {"scope": "pregame", "trigger": "closeout_pctile_home >= 0.75 and opp_3pa_rate_pctile_away >= 0.75", "entity": "game"},
            "mechanism": "defensive_identity.scheme_axes.closeout_score is a real per-team scheme metric; it specifically targets spot-up 3PA volume, a stylistic counter the opponent's blended season-average 3PA rate does not anticipate game-to-game.",
            "expected_sign": "-",
            "expected_magnitude": "small, opp 3PA-rate shift",
        },
        {
            "claim": "Two teams sharing 2+ overlapping scheme_tags (e.g. both SWITCH HEAVY) play a slower, more half-court-heavy game than the pregame pace-average total implies.",
            "condition": {"scope": "pregame", "trigger": "scheme_tag_overlap", "entity": "game"},
            "mechanism": "all_scheme_tags in defensive_identity is a real categorical field; two switch-heavy defenses facing each other tend to grind possessions into iso/post looks (both schemes discourage the actions that generate quick transition points), a same-direction interaction a pace-average total does not model.",
            "expected_sign": "-",
            "expected_magnitude": "small, pace/total shift",
        },
        {
            "claim": "A team with a large pace-identity gap vs its opponent (pace_identity_diff extreme) sees its own offensive rating deviate from its season average toward whichever team controls tempo.",
            "condition": {"scope": "pregame", "trigger": "pace_identity_diff", "entity": "team"},
            "mechanism": "offensive_identity.pace_pg is a continuous real field; large pace gaps are a known tempo-control interaction (the faster or more pace-controlling team tends to impose more of its style than a possession-weighted average predicts), which pregame ratings compute as team-marginal, not matchup-conditional.",
            "expected_sign": "+",
            "expected_magnitude": "small, off_rtg deviation",
        },
    ]


def mine_source2_cards() -> list[dict[str, Any]]:
    """Return the 9 style-mismatch cards mined from TEAM_REPORTS.json fields."""
    return _pregame_style_cards()


def all_seed_cards() -> list[dict[str, Any]]:
    """Card #1 (pre-registered) first, then up to 9 from source 2. No filler."""
    cards = [CARD_1_PREREGISTERED]
    cards.extend(mine_source2_cards())
    return cards[:10]


def seed(registry_module, ts: str) -> list[dict[str, Any]]:
    """Register every seed card via *registry_module* (card_registry). Returns results."""
    results = []
    for card in all_seed_cards():
        res = registry_module.register(
            claim=card["claim"],
            condition=card["condition"],
            mechanism=card["mechanism"],
            expected_sign=card["expected_sign"],
            expected_magnitude=card["expected_magnitude"],
            source=card.get("source", "profile-mined: data/cache/profiles/TEAM_REPORTS.json"),
            ts=ts,
        )
        results.append(res)
    return results


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(__file__).rsplit("scripts", 1)[0])
    from scripts.platformkit.claims import card_registry as _reg

    print(SOURCE1_STATUS)
    _ts = "2026-07-14T00:00:00Z"
    for _r in seed(_reg, _ts):
        print(_r)

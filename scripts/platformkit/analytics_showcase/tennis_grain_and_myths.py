"""Tennis grain and myths -- three honest stories curated from committed tennis verdicts.

Pure filtering/grouping of ONE already-committed artifact (fwd_claim_scoreboard.json):
picks specific tennis claim families and groups them into three stories -- momentum's
grain limit, two null tiebreak myths, and confirmed/replicated altitude+travel effects.
No new data, no new science -- just an honest curated re-statement of verdicts already
on the record.

DESCRIPTIVE_ONLY, edge_claimed=False -- no $/ROI claim, no new corpus.

Usage:
    python -m scripts.platformkit.analytics_showcase.tennis_grain_and_myths
    python -m scripts.platformkit.analytics_showcase.tennis_grain_and_myths --check
"""
import json
import math
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHOWCASE = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase")
IN_JSON = os.path.join(SHOWCASE, "out", "fwd_claim_scoreboard.json")
OUT_JSON = os.path.join(SHOWCASE, "out", "tennis_grain_and_myths.json")

# (hypothesis, reading, expected_verdict, expected_n) -- expected_* asserted at build time.
STORY_SPECS = [
    ("momentum_grain", "Momentum has a grain limit", [
        ("point_to_point_momentum",
         "Real, small effect: winning the last point raises win probability on the very next point.",
         "CONFIRMED_LOCAL", 456383),
        ("post_break_hold_rate",
         "Dead at game grain: no detectable effect on whether a player holds serve after breaking.",
         "NULL_LOCAL", 21208),
        ("post_break_hold_rate__split_A",
         "Split-half corroboration (first half): still null.",
         "NULL_LOCAL", 10522),
        ("post_break_hold_rate__split_B",
         "Split-half corroboration (second half): still null.",
         "NULL_LOCAL", 10686),
    ]),
    ("tiebreak_myths", "Two tiebreak myths, both null", [
        ("tiebreak_skill_persistence_partial",
         "No evidence that tiebreak skill persists as a stable player trait.",
         "NULL_LOCAL", 206),
        ("tiebreak_serve_order_win_rate",
         "The 'serve first in the breaker' myth: no detectable edge from serve order.",
         "NULL_LOCAL", 1281),
    ]),
    ("altitude_travel", "Altitude and travel, confirmed", [
        ("altitude_effect_on_serve_ace_rate",
         "Altitude lowers ace rate (thinner air behaves differently than folklore predicts).",
         "CONFIRMED_LOCAL", 27463),
        ("altitude_effect_on_serve_ace_rate__replication_years_2015_2020",
         "Replicates on the 2015-2020 year slice.",
         "REPLICATED", 14329),
        ("altitude_effect_on_serve_ace_rate__replication_years_2021_2025",
         "Replicates independently on the 2021-2025 year slice too.",
         "REPLICATED", 13134),
        ("long_travel_effect_on_win_prob_partial",
         "Long travel measurably lowers win probability.",
         "CONFIRMED_LOCAL", 26950),
    ]),
]

STORY_SUMMARIES = {
    "momentum_grain": ("Momentum is real at the point grain (CONFIRMED_LOCAL, n=456383) but the "
                        "same idea dies once you zoom out to game grain: whether a player holds "
                        "serve after breaking is NULL_LOCAL, confirmed null on both split halves."),
    "tiebreak_myths": ("Two popular tiebreak beliefs -- that some players have a persistent "
                        "tiebreak-clutch skill, and that serving first in the breaker matters -- "
                        "both come back NULL_LOCAL."),
    "altitude_travel": ("Altitude suppresses serve ace rate and long travel suppresses win "
                         "probability, both CONFIRMED_LOCAL; the altitude effect was independently "
                         "REPLICATED on two disjoint year slices (2015-2020 and 2021-2025)."),
}


def _find(families, hypothesis):
    for f in families:
        if f.get("sport") == "tennis" and f.get("hypothesis") == hypothesis:
            return f
    return None


def _build_claim(fam, reading):
    last = fam["history"][-1]
    return {
        "hypothesis": fam["hypothesis"],
        "verdict": last["verdict"],
        "n": last["n"],
        "effect": last["effect"],
        "corpus": last["corpus"],
        "reading": reading,
    }


def build():
    with open(IN_JSON, encoding="utf-8") as f:
        source = json.load(f)
    families = source["families"]

    stories = []
    for key, title, claim_specs in STORY_SPECS:
        claims = []
        for hypothesis, reading, expected_verdict, expected_n in claim_specs:
            fam = _find(families, hypothesis)
            if fam is None:
                raise AssertionError(f"missing tennis family: {hypothesis}")
            last = fam["history"][-1]
            if last["verdict"] != expected_verdict or last["n"] != expected_n:
                raise AssertionError(
                    f"{hypothesis}: expected verdict={expected_verdict} n={expected_n}, "
                    f"got verdict={last['verdict']} n={last['n']}")
            claims.append(_build_claim(fam, reading))
        stories.append({
            "key": key,
            "title": title,
            "summary": STORY_SUMMARIES[key],
            "claims": claims,
        })

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "descriptive_only": True,
        "edge_claimed": False,
        "headline": ("Tennis momentum is real point-to-point but dies at the game grain; two "
                     "tiebreak myths are null; altitude and travel effects are confirmed "
                     "(altitude replicated across two disjoint year slices)."),
        "method": ("These are our own preregistered tennis tests, surfaced verbatim from the "
                   "committed forward-claim scoreboard. A CONFIRMED_LOCAL/REPLICATED/NULL_LOCAL "
                   "verdict is an accuracy/effect finding, not a betting edge."),
        "source_artifact": "scripts/platformkit/analytics_showcase/out/fwd_claim_scoreboard.json",
        "stories": stories,
        "confounds": [
            "effect signs are raw directional effects on the stated metric, not "
            "opponent/surface-adjusted;",
            "corpora differ (slam point-level 2011-2015 vs match-level 2015-2025); each claim "
            "shows its own corpus;",
            "CONFIRMED/NULL are OUR preregistered leak-free verdicts vs an internal baseline -- "
            "descriptive accuracy findings, never a dollar-edge claim.",
        ],
    }

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)
    return payload


def _print_summary(payload):
    print(payload["headline"])
    for story in payload["stories"]:
        print(f"[{story['key']}] {story['title']}  ({len(story['claims'])} claims)")
        for c in story["claims"]:
            print(f"    {c['hypothesis']}: {c['verdict']} n={c['n']} effect={c['effect']} "
                  f"corpus={c['corpus']}")


def check():
    payload = build()
    with open(IN_JSON, encoding="utf-8") as f:
        source = json.load(f)
    families = source["families"]

    assert len(payload["stories"]) == 3, "expected exactly 3 stories"

    for key, _title, claim_specs in STORY_SPECS:
        story = next(s for s in payload["stories"] if s["key"] == key)
        assert len(story["claims"]) == len(claim_specs)
        for c in story["claims"]:
            fam = _find(families, c["hypothesis"])
            assert fam is not None, f"missing in source: {c['hypothesis']}"
            last = fam["history"][-1]
            assert c["n"] == last["n"], (c["hypothesis"], "n mismatch")
            assert c["verdict"] == last["verdict"], (c["hypothesis"], "verdict mismatch")
            assert c["corpus"], (c["hypothesis"], "empty corpus")
            assert c["effect"] is None or isinstance(c["effect"], (int, float)), \
                (c["hypothesis"], "effect not numeric/null")

    # spot-check the exact values called out in the task spec
    expected = {
        "point_to_point_momentum": ("CONFIRMED_LOCAL", 456383, 0.0216, "slam_points_2011_2015"),
        "post_break_hold_rate": ("NULL_LOCAL", 21208, 0.0051, "slam_points"),
        "tiebreak_skill_persistence_partial": ("NULL_LOCAL", 206, 0.0745,
                                                "matches_asof_setdetail_schedule_density_atp_wta"),
        "tiebreak_serve_order_win_rate": ("NULL_LOCAL", 1281, 0.0035, "slam_points"),
        "altitude_effect_on_serve_ace_rate": ("CONFIRMED_LOCAL", 27463, -0.0083,
                                               "travel_scouting_matches_atp_wta_2015_2025"),
        "altitude_effect_on_serve_ace_rate__replication_years_2015_2020": ("REPLICATED", 14329,
                                                                            -0.0078, None),
        "altitude_effect_on_serve_ace_rate__replication_years_2021_2025": ("REPLICATED", 13134,
                                                                            -0.0089, None),
        "long_travel_effect_on_win_prob_partial": ("CONFIRMED_LOCAL", 26950, -0.0699,
                                                    "travel_scouting_matches_atp_wta_2015_2025"),
    }
    all_claims = {c["hypothesis"]: c for s in payload["stories"] for c in s["claims"]}
    for hyp, (verdict, n, effect, corpus) in expected.items():
        c = all_claims[hyp]
        assert c["verdict"] == verdict, (hyp, c["verdict"], verdict)
        assert c["n"] == n, (hyp, c["n"], n)
        assert c["effect"] == effect, (hyp, c["effect"], effect)
        if corpus is not None:
            assert c["corpus"] == corpus, (hyp, c["corpus"], corpus)

    def _no_nan(x):
        if isinstance(x, float):
            assert not math.isnan(x) and not math.isinf(x)
        elif isinstance(x, dict):
            for v in x.values():
                _no_nan(v)
        elif isinstance(x, list):
            for v in x:
                _no_nan(v)

    _no_nan(payload)
    print("OK")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        p = build()
        _print_summary(p)

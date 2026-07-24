"""NBA momentum tested -- an honest split curated from committed NBA verdicts.

Pure filtering/grouping of ONE already-committed artifact (fwd_claim_scoreboard.json):
picks specific basketball_nba claim families and splits them into what's REAL
(structural fatigue/rest/clutch momentum-shaped effects, confirmed and replicated)
vs what's NULL (individual game-to-game "hot/cold" carryover shapes). No new data,
no new science -- just an honest curated re-statement of verdicts already on record.

This is NOT "momentum is a myth." Structural effects (back-to-backs, three-in-four
fatigue, clutch-lineup shortening, timeouts breaking runs) are real and some
replicate independently. It's the individual streak/carryover shapes (player B2B
scoring dips, foul-trouble shifts, rest-differential margin) that come back null.

DESCRIPTIVE_ONLY, edge_claimed=False -- no $/ROI claim, no new corpus.

Usage:
    python -m scripts.platformkit.analytics_showcase.nba_momentum_tested
    python -m scripts.platformkit.analytics_showcase.nba_momentum_tested --check
"""
import json
import math
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHOWCASE = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase")
IN_JSON = os.path.join(SHOWCASE, "out", "fwd_claim_scoreboard.json")
OUT_JSON = os.path.join(SHOWCASE, "out", "nba_momentum_tested.json")

# (hypothesis, reading, expected_verdict, expected_n) -- expected_* asserted at build time.
GROUP_SPECS = [
    ("real", "Momentum-shaped effects that ARE real",
     "Structural fatigue, rest, and clutch effects are confirmed -- some independently "
     "replicated -- these are real momentum-shaped dynamics, just not the individual "
     "hot-hand kind.", [
        ("b2b_rest_penalty",
         "Playing on a back-to-back measurably drags down scoring output.",
         "CONFIRMED_LOCAL", 7192, -1.955),
        ("three_in_four_fatigue",
         "Three games in four nights compounds the fatigue drag further.",
         "CONFIRMED_LOCAL", 7222, -1.213),
        ("clutch_lineup_shortening",
         "Coaches measurably shorten rotations in clutch minutes.",
         "CONFIRMED_LOCAL", 1052, -6.3384),
        ("clutch_usage_compression",
         "Usage concentrates onto fewer players when the game is on the line.",
         "CONFIRMED_LOCAL", 8164, 0.5031),
        ("timeout_interrupts_opponent_run__h1",
         "Calling a timeout measurably interrupts an opponent's scoring run.",
         "CONFIRMED_LOCAL", 1357, -0.7314),
        ("timeout_interrupts_opponent_run_replication_2022_23",
         "The timeout-breaks-a-run effect replicates independently on the 2022-23 corpus.",
         "REPLICATED", 2544, None),
        ("lineup_continuity_streak_vs_point_diff__2024-25",
         "How long a lineup has stayed together (continuity) measurably relates to point "
         "differential.",
         "CONFIRMED_LOCAL", 2460, 0.0788),
    ]),
    ("null", "The hot/cold carryover shapes that came back null",
     "The individual game-to-game 'streak' shapes -- a player's own B2B scoring, foul "
     "trouble shifting his efficiency or usage, rest differential, or B2B interacting "
     "with starter minutes -- carry no measurable signal past our baseline. NULL here "
     "means 'no signal past baseline,' not 'streaks are impossible.'", [
        ("player_b2b_scoring_dip",
         "A player's own scoring shows no detectable dip on a back-to-back beyond the "
         "team-level rest penalty already captured elsewhere.",
         "NULL_LOCAL", 65103, -0.0053),
        ("rest_differential_margin__h1",
         "The rest-day differential between two teams shows no detectable margin effect.",
         "NULL_LOCAL", 1798, -0.018),
        ("foul_trouble_efficiency_shift__h1",
         "Being in foul trouble shows no detectable shift in a player's scoring efficiency.",
         "NULL_LOCAL", 5972, -0.09861),
        ("foul_trouble_usage_shift__h1",
         "Foul trouble likewise shows no detectable shift in a player's usage rate.",
         "NULL_LOCAL", 5972, 0.00712),
        ("b2b_x_margin_starter_minutes__h1",
         "The interaction of back-to-back rest with point margin shows no detectable "
         "effect on starter minutes.",
         "NULL_LOCAL", 3596, -0.0372),
    ]),
]


def _find(families, hypothesis):
    for f in families:
        if f.get("sport") == "basketball_nba" and f.get("hypothesis") == hypothesis:
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

    groups = []
    for key, title, summary, claim_specs in GROUP_SPECS:
        claims = []
        for hypothesis, reading, expected_verdict, expected_n, expected_effect in claim_specs:
            fam = _find(families, hypothesis)
            if fam is None:
                raise AssertionError(f"missing basketball_nba family: {hypothesis}")
            last = fam["history"][-1]
            if last["verdict"] != expected_verdict or last["n"] != expected_n:
                raise AssertionError(
                    f"{hypothesis}: expected verdict={expected_verdict} n={expected_n}, "
                    f"got verdict={last['verdict']} n={last['n']}")
            if expected_effect is not None and last["effect"] != expected_effect:
                raise AssertionError(
                    f"{hypothesis}: expected effect={expected_effect}, got {last['effect']}")
            claims.append(_build_claim(fam, reading))
        groups.append({
            "key": key,
            "title": title,
            "summary": summary,
            "claims": claims,
        })

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "descriptive_only": True,
        "edge_claimed": False,
        "headline": ("Structural fatigue, rest, and clutch momentum effects in the NBA are "
                     "confirmed -- and some independently replicated -- while the individual "
                     "game-to-game hot/cold carryover shapes (a player's own B2B dip, foul-"
                     "trouble shifts, rest-differential margin) come back null."),
        "method": ("Our own preregistered NBA tests, surfaced verbatim from the committed "
                   "forward-claim scoreboard. A verdict is a leak-free accuracy/effect finding "
                   "vs an internal baseline -- never a betting edge. A NULL is not 'streaks do "
                   "not exist'; it is 'this shape carried no measurable signal past the "
                   "baseline'."),
        "source_artifact": "scripts/platformkit/analytics_showcase/out/fwd_claim_scoreboard.json",
        "groups": groups,
        "confounds": [
            "a gate NULL means 'no measurable value past our baseline', NOT 'this never "
            "happens';",
            "effects are raw directional effects on the stated metric, not opponent/venue-"
            "adjusted;",
            "corpora and seasons differ per claim; each row shows its own corpus;",
            "CONFIRMED/REPLICATED are descriptive accuracy findings, never a dollar-edge "
            "claim.",
        ],
    }

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)
    return payload


def _print_summary(payload):
    print(payload["headline"])
    for group in payload["groups"]:
        print(f"[{group['key']}] {group['title']}  ({len(group['claims'])} claims)")
        for c in group["claims"]:
            print(f"    {c['hypothesis']}: {c['verdict']} n={c['n']} effect={c['effect']} "
                  f"corpus={c['corpus']}")


def check():
    payload = build()
    with open(IN_JSON, encoding="utf-8") as f:
        source = json.load(f)
    families = source["families"]

    assert len(payload["groups"]) == 2, "expected exactly 2 groups"

    real = next(g for g in payload["groups"] if g["key"] == "real")
    null = next(g for g in payload["groups"] if g["key"] == "null")
    assert all(c["verdict"] in ("CONFIRMED_LOCAL", "REPLICATED") for c in real["claims"])
    assert all(c["verdict"] == "NULL_LOCAL" for c in null["claims"])

    for key, _title, _summary, claim_specs in GROUP_SPECS:
        group = next(g for g in payload["groups"] if g["key"] == key)
        assert len(group["claims"]) == len(claim_specs)
        for c in group["claims"]:
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
        "b2b_rest_penalty": ("CONFIRMED_LOCAL", 7192, -1.955),
        "three_in_four_fatigue": ("CONFIRMED_LOCAL", 7222, -1.213),
        "clutch_lineup_shortening": ("CONFIRMED_LOCAL", 1052, -6.3384),
        "clutch_usage_compression": ("CONFIRMED_LOCAL", 8164, 0.5031),
        "timeout_interrupts_opponent_run__h1": ("CONFIRMED_LOCAL", 1357, -0.7314),
        "timeout_interrupts_opponent_run_replication_2022_23": ("REPLICATED", 2544, None),
        "lineup_continuity_streak_vs_point_diff__2024-25": ("CONFIRMED_LOCAL", 2460, 0.0788),
        "player_b2b_scoring_dip": ("NULL_LOCAL", 65103, -0.0053),
        "rest_differential_margin__h1": ("NULL_LOCAL", 1798, -0.018),
        "foul_trouble_efficiency_shift__h1": ("NULL_LOCAL", 5972, -0.09861),
        "foul_trouble_usage_shift__h1": ("NULL_LOCAL", 5972, 0.00712),
        "b2b_x_margin_starter_minutes__h1": ("NULL_LOCAL", 3596, -0.0372),
    }
    all_claims = {c["hypothesis"]: c for g in payload["groups"] for c in g["claims"]}
    for hyp, (verdict, n, effect) in expected.items():
        c = all_claims[hyp]
        assert c["verdict"] == verdict, (hyp, c["verdict"], verdict)
        assert c["n"] == n, (hyp, c["n"], n)
        assert c["effect"] == effect, (hyp, c["effect"], effect)

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

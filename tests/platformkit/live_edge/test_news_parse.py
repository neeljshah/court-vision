"""Per-file test for scripts.platformkit.live_edge.news.parser (A2 golden set).

GOLDEN SET PROVENANCE (all REAL captured text, hand-labeled by reading the
text itself -- never the source's own structured status field, which the
free-text often disagrees with e.g. ESPN's DAY_TO_DAY category vs a
"ruled out" sentence):
  - 12 rows: data/cache/edge_engine/injury_facts_nba.jsonl `detail` field
    (real m39/injury_facts captures, various dates).
  - 16 rows: data/cache/edge_engine/injury_facts_wnba.jsonl `detail` field
    (same real m39 pipeline; WNBA corpus happens to carry the doubtful/
    questionable/probable vocabulary the NBA corpus's summer-league-heavy
    slice lacks -- see PROBE.md sibling note in the A2 report).
  - 1 row: bare "day-to-day" (real, verbatim `detail` value in the WNBA store).
  - 6 rows: THIS SESSION'S live capture, data/omni/live_edge/news/raw/
    2026-07-14.jsonl (fresh, report_ts = actual capture time).
  - 5 rows: real ESPN news headlines (no injury-status word at all) as the
    negative control -- true_status is None.

KNOWN GAP (reported honestly, not papered over): zero real "GTD"/
"game-time decision" examples exist anywhere in the corpora probed for this
lane. The GTD regex rule exists but is UNTESTED by real data today.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.platformkit.live_edge.news.parser import parse_item  # noqa: E402

GOLDEN = [
    # -- NBA injury_facts_nba.jsonl detail field (real) --
    ("Ejiofor (rest) won't play in Tuesday's Salt Lake City Summer League game "
     "against the Grizzlies, Brad Rowland of the Locked On Podcast Network reports.", "OUT"),
    ("Newell (rest) has been ruled out for Tuesday's Salt Lake City Summer League "
     "game against the Grizzlies, Brad Rowland of the Locked On Podcast Network reports.", "OUT"),
    ("Flemings (rest) won't play in Tuesday's Salt Lake City Summer League game "
     "against the Grizzlies, Brad Rowland of the Locked On Podcast Network reports.", "OUT"),
    ("Gilbert (hip) is out for Tuesday's Summer League game against the Grizzlies, "
     "Brad Rowland of the Locked On Podcast Network reports.", "OUT"),
    ("Tatum (knee) has been ruled out for Saturday's Game 7 against the 76ers, "
     "Shams Charania of ESPN reports.", "OUT"),
    ("Wolf (back) is out for Monday's California Classic Summer League Game against "
     "the Warriors Blue, Erik Slater of ClutchPoints.com reports.", "OUT"),
    ("Porter (hamstring) has been ruled out for the remainder of the 2025-26 season, "
     "Erik Slater of ClutchPoints.com reports.", "OUT"),
    ("Mann (knee) is out for Sunday's game against the Raptors, Erik Slater of "
     "ClutchPoints.com reports.", "OUT"),
    ("Okoro (quad) is out for Sunday's game in Dallas.", "OUT"),
    ("Gordon is out for Thursday's Game 6 against the Timberwolves, Anthony Slater "
     "of ESPN.com reports.", "OUT"),
    ("Richard is out for Monday's California Classic Summer League game against the "
     "Heat for undisclosed reasons, Dalton Johnson of NBC Sports Bay Area reports.", "OUT"),
    ("Brooklyn general manager Sean Marks announced Monday that Traore underwent "
     "right knee surgery and won't play in Summer League, C.J. Holmes of the New "
     "York Daily News reports.", "OUT"),  # name-lead absent -- status must still hit

    # -- WNBA injury_facts_wnba.jsonl detail field (real; only corpus w/ this vocab) --
    ("Evans (leg) is listed as doubtful for Thursday's game in Portland.", "DOUBTFUL"),
    ("Jones is listed as doubtful for Saturday's game versus the Fire.", "DOUBTFUL"),
    ("Juhasz (knee) has been downgraded to doubtful for of Monday's game versus the "
     "Sun.", "DOUBTFUL"),
    ("Nye (knee) is questionable for Thursday's game against the Storm.", "QUESTIONABLE"),
    ("Wilson (leg) is listed as questionable for Thursday's game against the Fire.",
     "QUESTIONABLE"),
    ("Samuelson (finger) is listed as questionable for Thursday's game against Las "
     "Vegas.", "QUESTIONABLE"),
    ("Williams (back) is questionable for Friday's game against the Sun.", "QUESTIONABLE"),
    ("Cunningham (back) is questionable for Thursday's game against the Mercury.",
     "QUESTIONABLE"),
    ("Sabally (knee) is questionable for Friday's game against Dallas.", "QUESTIONABLE"),
    ("Reese (leg) is questionable for Saturday's game against the Fire.", "QUESTIONABLE"),
    ("Whitcomb (knee) is listed as probable for Thursday's game against the Fever.",
     "PROBABLE"),
    ("Thomas (foot) is listed as probable for Thursday's game against Indiana.", "PROBABLE"),
    ("Boston (lower leg) is probable for Thursday's game against the Mercury.", "PROBABLE"),
    ("Clark (back) is listed as probable for Sunday's game against the Aces.", "PROBABLE"),
    ("Citron (knee) is listed as probable for Sunday's game against the Storm.", "PROBABLE"),
    ("Whitcomb (knee) is probable for Monday's matchup with Minnesota.", "PROBABLE"),
    ("day-to-day", "DAY_TO_DAY"),  # verbatim real `detail` value in the WNBA store

    # -- live capture, THIS SESSION, data/omni/live_edge/news/raw/2026-07-14.jsonl --
    ("Newell (rest) is out for Monday's Summer League game against Boston, Brad "
     "Rowland of the Locked On Podcast Network reports.", "OUT"),
    ("Dennis (Achilles) is out for Monday's Summer League game against Boston, "
     "perBrad Rowland of the Locked On Podcast Network.", "OUT"),
    ("Williams (undisclosed) is out for Monday's Summer League game against "
     "Atlanta, according to Jack Simone of BostonSportsJournal.com.", "OUT"),
    ("Gonzalez (rest) is sitting out Monday's Summer League game against the "
     "Hawks, per Jack Simone of BostonSportsJournal.com.", "OUT"),
    ("Landale (ankle) will return to the Hawks on a one-year, $14 million deal, "
     "Shams Charania of ESPN reports.", None),  # no status word -- negative control
    ("Gilbert (adductor) is out for Monday's Summer League game against Boston, "
     "per Brad Rowland of the Locked On Podcast Network.", "OUT"),

    # -- real ESPN news headlines, non-injury (negative controls) --
    ("RC makes case for Jalen Brunson to win ESPY for Best NBA Player", None),
    ("Meet the summer league rookies who were once unranked in high school", None),
    ("'The Hoop Collective': Episodes of Brian Windhorst's NBA podcast", None),
    ("Tyler Herro wants to 'move on' from Bam Adebayo altercation", None),
    ("Inside the hopeful resurrection of the Chicago Bulls, what's next", None),
]


def test_golden_set_size():
    assert len(GOLDEN) >= 30, f"golden set has {len(GOLDEN)} items, need >=30"


def test_status_accuracy_at_least_90pct():
    n_correct = 0
    misses = []
    for text, true_status in GOLDEN:
        row = parse_item(text, report_ts="2026-07-14T00:00:00+00:00", source="test")
        if row["status"] == true_status:
            n_correct += 1
        else:
            misses.append((text[:60], true_status, row["status"]))
    accuracy = n_correct / len(GOLDEN)
    print(f"news_parse golden-set accuracy: {n_correct}/{len(GOLDEN)} = {accuracy:.3f}")
    for m in misses:
        print(f"  MISS text={m[0]!r} true={m[1]} got={m[2]}")
    assert accuracy >= 0.90, f"status accuracy {accuracy:.3f} < 0.90 (misses: {misses})"


def test_confidence_reflects_match_quality():
    named = parse_item("Tatum (knee) has been ruled out for Saturday's game.",
                        report_ts="2026-07-14T00:00:00+00:00")
    assert named["status"] == "OUT" and named["confidence"] == 0.9

    no_status = parse_item("Random unrelated headline about ticket sales.",
                           report_ts="2026-07-14T00:00:00+00:00")
    assert no_status["status"] is None and no_status["confidence"] == 0.0


if __name__ == "__main__":
    test_golden_set_size()
    test_status_accuracy_at_least_90pct()
    test_confidence_reflects_match_quality()
    print("all news_parse checks passed")

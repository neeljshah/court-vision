"""Focused G393 checks for extracted caller and parser behavior."""
from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.platformkit.tracking import g393_finish
from scripts.platformkit.tracking.g393_parser_harness import DAEMON, PAIR, RUN_CLIP, replay
from scripts.platformkit.tracking.g393_prepare import validate


ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/tracking/g393_leading_hyphen_game_id_2026-09-11/preregistration.md"


def _sealed_digest(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    above, seal = text.rsplit("SEAL sha256 ", 1)
    return hashlib.sha256(above.encode("utf-8")).hexdigest(), seal.strip()


def test_g393_extracted_parser_preserves_game_ids_and_seal():
    daemon = (ROOT / DAEMON).read_text(encoding="utf-8")
    clip = (ROOT / RUN_CLIP).read_text(encoding="utf-8")
    review = replay(daemon, clip)
    assert validate(review) == {"leading_before_failures": 30, "leading_candidate_recovered": 30,
                                "ordinary_unchanged": 30, "supplemental_preserved": 5,
                                "candidate_value_mismatches": 1}
    assert review["argument_count"] == 12
    assert all("input path" in record["after"]["namespace"]["video"] for record in review["records"])
    for record in review["records"]:
        before = record["before"]["argv"]
        expected = before[:4] + ["--game-id=" + record["game_id"]] + before[6:]
        assert record["after"]["argv"] == expected
        assert record["after"]["namespace"]["frames"] == 3000
        assert record["after"]["namespace"]["no_show"] is True
    digest, seal = _sealed_digest(PREREG)
    assert digest == seal


def test_g393_no_candidate_form_clears_the_sealed_control_bar():
    """The finisher's three-form scoring, and the one control no caller form survives."""
    daemon = (ROOT / DAEMON).read_text(encoding="utf-8")
    clip = (ROOT / RUN_CLIP).read_text(encoding="utf-8")
    review = g393_finish.score(daemon, clip)
    counts = g393_finish.tally(review)
    assert counts["split_baseline"]["leading_recovered"] == 0
    assert counts["dashdash_separator"] == {"leading_recovered": 0, "ordinary_recovered": 0,
                                           "supplemental_preserved": 0, "control_extra_preserved": 0,
                                           "unrelated_drift": 0, "sealed_eligible": 0}
    equals = counts["equals_single_token"]
    assert (equals["leading_recovered"], equals["ordinary_recovered"]) == (30, 30)
    assert (equals["supplemental_preserved"], equals["control_extra_preserved"]) == (5, 2)
    assert equals["unrelated_drift"] == 0
    # The sealed bar demands 6/6 controls, so NO form is eligible.
    assert [name for name in g393_finish.FORMS if counts[name]["sealed_eligible"]] == []
    # The single failing control fails SILENTLY -- exit 0 with the wrong value.
    control = next(r for r in review["records"] if r["game_id"] == "--")
    cell = control["forms"]["equals_single_token"]
    assert cell["return_status"] == 0 and cell["namespace"]["game_id"] == []


def test_g393_scratch_copy_fixes_what_the_repo_copy_does_not():
    """The proposal works only as a scratch copy; the repo caller still fails."""
    daemon = (ROOT / DAEMON).read_text(encoding="utf-8")
    clip = (ROOT / RUN_CLIP).read_text(encoding="utf-8")
    proof = g393_finish.scratch_proof(daemon, clip)
    assert proof["split_baseline"]["leading_recovered"] is False
    assert proof["equals_single_token"]["leading_recovered"] is True
    assert proof["dashdash_separator"]["leading_recovered"] is False
    # Nothing was written into the repo: the landed caller still carries the split pair.
    assert PAIR in daemon and '"--game-id=" + game_id' not in daemon
    assert all(path.startswith("C:/Users/neelj/AppData/Local/Temp/g393_scratch/")
               for path in (proof[name]["path"] for name in proof))


def test_g393_caller_census_and_q6_scan():
    """Every affected caller line is named, and no artifact carries claim vocabulary."""
    census = g393_finish.caller_lines(ROOT)
    affected = sorted("%s:%s" % (row["path"], row["line"]) for row in census if row["affected"] == "True")
    assert "scripts/platformkit/track_daemon.py:96" in affected
    assert "scripts/platformkit/footage_cycle.py:154" in affected
    assert "scripts/platformkit/footage_bridge.py:500" in affected
    assert len(affected) == 14
    evidence = ROOT / g393_finish.EVIDENCE
    artifacts = [path for path in evidence.rglob("*") if path.is_file()]
    artifacts.append(ROOT / (g393_finish.EVIDENCE.as_posix() + ".md"))
    assert g393_finish.q6_scan(artifacts) == []

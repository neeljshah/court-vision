"""Focused archive checks for S261 attempt 2's full CPCV evidence."""
import hashlib
import json
from pathlib import Path

from scripts.platformkit import s261_ingame_headline_rederive_v2 as base


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "docs" / "evidence" / "harness"
PREREG = "docs/evidence/harness/S261_ingame_headline_rederive_v2_attempt2_prereg_2026-09-04.md"


def test_s261_attempt2_full_archive_aliases_exclusions_diffs_and_seal():
    shares = base._shares({"static": .6, "score": .5, "conditional": .4})
    assert shares["total_calibration_change"] == shares["static_minus_conditional"]
    artifact = json.loads((HARNESS / "S261_ingame_headline_rederive_v2_attempt2_2026-09-04.json").read_text())
    assert artifact["run_scope"] == "full_local"
    assert artifact["sample_game_path_limit"] == 0
    expected = {"nba": (1313, {"invalid_inning": 0, "tied_final_score": 0},
                        {"static": "0.00983250084408843", "conditional": "0.00424678066236500"}),
                "mlb": (23279, {"invalid_inning": 2458, "tied_final_score": 2246},
                        {"static": "0.00797282410431543", "conditional": "0.00199755953257377"})}
    for sport, (n_eff, exclusions, diffs) in expected.items():
        values = artifact["sports"][sport]
        assert values["game_path_count"] == n_eff
        assert values["prior_share_ci"]["n_eff"] == n_eff
        assert values["exclusions"] == exclusions
        assert values["public_value_abs_diff_exact"] == diffs
        assert values["shares"]["total_calibration_change"] == values["shares"]["static_minus_conditional"]
        assert values["prior_share_ci"]["finite_resamples"] == 10000
        assert set(values["reproduction_abs_diff"]) == {"static", "score", "conditional"}
    memo = (HARNESS / "S261_ingame_headline_rederive_v2_attempt2_2026-09-04.md").read_text()
    for text in ("2458 `invalid_inning`", "2246 `tied_final_score`", "NOT VERIFIED",
                 "0.00983250084408843", "0.00424678066236500", "0.00797282410431543",
                 "0.00199755953257377"):
        assert text in memo
    prereg = (ROOT / PREREG).read_bytes().replace(b"\r\n", b"\n")
    assert b"\r\n" not in prereg
    seal = artifact["prereg_seal_sha256"]
    assert hashlib.sha256(prereg[:prereg.index(b"Seal SHA-256")]).hexdigest().upper() == seal

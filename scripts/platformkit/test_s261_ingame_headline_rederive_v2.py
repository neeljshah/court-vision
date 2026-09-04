"""Focused contract checks for the S261 additive rederive schema."""
import hashlib
import json
import subprocess
from pathlib import Path

from scripts.platformkit import s261_ingame_headline_rederive_v2 as subject


def _state(index: int) -> dict:
    return {"game_id": f"g{index}", "state_ts": f"2025-01-{index + 1:02d}T01:00:00",
            "home": "H", "away": "A", "outcome": 0,
            "features": {"checkpoint": 1, "home_score": 1, "away_score": 0},
            "feature_avail": {"checkpoint": "2025-01-01T00:00:00", "home_score": "2025-01-01T00:00:00",
                              "away_score": "2025-01-01T00:00:00"}}


def test_s261_aliases_exclusions_public_diffs_and_committed_lf_seal(monkeypatch, tmp_path):
    states = [_state(index) for index in range(30)]
    meta = {row["game_id"]: (row["game_id"], row["state_ts"][:10]) for row in states}

    def collect():
        return states, meta, [], {"invalid_inning": 0, "tied_final_score": 0}

    def scored(rows, sport):
        return [{"state_id": row["game_id"], "static": .6, "score": .5, "conditional": .4,
                 "outcome": float(row["outcome"]), "split_id": 0} for row in rows]

    monkeypatch.setattr(subject, "_nba_states", collect)
    monkeypatch.setattr(subject, "_mlb_states", collect)
    monkeypatch.setattr(subject, "_oos_triplets", scored)
    summary = subject.archive(tmp_path, validate_public=False)
    sport = summary["sports"]["nba"]
    assert sport["checkpoint_count"] == 30
    assert sport["cpcv_path_evaluation_count"] == 30
    assert sport["prior_share_ci"]["finite_resamples"] == sport["prior_share_ci"]["resamples"]
    assert set(sport["reproduction_abs_diff"]) == {"static", "score", "conditional"}
    assert subject._EXCLUSIONS == {"invalid_inning": 2458, "tied_final_score": 2246}
    _, exact = subject._public_diffs("nba", {"static": 0.21883250084408842, "conditional": 0.163246780662365})
    assert exact == {"static": "0.00983250084408843", "conditional": "0.00424678066236500"}
    prereg = "docs/evidence/harness/S261_ingame_headline_rederive_v2_prereg_2026-09-04.md"
    try:
        committed = subprocess.check_output(["git", "show", f"HEAD:{prereg}"])
        expected = committed.split(b"`")[-2].decode("ascii")
        assert b"\r\n" not in committed
        assert hashlib.sha256(committed[:committed.index(b"Seal SHA-256")]).hexdigest().upper() == expected
        print("seal reader: committed Git object")
    except subprocess.CalledProcessError as error:
        try:
            subprocess.check_output(["git", "cat-file", "-e", f"HEAD:{prereg}"])
        except subprocess.CalledProcessError:
            committed = (Path(__file__).resolve().parents[2] / prereg).read_bytes().replace(b"\r\n", b"\n")
            expected = committed.split(b"`")[-2].decode("ascii")
            assert b"\r\n" not in committed
            assert hashlib.sha256(committed[:committed.index(b"Seal SHA-256")]).hexdigest().upper() == expected
            print("seal reader: landing-time file fallback")
        else:
            raise error
    root = Path(__file__).resolve().parents[2]
    artifact = json.loads((root / "docs/evidence/harness/S261_ingame_headline_rederive_v2_sample_2026-09-04.json").read_text())
    memo = (root / "docs/evidence/harness/S261_ingame_headline_rederive_v2_2026-09-04.md").read_text()
    assert artifact["sports"]["mlb"]["exclusions"] == {"invalid_inning": 2458, "tied_final_score": 2246}
    assert artifact["sports"]["nba"]["prior_share_ci"]["finite_resamples"] == 10000
    assert set(artifact["sports"]["mlb"]["reproduction_abs_diff"]) == {"static", "score", "conditional"}
    for value in ("0.00983250084408843", "0.00424678066236500", "0.00797282410431543",
                  "0.00199755953257377", "2458 `invalid_inning`", "2246 `tied_final_score`"):
        assert value in memo


def test_s261_seal_landing_time_file_fallback(monkeypatch, tmp_path, capsys):
    def absent_from_head(*args, **kwargs):
        raise subprocess.CalledProcessError(
            128, args[0], stderr=b"fatal: path exists on disk, but not in 'HEAD'\n")

    monkeypatch.setattr(subprocess, "check_output", absent_from_head)
    test_s261_aliases_exclusions_public_diffs_and_committed_lf_seal(monkeypatch, tmp_path)
    output = capsys.readouterr().out
    assert "seal reader: landing-time file fallback" in output
    print(output, end="")

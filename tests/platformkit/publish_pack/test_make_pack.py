"""Per-file tests for make_pack: allowlist-only zip + loud refusal on a
forbidden/secret file."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scripts.platformkit.publish_pack import make_pack, pack_manifest as M


def _fixture_tree(root: Path) -> None:
    ic = root / "data" / "cache" / "intel_claims"
    ic.mkdir(parents=True)
    (ic / "foo_claims.jsonl").write_text('{"claim_id": "foo"}\n')
    (ic / "foo_claims.index.jsonl").write_text('{"claim_id": "foo"}\n')
    (ic / "foo_claims_validation.json").write_text('{"edge_claimed": false}\n')
    # a ledger family -> must be silently excluded.
    (ic / "some_ledger.jsonl").write_text('{"x": 1}\n')
    (ic / "some_ledger_validation.json").write_text("{}\n")
    prof = root / "data" / "cache" / "profiles"
    prof.mkdir(parents=True)
    (prof / "nba_player_profiles.parquet").write_bytes(b"PAR1fake")
    dom = root / "data" / "domains" / "tennis"
    dom.mkdir(parents=True)
    (dom / "matches.parquet").write_bytes(b"PAR1fake")
    (dom / "odds.parquet").write_bytes(b"PAR1odds")  # NOT in allowlist


def test_allowlist_only_zip(tmp_path: Path) -> None:
    _fixture_tree(tmp_path)
    out = tmp_path / "out"
    info = make_pack.build(tmp_path, out)

    names = set(zipfile.ZipFile(info["_zip_path"]).namelist())
    assert "pack_info.json" in names
    assert "data/cache/intel_claims/foo_claims.jsonl" in names
    assert "data/cache/profiles/nba_player_profiles.parquet" in names
    assert "data/domains/tennis/matches.parquet" in names
    # scraped odds + ledger family never ship.
    assert "data/domains/tennis/odds.parquet" not in names
    assert not any("ledger" in n for n in names)

    disk_info = json.loads((out / "pack_info.json").read_text())
    assert disk_info["edge_claimed"] is False
    assert disk_info["family_count"] == 1  # only foo_claims


def test_secret_file_refused_loudly(tmp_path: Path) -> None:
    _fixture_tree(tmp_path)
    # a file the allowlist WOULD select but which carries a secret.
    (tmp_path / "data" / "cache" / "intel_claims" / "evil_claims.jsonl").write_text(
        '{"api_key": "sk-deadbeef"}\n')
    with pytest.raises(RuntimeError, match="secret-like token"):
        make_pack.build(tmp_path, tmp_path / "out")


def test_forbidden_reason_paths() -> None:
    assert M.forbidden_reason("data/domains/mlb/odds.parquet")
    assert M.forbidden_reason("data/frontend/paper.json")
    assert M.forbidden_reason("data/cache/line_history/x.jsonl")
    # a legit descriptive family that merely mentions line_history is NOT forbidden.
    assert M.forbidden_reason(
        "data/cache/intel_claims/line_history_consensus_claims.jsonl") is None

"""Per-file tests for install_pack: unpack, refuse-overwrite, config snippet.
The network download is bypassed -- install() takes zip bytes directly."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from scripts.platformkit.publish_pack import install_pack


def _make_zip(edge_claimed: bool = False) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data/cache/intel_claims/foo_claims.jsonl", '{"claim_id": "foo"}\n')
        zf.writestr("data/cache/profiles/nba_player_profiles.parquet", "PAR1fake")
        zf.writestr("pack_info.json", json.dumps({
            "version_date": "20260717", "file_count": 2, "family_count": 1,
            "edge_claimed": edge_claimed, "honest_note": "snapshot"}))
    return buf.getvalue()


def test_unpack_fresh_clone(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(install_pack, "MARKER",
                        tmp_path / "data" / "cache" / "publish_pack" / "pack_info.json")
    info = install_pack.install(tmp_path, _make_zip(), is_update=False)
    assert info["version_date"] == "20260717"
    assert (tmp_path / "data" / "cache" / "intel_claims" / "foo_claims.jsonl").is_file()
    assert install_pack.MARKER.is_file()


def test_refuse_overwrite_existing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(install_pack, "MARKER",
                        tmp_path / "data" / "cache" / "publish_pack" / "pack_info.json")
    dest = tmp_path / "data" / "cache" / "intel_claims" / "foo_claims.jsonl"
    dest.parent.mkdir(parents=True)
    dest.write_text("my own precious local data that is a different size\n")
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        install_pack.install(tmp_path, _make_zip(), is_update=False)
    # --update overwrites.
    install_pack.install(tmp_path, _make_zip(), is_update=True)
    assert dest.read_text().startswith('{"claim_id"')


def test_refuse_edge_claimed_pack(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(install_pack, "MARKER",
                        tmp_path / "data" / "cache" / "publish_pack" / "pack_info.json")
    with pytest.raises(RuntimeError, match="edge_claimed"):
        install_pack.install(tmp_path, _make_zip(edge_claimed=True), is_update=False)


def test_config_snippet_correct(tmp_path: Path, capsys) -> None:
    install_pack.print_next_steps(tmp_path, {
        "version_date": "20260717", "file_count": 2, "family_count": 1,
        "honest_note": "snapshot"})
    out = capsys.readouterr().out
    assert "scripts.platformkit.mcp_server.server" in out
    assert tmp_path.as_posix() in out          # Desktop cwd
    assert "system_health" in out              # smoke test present
    assert "no_data BY DESIGN" in out

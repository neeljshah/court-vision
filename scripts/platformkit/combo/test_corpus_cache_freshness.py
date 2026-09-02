"""Gap S41/S44 -- corpus_cache.freshness_report: stale detection + order basis.

Per-file test only: `python -m pytest scripts/platformkit/combo/test_corpus_cache_freshness.py -q`
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pandas as pd
import pytest

from scripts.platformkit.combo import corpus_cache as cc


def _seed(tmp_path, monkeypatch, *, with_date: bool):
    """Write one fake cached corpus + sidecar into a tmp cache dir."""
    monkeypatch.setattr(cc, "_CACHE_DIR", tmp_path)
    src = tmp_path / "fake_source.parquet"
    rows = {"event_id": ["a", "b"], "corpus_unit": ["u", "u"],
            "y": [1.0, 0.0], "p_base": [0.6, 0.4]}
    if with_date:
        rows[cc.DATE_COL] = pd.to_datetime(["2026-01-01", "2026-01-02"])
    df = pd.DataFrame(rows)
    df.to_parquet(src, index=False)
    df.to_parquet(tmp_path / "gate_corpus_mlb.parquet", index=False)
    (tmp_path / "gate_corpus_mlb.sources.json").write_text(json.dumps({
        "sport": "mlb", "built_at": time.time(), "n_rows": len(df),
        "sources": cc._source_manifest([src]),
    }), encoding="utf-8")
    return src


def test_fresh_cache_reports_not_stale(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, with_date=False)
    rep = cc.freshness_report("mlb")
    assert rep["stale"] is False
    assert rep["stale_reason"] is None
    assert rep["n_rows_cached"] == rep["n_rows_at_build"] == 2
    assert rep["cache_exists"] and rep["sidecar_exists"]
    assert rep["sources"][0]["changed"] is False


def test_changed_source_reports_stale(tmp_path, monkeypatch):
    src = _seed(tmp_path, monkeypatch, with_date=False)
    # rewrite the source with different content -> mtime AND sha both move
    pd.DataFrame({"event_id": ["a", "b", "c"]}).to_parquet(src, index=False)
    rep = cc.freshness_report("mlb")
    assert rep["stale"] is True
    assert "fake_source.parquet" in rep["stale_reason"]
    assert rep["sources"][0]["changed"] is True


def test_missing_cache_is_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "_CACHE_DIR", tmp_path)
    rep = cc.freshness_report("mlb")
    assert rep["stale"] is True
    assert rep["n_rows_cached"] is None


def test_order_basis_positional_without_a_date_column(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, with_date=False)
    assert cc.freshness_report("mlb")["order_basis"] == cc.POSITIONAL_ORDER


def test_order_basis_names_the_date_column_when_present(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, with_date=True)
    assert cc.freshness_report("mlb")["order_basis"] == cc.DATE_COL


def test_unknown_sport_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "_CACHE_DIR", tmp_path)
    with pytest.raises(ValueError):
        cc.freshness_report("cricket")


@pytest.mark.parametrize("sport", cc.SPORTS)
def test_real_corpus_carries_a_usable_date(sport):
    """S44: every gate corpus surfaces event_date, chronological within corpus_unit.

    Skipped where data/ is absent (a git worktree has no data tree).
    """
    if not cc._corpus_path(sport).exists():
        pytest.skip("no cached corpus for %s" % sport)
    df = pd.read_parquet(cc._corpus_path(sport))
    assert cc.DATE_COL in df.columns
    dates = pd.to_datetime(df[cc.DATE_COL], errors="coerce")
    assert dates.notna().all()
    # Chronological WITHIN a corpus_unit; tennis is NOT monotonic across units
    # (ATP is concatenated before WTA), which is exactly why a positional
    # walk-forward over the whole frame is not a chronological one.
    for _, group in df.assign(_d=dates).groupby("corpus_unit"):
        assert group["_d"].is_monotonic_increasing
    assert cc.freshness_report(sport)["order_basis"] == cc.DATE_COL


# --------------------------------------------------------------------------- #
# Gap S68 -- portable sidecars: relative source keys + opt-in portable load
# --------------------------------------------------------------------------- #

def _seed_host_a(tmp_path, monkeypatch):
    """Build a real corpus + sidecar on 'host A' via build_gate_corpus itself."""
    repo_a = tmp_path / "hostA"
    (repo_a / "data" / "domains").mkdir(parents=True)
    src = repo_a / "data" / "domains" / "fake_source.parquet"
    df = pd.DataFrame({"event_id": ["a", "b"], "corpus_unit": ["u", "u"],
                       "y": [1.0, 0.0], "p_base": [0.6, 0.4]})
    df.to_parquet(src, index=False)
    cache_a = repo_a / "data" / "cache" / "combo"
    monkeypatch.setattr(cc, "_REPO", repo_a)
    monkeypatch.setattr(cc, "_CACHE_DIR", cache_a)
    monkeypatch.setitem(cc._BUILDERS, "mlb", lambda: (df, [src]))
    cc.build_gate_corpus("mlb")
    return repo_a, cache_a, src


def _move_to_host_b(tmp_path, monkeypatch, cache_a):
    """Copy ONLY the cache (parquet + sidecar) to a host with no sources."""
    repo_b = tmp_path / "hostB"
    cache_b = repo_b / "data" / "cache" / "combo"
    shutil.copytree(cache_a, cache_b)
    monkeypatch.setattr(cc, "_REPO", repo_b)
    monkeypatch.setattr(cc, "_CACHE_DIR", cache_b)
    return repo_b, cache_b


def test_build_records_relative_sources_and_a_corpus_hash(tmp_path, monkeypatch):
    _, cache_a, _ = _seed_host_a(tmp_path, monkeypatch)
    man = json.loads((cache_a / "gate_corpus_mlb.sources.json").read_text(encoding="utf-8"))
    assert list(man["sources"]) == ["data/domains/fake_source.parquet"]
    assert man["corpus_sha256"] == cc._file_sha256(cache_a / "gate_corpus_mlb.parquet")
    assert cc.freshness_report("mlb")["load_provenance"] == "host-local"


def test_relative_sidecar_loads_on_the_build_host(tmp_path, monkeypatch):
    _seed_host_a(tmp_path, monkeypatch)
    assert len(cc.load_gate_corpus("mlb")) == 2
    assert cc.freshness_report("mlb")["stale"] is False


def test_host_b_refuses_by_default_and_names_the_absent_source(tmp_path, monkeypatch):
    _, cache_a, _ = _seed_host_a(tmp_path, monkeypatch)
    _move_to_host_b(tmp_path, monkeypatch, cache_a)
    with pytest.raises(cc.StaleCorpusError) as exc:
        cc.load_gate_corpus("mlb")
    assert "data/domains/fake_source.parquet" in str(exc.value)
    assert "no longer exists" in str(exc.value)


def test_host_b_loads_in_portable_mode(tmp_path, monkeypatch):
    _, cache_a, _ = _seed_host_a(tmp_path, monkeypatch)
    _move_to_host_b(tmp_path, monkeypatch, cache_a)
    assert len(cc.load_gate_corpus("mlb", portable=True)) == 2
    rep = cc.freshness_report("mlb")
    assert rep["load_provenance"] == "portable-sidecar"
    assert rep["sources"][0]["exists"] is False


def test_portable_mode_refuses_a_tampered_parquet(tmp_path, monkeypatch):
    _, cache_a, _ = _seed_host_a(tmp_path, monkeypatch)
    _, cache_b = _move_to_host_b(tmp_path, monkeypatch, cache_a)
    pd.DataFrame({"event_id": ["z"]}).to_parquet(cache_b / "gate_corpus_mlb.parquet", index=False)
    with pytest.raises(cc.StaleCorpusError) as exc:
        cc.load_gate_corpus("mlb", portable=True)
    assert "sha256" in str(exc.value)
    assert cc.freshness_report("mlb")["load_provenance"] == "unloadable"


def test_portable_mode_refuses_a_pre_s68_sidecar(tmp_path, monkeypatch):
    """No corpus_sha256 to vouch for the bytes -> refuse, never a silent load."""
    _, cache_a, _ = _seed_host_a(tmp_path, monkeypatch)
    _, cache_b = _move_to_host_b(tmp_path, monkeypatch, cache_a)
    side = cache_b / "gate_corpus_mlb.sources.json"
    man = json.loads(side.read_text(encoding="utf-8"))
    man.pop("corpus_sha256")
    side.write_text(json.dumps(man), encoding="utf-8")
    with pytest.raises(cc.StaleCorpusError) as exc:
        cc.load_gate_corpus("mlb", portable=True)
    assert "corpus_sha256" in str(exc.value)


def test_legacy_absolute_sidecar_still_loads(tmp_path, monkeypatch):
    """Backward compatibility: a pre-S68 sidecar keyed by ABSOLUTE host path."""
    src = _seed(tmp_path, monkeypatch, with_date=False)
    side = tmp_path / "gate_corpus_mlb.sources.json"
    man = json.loads(side.read_text(encoding="utf-8"))
    man["sources"] = {str(src): list(man["sources"].values())[0]}
    side.write_text(json.dumps(man), encoding="utf-8")
    assert Path(list(man["sources"])[0]).is_absolute()
    assert len(cc.load_gate_corpus("mlb")) == 2
    assert cc.freshness_report("mlb")["load_provenance"] == "host-local"


@pytest.mark.parametrize("sport", cc.SPORTS)
def test_real_sidecars_are_portable(sport):
    """Every shipped sidecar keys its sources RELATIVE and records its own hash.

    Skipped where data/ is absent (a git worktree has no data tree).
    """
    if not cc._sidecar_path(sport).exists():
        pytest.skip("no cached corpus for %s" % sport)
    man = json.loads(cc._sidecar_path(sport).read_text(encoding="utf-8"))
    assert man.get("corpus_sha256") == cc._file_sha256(cc._corpus_path(sport))
    for key in man["sources"]:
        assert not Path(key).is_absolute(), key
        assert cc._resolve_source(key).exists(), key
    assert cc.freshness_report(sport)["load_provenance"] == "host-local"


def test_portable_covers_a_different_file_at_the_recorded_path(tmp_path, monkeypatch):
    """The pod case: host B HAS data/domains/... but it is not the recorded file."""
    _, cache_a, _ = _seed_host_a(tmp_path, monkeypatch)
    repo_b, _ = _move_to_host_b(tmp_path, monkeypatch, cache_a)
    impostor = repo_b / "data" / "domains" / "fake_source.parquet"
    impostor.parent.mkdir(parents=True)
    pd.DataFrame({"event_id": ["different"]}).to_parquet(impostor, index=False)
    with pytest.raises(cc.StaleCorpusError) as exc:
        cc.load_gate_corpus("mlb")
    assert "changed since build" in str(exc.value)
    assert len(cc.load_gate_corpus("mlb", portable=True)) == 2
    rep = cc.freshness_report("mlb")
    assert rep["load_provenance"] == "portable-sidecar"
    assert rep["stale"] is True          # honest: the recorded source is not here

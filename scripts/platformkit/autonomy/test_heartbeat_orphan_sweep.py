"""Per-file tests for scripts.platformkit.autonomy.heartbeat_orphan_sweep.

Acceptance criteria (conservative / fail-closed):
  (A) A STALE + UNOWNED .txt stem is pruned.
  (B) A FRESH unowned stem is KEPT (never deleted just for being unowned).
  (C) An OWNED stem (manifest or known self-beat) is KEPT even if stale.
  (D) dry_run=True deletes nothing but reports would_prune.
  (E) Idempotent: a second sweep with nothing stale-unowned is a no-op.
  (F) Manifest UNKNOWN -> prune NOTHING (fail-closed).
  (G) Only *.txt directly in the dir; a non-.txt and a nested file are untouched.
  (H) Never raises on a missing directory / bad input.
  (I) No $ field; honest_note present.

Run (per-file only -- never full pytest):
    cd /c/Users/neelj/nba-ai-system && \
      python -m pytest scripts/platformkit/autonomy/test_heartbeat_orphan_sweep.py -q
"""
from __future__ import annotations

import json
import os
import pathlib

import pytest

from scripts.platformkit.autonomy import heartbeat_orphan_sweep as hs


_NOW = 1_750_000_000.0
_STALE = hs.DEFAULT_STALE_SEC


def _write(hb_dir: pathlib.Path, name: str, age_sec: float, now: float) -> pathlib.Path:
    """Write a heartbeat file and backdate its mtime by *age_sec*."""
    hb_dir.mkdir(parents=True, exist_ok=True)
    p = hb_dir / name
    p.write_text("ok", encoding="ascii")
    mt = now - age_sec
    os.utime(str(p), (mt, mt))
    return p


# --------------------------------------------------------------------------- #
# (A/B) stale-unowned pruned; fresh-unowned kept
# --------------------------------------------------------------------------- #

def test_stale_unowned_is_pruned(tmp_path):
    hb = tmp_path / "hb"
    stale = _write(hb, "dead_scraper.txt", _STALE + 3600.0, _NOW)
    doc = hs.sweep(hb_dir=hb, now=_NOW)
    # If the manifest is unavailable in this env the sweep fail-closes; only assert
    # the prune when we could actually resolve the owned set.
    if doc["manifest_ok"]:
        assert "dead_scraper" in doc["pruned"]
        assert not stale.exists()
    else:
        assert doc["pruned"] == []
        assert stale.exists()


def test_fresh_unowned_is_kept(tmp_path):
    hb = tmp_path / "hb"
    fresh = _write(hb, "new_daemon.txt", 30.0, _NOW)  # 30s old -> fresh
    doc = hs.sweep(hb_dir=hb, now=_NOW)
    assert fresh.exists(), "a FRESH unowned stem must never be deleted"
    assert "new_daemon" not in doc["pruned"]
    if doc["manifest_ok"]:
        assert any(k.get("stem") == "new_daemon" for k in doc["kept_fresh"])


# --------------------------------------------------------------------------- #
# (C) owned stem kept even if stale
# --------------------------------------------------------------------------- #

def test_owned_stem_kept_even_if_stale(tmp_path):
    hb = tmp_path / "hb"
    # m9_supervisor is a KNOWN self-beating owned stem; make it very stale.
    owned = _write(hb, "m9_supervisor.txt", _STALE * 10, _NOW)
    doc = hs.sweep(hb_dir=hb, now=_NOW)
    assert owned.exists(), "a known-owned stem must never be pruned"
    assert "m9_supervisor" not in doc["pruned"]


# --------------------------------------------------------------------------- #
# (D) dry_run deletes nothing
# --------------------------------------------------------------------------- #

def test_dry_run_deletes_nothing(tmp_path):
    hb = tmp_path / "hb"
    stale = _write(hb, "dead_scraper.txt", _STALE + 3600.0, _NOW)
    doc = hs.sweep(hb_dir=hb, now=_NOW, dry_run=True)
    assert stale.exists(), "dry_run must not delete"
    assert doc["pruned"] == []
    if doc["manifest_ok"]:
        assert "dead_scraper" in doc["would_prune"]


# --------------------------------------------------------------------------- #
# (E) idempotent
# --------------------------------------------------------------------------- #

def test_idempotent_second_sweep_is_noop(tmp_path):
    hb = tmp_path / "hb"
    _write(hb, "dead_scraper.txt", _STALE + 3600.0, _NOW)
    hs.sweep(hb_dir=hb, now=_NOW)
    doc2 = hs.sweep(hb_dir=hb, now=_NOW)
    assert doc2["pruned"] == [], "second sweep must prune nothing"


# --------------------------------------------------------------------------- #
# (F) manifest unknown -> fail-closed
# --------------------------------------------------------------------------- #

def test_manifest_unknown_prunes_nothing(tmp_path, monkeypatch):
    hb = tmp_path / "hb"
    stale = _write(hb, "dead_scraper.txt", _STALE + 3600.0, _NOW)
    monkeypatch.setattr(hs, "_manifest_owned_stems", lambda: None)
    doc = hs.sweep(hb_dir=hb, now=_NOW)
    assert doc["manifest_ok"] is False
    assert doc["pruned"] == []
    assert stale.exists(), "fail-closed: never delete when owned set is UNKNOWN"


# --------------------------------------------------------------------------- #
# (G) only immediate *.txt are candidates
# --------------------------------------------------------------------------- #

def test_only_immediate_txt_swept(tmp_path, monkeypatch):
    hb = tmp_path / "hb"
    # force a known owned set so we exercise the prune path deterministically
    monkeypatch.setattr(hs, "_manifest_owned_stems", lambda: frozenset({"m1_paper"}))
    txt = _write(hb, "dead_scraper.txt", _STALE + 3600.0, _NOW)
    other = _write(hb, "dead_scraper.log", _STALE + 3600.0, _NOW)  # not .txt
    nested = hb / "sub"
    nestedf = _write(nested, "deep.txt", _STALE + 3600.0, _NOW)
    doc = hs.sweep(hb_dir=hb, now=_NOW)
    assert "dead_scraper" in doc["pruned"]
    assert not txt.exists()
    assert other.exists(), "a non-.txt file must be untouched"
    assert nestedf.exists(), "a nested file must be untouched"


# --------------------------------------------------------------------------- #
# (H) never raises on missing dir
# --------------------------------------------------------------------------- #

def test_missing_dir_never_raises(tmp_path):
    doc = hs.sweep(hb_dir=tmp_path / "does_not_exist", now=_NOW)
    assert isinstance(doc, dict)
    assert doc["pruned"] == []


# --------------------------------------------------------------------------- #
# (I) honesty rails
# --------------------------------------------------------------------------- #

def test_no_dollar_field_and_honest_note(tmp_path):
    hb = tmp_path / "hb"
    _write(hb, "x.txt", 10.0, _NOW)
    doc = hs.sweep(hb_dir=hb, now=_NOW)
    # The honest_note legitimately contains the phrase "no $ field" (the
    # disclaimer); assert there is no $-VALUE anywhere else in the document.
    without_note = {k: v for k, v in doc.items() if k != "honest_note"}
    blob = json.dumps(without_note).lower()
    assert "$" not in blob
    assert "honest_note" in doc
    assert doc["honest_note"]

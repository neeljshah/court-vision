"""Per-file test: index.py -- fit lanes + a tiny end-to-end build into a temp dir.

Standalone + pytest-discoverable. Does NOT touch the real index. ASCII.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import numpy as np  # noqa: E402

from scripts.platformkit.knowledge import index as I  # noqa: E402


def test_fit_lanes_shapes():
    texts = ["drop coverage ball screen", "transition tempo after rebound",
             "pick and roll short roll read", "isolation closeout pressure"]
    dvec, darr, svec = I.fit_lanes(texts)
    assert darr.shape[0] == len(texts)
    assert darr.dtype == np.float32
    # L2-normed rows: each row norm ~1 (or 0 for empty)
    norms = np.linalg.norm(darr, axis=1)
    assert np.all((np.abs(norms - 1.0) < 1e-4) | (norms < 1e-9))
    assert len(dvec.vocabulary_) > 0 and len(svec.vocabulary_) > 0


def test_end_to_end_tiny_build(monkeypatch):
    from scripts.platformkit.knowledge import config, ingest
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        # tiny vault
        nba = d / "vault" / "NBA" / "Tactics"
        nba.mkdir(parents=True)
        (nba / "drop_coverage.md").write_text(
            "---\ntags: [nba, concept]\n---\n# Drop Coverage\n## Summary\nWall the rim.\n",
            encoding="utf-8")
        (nba / "transition.md").write_text(
            "---\ntags: [nba, concept]\n---\n# Transition Tempo\n## Summary\n"
            "Push the pace after a rebound to attack before the defense sets.\n",
            encoding="utf-8")
        idx = d / "index"
        monkeypatch.setattr(config, "VAULT_ROOT", d / "vault")
        monkeypatch.setattr(config, "MEMORY_DIR", d / "nope")
        monkeypatch.setattr(config, "INDEX_DIR", idx)
        monkeypatch.setattr(config, "CORPUS_PARQUET", idx / "corpus.parquet")
        monkeypatch.setattr(config, "VECTORS_NPY", idx / "vectors_dense.npy")
        monkeypatch.setattr(config, "TFIDF_DENSE_PKL", idx / "tfidf_dense.pkl")
        monkeypatch.setattr(config, "TFIDF_SPARSE_PKL", idx / "tfidf_sparse.pkl")
        monkeypatch.setattr(config, "MANIFEST_PATH", idx / "manifest.json")
        monkeypatch.setattr(config, "LOCK_FILE", idx / ".lock")
        monkeypatch.setattr(config, "SPORTS", ("NBA",))
        manifest = I.build(refresh=False)
        assert (idx / "corpus.parquet").exists()
        assert (idx / "vectors_dense.npy").exists()
        assert (idx / "tfidf_dense.pkl").exists()
        assert (idx / "tfidf_sparse.pkl").exists()
        assert manifest["note_count"] >= 2


def _run() -> int:
    import types
    fails = 0
    # minimal monkeypatch shim for standalone mode
    class MP:
        def __init__(self):
            self._undo = []

        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)

        def restore(self):
            for obj, name, val in reversed(self._undo):
                setattr(obj, name, val)

    try:
        test_fit_lanes_shapes()
        print("PASS test_fit_lanes_shapes")
    except AssertionError as exc:
        fails += 1
        print("FAIL test_fit_lanes_shapes", exc)
    mp = MP()
    try:
        test_end_to_end_tiny_build(mp)
        print("PASS test_end_to_end_tiny_build")
    except AssertionError as exc:
        fails += 1
        print("FAIL test_end_to_end_tiny_build", exc)
    finally:
        mp.restore()
    return fails


if __name__ == "__main__":
    raise SystemExit(_run())

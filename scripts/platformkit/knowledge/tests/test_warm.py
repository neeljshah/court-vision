"""Per-file test: warm.py -- write/read round-trip + boundary on the warmed bundle.

Patches assemble so it runs without a built index. Standalone + pytest. ASCII.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.knowledge import warm as W  # noqa: E402
from scripts.platformkit.knowledge.assemble import Bundle, NO_EDGE_DISCLAIMER  # noqa: E402


def _patch_assemble(monkeypatch, reject=False):
    if reject:
        md = "# Scouting Context -- NBA\n\nNo relevant intel found.\n\n" + \
            NO_EDGE_DISCLAIMER
        bundle = Bundle(markdown=md, citations=[], reject=True)
    else:
        md = ("# Scouting Context -- NBA\n\n## Relevant concepts\n"
              "- Drop Coverage: wall the rim. [[NBA/Tactics/drop_coverage]]\n\n"
              + NO_EDGE_DISCLAIMER)
        bundle = Bundle(markdown=md, citations=["[[NBA/Tactics/drop_coverage]]"],
                        reject=False)
    monkeypatch.setattr(W, "assemble", lambda *a, **k: bundle)


def test_warm_write_read_roundtrip(tmp_path, monkeypatch):
    _patch_assemble(monkeypatch)
    payload = W.warm_game("game1", "NBA", question="tempo", cache_dir=tmp_path)
    assert payload["game_id"] == "game1" and not payload["reject"]
    got = W.read_warm("game1", cache_dir=tmp_path)
    assert got is not None and got["bundle"] == payload["bundle"]
    assert NO_EDGE_DISCLAIMER in got["bundle"]


def test_warm_read_miss_returns_none(tmp_path):
    assert W.read_warm("nope", cache_dir=tmp_path) is None


def test_warm_reject_path(tmp_path, monkeypatch):
    _patch_assemble(monkeypatch, reject=True)
    payload = W.warm_game("g2", "NBA", cache_dir=tmp_path)
    assert payload["reject"]
    assert "No relevant intel found." in payload["bundle"]


def _run() -> int:
    class MP:
        def __init__(self):
            self._u = []

        def setattr(self, obj, name, val):
            self._u.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)

        def restore(self):
            for o, n, v in reversed(self._u):
                setattr(o, n, v)

    fails = 0
    for fn, needs_mp in ((test_warm_write_read_roundtrip, True),
                         (test_warm_read_miss_returns_none, False),
                         (test_warm_reject_path, True)):
        mp = MP()
        with tempfile.TemporaryDirectory() as d:
            try:
                if needs_mp:
                    fn(Path(d), mp)
                else:
                    fn(Path(d))
                print("PASS", fn.__name__)
            except AssertionError as exc:
                fails += 1
                print("FAIL", fn.__name__, exc)
            finally:
                mp.restore()
    return fails


if __name__ == "__main__":
    raise SystemExit(_run())

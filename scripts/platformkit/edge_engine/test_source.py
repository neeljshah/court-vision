"""Per-file test for edge_engine.source. Run ONLY this file (full suite freezes).

  cd /c/Users/neelj/nba-ai-system && \
  C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
  scripts/platformkit/edge_engine/test_source.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest  # noqa: E402

from scripts.platformkit.edge_engine.schema import NewsItem  # noqa: E402
from scripts.platformkit.edge_engine.source import (  # noqa: E402
    FileSource, LiveSource, MockSource, SourceAdapter, utc_now_iso,
)

_RECS = [
    {"source_id": "x:1", "text": "Doncic OUT (calf).", "url": "u1",
     "captured_at": "2026-01-15T11:00:00+00:00", "sport": "nba"},
    {"source_id": "x:2", "text": "Wind 18mph out to RF at Wrigley.", "url": "u2",
     "captured_at": "2026-04-10T17:00:00+00:00", "sport": "mlb"},
]


def test_mocksource_yields_validated_items():
    items = list(MockSource(_RECS).items())
    assert len(items) == 2
    assert all(isinstance(it, NewsItem) for it in items)
    assert items[0].captured_at == "2026-01-15T11:00:00+00:00"
    assert items[1].sport == "mlb"


def test_mocksource_stamps_default_when_missing():
    rec = [{"source_id": "x:9", "text": "t", "url": "u"}]
    it = list(MockSource(rec, default_captured_at="2026-01-15T09:00:00+00:00").items())[0]
    assert it.captured_at == "2026-01-15T09:00:00+00:00"


def test_mocksource_accepts_prebuilt_newsitem():
    ni = NewsItem(source_id="x:7", text="t", url="u", captured_at="2026-01-15T11:00:00+00:00")
    it = list(MockSource([ni]).items())[0]
    assert it.source_id == "x:7"


def test_adapter_rejects_bad_sport():
    bad = [{"source_id": "x:1", "text": "t", "url": "u",
            "captured_at": "2026-01-15T11:00:00+00:00", "sport": "cricket"}]
    with pytest.raises(AssertionError):
        list(MockSource(bad).items())


def test_adapter_rejects_missing_text():
    bad = [{"source_id": "x:1", "url": "u", "captured_at": "2026-01-15T11:00:00+00:00"}]
    with pytest.raises(KeyError):
        list(MockSource(bad).items())


def test_adapter_rejects_bad_captured_at():
    bad = [{"source_id": "x:1", "text": "t", "url": "u", "captured_at": "nope"}]
    with pytest.raises(ValueError):
        list(MockSource(bad).items())


def test_raw_sources_provenance():
    rs = MockSource(_RECS).raw_sources()
    assert {r.source_id for r in rs} == {"x:1", "x:2"}


def test_filesource_reads_json_list(tmp_path):
    p = tmp_path / "corpus.json"
    p.write_text(json.dumps(_RECS), encoding="utf-8")
    items = list(FileSource(str(p)).items())
    assert len(items) == 2
    assert items[0].source_id == "x:1"


def test_filesource_reads_items_wrapper(tmp_path):
    p = tmp_path / "corpus.json"
    p.write_text(json.dumps({"items": _RECS}), encoding="utf-8")
    assert len(list(FileSource(str(p)).items())) == 2


def test_filesource_reads_jsonl(tmp_path):
    p = tmp_path / "corpus.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in _RECS) + "\n", encoding="utf-8")
    items = list(FileSource(str(p)).items())
    assert len(items) == 2
    assert items[1].sport == "mlb"


def test_filesource_replay_is_hermetic_default(tmp_path):
    # a row missing captured_at is stamped with the FIXED default, never live 'now'
    p = tmp_path / "c.jsonl"
    p.write_text(json.dumps({"source_id": "x:3", "text": "t", "url": "u"}) + "\n",
                 encoding="utf-8")
    it = list(FileSource(str(p), default_captured_at="1970-01-01T00:00:00+00:00").items())[0]
    assert it.captured_at == "1970-01-01T00:00:00+00:00"


def test_filesource_missing_file_raises(tmp_path):
    with pytest.raises(AssertionError):
        list(FileSource(str(tmp_path / "nope.json")).items())


def test_livesource_is_a_stub():
    with pytest.raises(NotImplementedError):
        list(LiveSource("beat-feed").items())


def test_utc_now_iso_is_parseable():
    from datetime import datetime
    datetime.fromisoformat(utc_now_iso())  # no raise


def test_sourceadapter_is_abstract():
    with pytest.raises(TypeError):
        SourceAdapter()  # cannot instantiate the interface directly

"""Per-file test for the interaction_batch autoloop wiring (runner MOCKED).

Acceptance:
 * kind "interaction_batch" is a VALID_KIND and template_content_sha resolves a
   progress-advancing token (advances as the ledger grows).
 * run_cycle dispatches interaction_fn, bumps the K-ledger by new_deduped_k, and
   queues a survivor as a human_queue row -- all without importing/running the
   real factory fit (interaction_fn is injected).

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_interaction_wiring.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.autoloop import autoloop_runner as AR
from scripts.platformkit.autoloop import standing_prereg as SP


def _write_interaction_template(path, source_file):
    body = {
        "template_id": path.stem, "sport": "basketball_nba", "kind": "interaction_batch",
        "factory_template": "nba_shot_offense_x_offense",
        "source_globs": [str(source_file.name)],
        "interaction_ledger": "does/not/matter/here.jsonl",
        "universe": ["zone_efg_rim", "zone_efg_paint"],
        "corpus": {"source": "n/a"}, "bars": {"eps": 0.05},
        "k_ledger": "data/cache/autoloop/k_ledger/basketball_nba__%s.jsonl" % path.stem,
        "planted_null": {"required": False}, "max_candidates_per_cycle": 20,
    }
    body["prereg_sha"] = SP.compute_sha(body)
    path.write_text(json.dumps(body, sort_keys=True), encoding="utf-8")
    return body


def _noop_maintenance(watermarks, queue_fn=None):
    return {}


def test_interaction_batch_is_valid_kind():
    assert "interaction_batch" in SP.VALID_KINDS


def test_content_sha_advances_with_progress(tmp_path):
    src = tmp_path / "player_offense_events_2025_26.parquet"
    src.write_bytes(b"corpus-bytes")
    p = tmp_path / "T06_interaction_nba.json"
    # source_globs are repo-relative; point interaction_ledger at a tmp file we grow.
    body = {
        "template_id": "T06_interaction_nba", "sport": "basketball_nba",
        "kind": "interaction_batch", "factory_template": "nba_shot_offense_x_offense",
        "source_globs": ["scripts/platformkit/autoloop/standing_prereg.py"],  # a real repo file
        "interaction_ledger": None, "universe": ["zone_efg_rim"],
        "corpus": {"source": "n/a"}, "bars": {}, "k_ledger": "x.jsonl",
        "planted_null": {"required": False}, "max_candidates_per_cycle": 20,
    }
    body["prereg_sha"] = SP.compute_sha(body)
    p.write_text(json.dumps(body, sort_keys=True), encoding="utf-8")
    tpl = SP.load_template(p)
    assert tpl.ok, tpl.reason
    sha = SP.template_content_sha(tpl)
    assert sha and len(sha) == 64  # a resolvable content token


def test_run_cycle_dispatches_interaction_and_queues_survivor(tmp_path):
    tdir = tmp_path / "templates"
    tdir.mkdir()
    src = tmp_path / "src.parquet"
    src.write_bytes(b"x")
    _write_interaction_template(tdir / "T06_interaction_nba.json", src)

    def fake_interaction_fn(tpl):
        return {"fits_run": 4, "rejected": 3, "ship_review_queued": 1,
                "human_rows": [{"kind": "INTERACTION_SURVIVOR", "template_id": tpl.template_id,
                                "candidate_id": "nba_shot_offense_x_offense::zone_efg_rim__x__zone_efg_paint",
                                "effect": 0.031, "p": 0.0004, "n": 5200, "cum_K": 4,
                                "note": "PROVISIONAL", "edge_claimed": False}],
                "new_deduped_k": 4}

    paths = dict(report_path=tmp_path / "r.json", queue_path=tmp_path / "q.jsonl",
                 heartbeat_path=tmp_path / "hb.txt", k_ledger_dir=tmp_path / "kl",
                 watermark_path=tmp_path / "wm.json")
    report = AR.run_cycle(
        templates_dir=tdir, interaction_fn=fake_interaction_fn,
        corpus_sha_fn=lambda tpl: "sha_v1", refresh_fn=lambda: None,
        maintenance_fn=_noop_maintenance, **paths)

    row = report["per_template"][0]
    assert row["kind"] == "interaction_batch"
    assert row["fits_run"] == 4
    assert row["ship_review_queued"] == 1
    assert row["cum_k"] == 4  # new_deduped_k fed the autoloop FWER K-ledger
    assert report["human_queue_appended"] == 1

    queue_rows = [json.loads(l) for l in (tmp_path / "q.jsonl").read_text().splitlines()]
    assert any(r["kind"] == "INTERACTION_SURVIVOR" for r in queue_rows)

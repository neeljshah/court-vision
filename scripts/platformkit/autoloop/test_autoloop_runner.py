"""Per-file test for scripts.platformkit.autoloop.autoloop_runner.

Acceptance criteria (AUTOLOOP_SPEC_2026-07-06.md sec 6 test plan):
1. run_cycle one-shot on a tmp registry w/ a stub harness -> report shape +
   human-queue emission (SHIP_CANDIDATE row from a stub reclaim_fit).
2. PREREG_TAMPER anti-fake at the cycle level: a tampered template's row has
   prereg_tamper=true and fits_run=0; an ANOMALY queue row is appended.
3. skipped_no_new_data: unchanged corpus sha -> no fit, K flat.
4. stop-flag halt: serve_forever with should_stop=True runs zero cycles.
5. factory-absent (claims_regen with no real factory wired) -> honest
   SKIPPED_FAMILY status, cycle continues, no crash.
6. honesty-lint fail-closed: a report tripping the linter is not written.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_autoloop_runner.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.autoloop import autoloop_runner as AR
from scripts.platformkit.autoloop import standing_prereg as SP


def _write_template(path, *, kind="claims_regen", universe=None, extra=None):
    body = {
        "template_id": path.stem, "sport": "nba", "kind": kind,
        "universe": universe or ["sig_a"],
        "corpus": {"source": "n/a"}, "bars": {"source": "n/a"},
        "k_ledger": "data/cache/autoloop/k_ledger/nba__%s.jsonl" % path.stem,
        "planted_null": {"required": False}, "max_candidates_per_cycle": 8,
    }
    if extra:
        body.update(extra)
    body["prereg_sha"] = SP.compute_sha(body)
    path.write_text(json.dumps(body, sort_keys=True), encoding="utf-8")
    return body


def _paths(tmp_path):
    return dict(
        report_path=tmp_path / "report.json", queue_path=tmp_path / "queue.jsonl",
        heartbeat_path=tmp_path / "hb.txt", k_ledger_dir=tmp_path / "k_ledger",
        watermark_path=tmp_path / "watermark.json",
    )


def test_one_shot_stub_harness_report_shape_and_queue(tmp_path):
    tdir = tmp_path / "templates"
    tdir.mkdir()
    _write_template(tdir / "t01.json", kind="reclaim_fit", universe=["sig_a"])

    def stub_reclaim_fit(template, eligible):
        return {"fits_run": 1, "rejected": 0, "ship_review_queued": 1,
               "human_rows": [{"kind": "SHIP_CANDIDATE", "template_id": template.template_id}],
               "new_deduped_k": 1}

    report = AR.run_cycle(
        templates_dir=tdir, reclaim_fit_fn=stub_reclaim_fit,
        corpus_sha_fn=lambda tpl: "sha_v1", refresh_fn=lambda: None,
        **_paths(tmp_path),
    )
    assert "ts" in report and "wall_clock_sec" in report
    row = report["per_template"][0]
    assert row["template_id"] == "t01"
    assert row["fits_run"] == 1
    assert row["ship_review_queued"] == 1
    assert row["cum_k"] == 1
    assert report["human_queue_appended"] == 1

    queue_rows = [json.loads(l) for l in (tmp_path / "queue.jsonl").read_text().splitlines()]
    assert any(r["kind"] == "SHIP_CANDIDATE" for r in queue_rows)
    assert (tmp_path / "hb.txt").exists()
    assert json.loads((tmp_path / "report.json").read_text())["per_template"][0]["fits_run"] == 1


def test_prereg_tamper_at_cycle_level(tmp_path):
    tdir = tmp_path / "templates"
    tdir.mkdir()
    p = tdir / "t02.json"
    body = _write_template(p, kind="reclaim_fit")
    tampered = dict(body)
    tampered["max_candidates_per_cycle"] = 999
    p.write_text(json.dumps(tampered, sort_keys=True), encoding="utf-8")

    report = AR.run_cycle(
        templates_dir=tdir, corpus_sha_fn=lambda tpl: "sha_v1",
        refresh_fn=lambda: None, **_paths(tmp_path),
    )
    row = report["per_template"][0]
    assert row["prereg_tamper"] is True
    assert row["fits_run"] == 0
    assert row["status"] == "PREREG_TAMPER"

    queue_rows = [json.loads(l) for l in (tmp_path / "queue.jsonl").read_text().splitlines()]
    assert any(r["kind"] == "ANOMALY" and r.get("reason") == "PREREG_TAMPER" for r in queue_rows)


def test_skipped_no_new_data_keeps_k_flat(tmp_path):
    tdir = tmp_path / "templates"
    tdir.mkdir()
    _write_template(tdir / "t03.json", kind="reclaim_fit", universe=["sig_a"])
    calls = {"n": 0}

    def stub_reclaim_fit(template, eligible):
        calls["n"] += 1
        return {"fits_run": 1, "rejected": 1, "ship_review_queued": 0,
               "human_rows": [], "new_deduped_k": 1}

    paths = _paths(tmp_path)
    r1 = AR.run_cycle(templates_dir=tdir, reclaim_fit_fn=stub_reclaim_fit,
                      corpus_sha_fn=lambda tpl: "same_sha", refresh_fn=lambda: None, **paths)
    assert r1["per_template"][0]["cum_k"] == 1
    assert calls["n"] == 1

    r2 = AR.run_cycle(templates_dir=tdir, reclaim_fit_fn=stub_reclaim_fit,
                      corpus_sha_fn=lambda tpl: "same_sha", refresh_fn=lambda: None, **paths)
    assert r2["per_template"][0]["status"] == "skipped_no_new_data"
    assert r2["per_template"][0]["cum_k"] == 1  # unchanged -- K never inflated by a no-op tick
    assert calls["n"] == 1  # the stub harness was NOT called again


def test_stop_flag_halts_serve_forever(tmp_path):
    calls = {"cycles": 0}

    def fake_cycle(**kwargs):
        calls["cycles"] += 1
        return {"per_template": [], "human_queue_appended": 0}

    orig_run_cycle = AR.run_cycle
    AR.run_cycle = fake_cycle
    try:
        ticks = AR.serve_forever(should_stop=lambda: True, sleep=lambda s: None)
    finally:
        AR.run_cycle = orig_run_cycle
    assert ticks == 0
    assert calls["cycles"] == 0


def test_factory_absent_is_honest_skipped_family(tmp_path):
    tdir = tmp_path / "templates"
    tdir.mkdir()
    _write_template(tdir / "t04.json", kind="claims_regen", universe=["no_such_family"],
                    extra={"sport": "no_such_sport_xyz"})

    report = AR.run_cycle(
        templates_dir=tdir, corpus_sha_fn=lambda tpl: "sha_v1",
        refresh_fn=lambda: None, **_paths(tmp_path),
    )
    row = report["per_template"][0]
    assert row["status"] == "SKIPPED_FAMILY"
    assert row["claims_regenerated"] == 0


def test_honesty_lint_suppresses_write(tmp_path, monkeypatch):
    tdir = tmp_path / "templates"
    tdir.mkdir()
    _write_template(tdir / "t05.json", kind="reclaim_fit")
    monkeypatch.setattr(AR, "_honesty_clean", lambda obj: False)

    report_path = tmp_path / "report.json"
    report = AR.run_cycle(
        templates_dir=tdir, corpus_sha_fn=lambda tpl: "sha_v1",
        refresh_fn=lambda: None, report_path=report_path,
        queue_path=tmp_path / "queue.jsonl", heartbeat_path=tmp_path / "hb.txt",
        k_ledger_dir=tmp_path / "k_ledger", watermark_path=tmp_path / "watermark.json",
    )
    assert report.get("_write_suppressed") == "honesty_lint_tripped"
    assert not report_path.exists()


def test_should_stop_default_fail_safe_on_unreadable_flag(tmp_path, monkeypatch):
    bad_flag = tmp_path / "live_status.json"
    bad_flag.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(AR, "STOP_FLAG_PATH", bad_flag)
    assert AR.should_stop_default() is True  # unreadable -- fail-safe halt


def test_should_stop_default_false_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(AR, "STOP_FLAG_PATH", tmp_path / "absent.json")
    assert AR.should_stop_default() is False

"""Per-file test for scripts.platformkit.autoloop.standing_prereg.

Acceptance criteria (AUTOLOOP_SPEC_2026-07-06.md sec 6 test plan):
1. registry load + sha verify: a template whose body matches its prereg_sha
   LOADS ok=True.
2. THE ANTI-FAKE TEST (PREREG_TAMPER): a one-byte edit to any field WITHOUT
   re-shaing -> the loader flags PREREG_TAMPER, ok=False.
3. blocklist exclusion: a universe member with a live REJECT row is skipped
   (derived, not hand-copied); a stale-past-stale_after_days REJECT is
   eligible again.
4. K ledger: append-only, NEVER reset -- cum_k accumulates across appends.
5. watermark skip: is_due() False on an unchanged sha, True on a new one.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_standing_prereg.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.autoloop import standing_prereg as SP


def _write_template(path, *, kind="claims_regen", universe=None, extra=None):
    body = {
        "template_id": path.stem, "sport": "nba", "kind": kind,
        "universe": universe or ["sig_a", "sig_b"],
        "corpus": {"source": "n/a"}, "bars": {"source": "n/a"},
        "k_ledger": "data/cache/autoloop/k_ledger/nba__%s.jsonl" % path.stem,
        "planted_null": {"required": False}, "max_candidates_per_cycle": 2,
    }
    if extra:
        body.update(extra)
    body["prereg_sha"] = SP.compute_sha(body)
    path.write_text(json.dumps(body, sort_keys=True), encoding="utf-8")
    return body


def test_load_template_verifies_matching_sha(tmp_path):
    p = tmp_path / "t01.json"
    _write_template(p)
    tpl = SP.load_template(p)
    assert tpl.ok is True
    assert tpl.reason is None
    assert tpl.template_id == "t01"
    assert tpl.universe == ["sig_a", "sig_b"]


def test_prereg_tamper_anti_fake(tmp_path):
    """THE ANTI-FAKE TEST: a one-byte edit to a pinned field without re-shaing
    is refused as PREREG_TAMPER, never silently loaded."""
    p = tmp_path / "t02.json"
    body = _write_template(p)
    tampered = dict(body)
    tampered["max_candidates_per_cycle"] = body["max_candidates_per_cycle"] + 1
    p.write_text(json.dumps(tampered, sort_keys=True), encoding="utf-8")

    tpl = SP.load_template(p)
    assert tpl.ok is False
    assert tpl.reason == "PREREG_TAMPER"


def test_malformed_missing_field_refused(tmp_path):
    p = tmp_path / "t03.json"
    body = {"template_id": "t03", "sport": "nba", "kind": "claims_regen"}
    p.write_text(json.dumps(body), encoding="utf-8")
    tpl = SP.load_template(p)
    assert tpl.ok is False
    assert tpl.reason.startswith("MALFORMED_MISSING")


def test_load_all_templates_isolates_one_bad_template(tmp_path):
    _write_template(tmp_path / "good.json")
    (tmp_path / "bad.json").write_text("{not valid json", encoding="utf-8")
    tpls = SP.load_all_templates(tmp_path)
    by_id = {t.path.stem: t for t in tpls}
    assert by_id["good"].ok is True
    assert by_id["bad"].ok is False
    assert by_id["bad"].reason.startswith("UNREADABLE")


def test_blocklist_skips_live_reject_and_allows_stale(tmp_path):
    ledger = tmp_path / "reject_ledger.jsonl"
    from scripts.platformkit import reject_ledger as RL
    import datetime as _dt
    RL.record("nba", "sig_a", "REJECT", ledger_path=ledger)  # fresh -- blocked
    stale_ts = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=400)).isoformat()
    RL.record("nba", "sig_b", "REJECT", ts=stale_ts, ledger_path=ledger)  # old -- revisitable

    p = tmp_path / "t04.json"
    body = _write_template(p, universe=["sig_a", "sig_b", "sig_c"],
                          extra={"stale_after_days": 180})
    tpl = SP.load_template(p)
    blocked = SP.derive_blocklist(tpl, ledger_path=ledger)
    assert "sig_a" in blocked  # live REJECT -- blocked
    assert "sig_b" not in blocked  # REJECT older than stale_after_days -- revisitable
    assert "sig_c" not in blocked  # never tested -- eligible


def test_blocklist_hard_excludes_by_name(tmp_path):
    p = tmp_path / "t05.json"
    body = _write_template(p, universe=["sig_a", "sig_x"],
                          extra={"excluded_signals": ["sig_x"]})
    tpl = SP.load_template(p)
    blocked = SP.derive_blocklist(tpl, ledger_path=tmp_path / "empty_ledger.jsonl")
    assert "sig_x" in blocked
    assert "sig_a" not in blocked


def test_k_ledger_append_only_never_reset(tmp_path):
    base = tmp_path / "k_ledger"
    SP.k_ledger_append("nba", "t06", "2026-07-06T00:00:00Z", 3, 3, base_dir=base)
    SP.k_ledger_append("nba", "t06", "2026-07-06T01:00:00Z", 2, 5, base_dir=base)
    rows = SP.k_ledger_load("nba", "t06", base_dir=base)
    assert len(rows) == 2
    assert rows[0]["cum_k"] == 3
    assert rows[1]["cum_k"] == 5
    assert SP.k_ledger_cum_k("nba", "t06", base_dir=base) == 5


def test_watermark_skip_unchanged_sha_due_on_new_sha():
    watermarks = {}
    assert SP.is_due("t07", "sha_v1", watermarks) is True  # never seen -- always due
    watermarks["t07"] = {"corpus_sha": "sha_v1"}
    assert SP.is_due("t07", "sha_v1", watermarks) is False  # unchanged -- skip
    assert SP.is_due("t07", "sha_v2", watermarks) is True  # changed -- due again


def test_watermark_save_and_load_roundtrip(tmp_path):
    wpath = tmp_path / "watermark.json"
    SP.save_watermarks({"t08": {"corpus_sha": "abc", "last_run_ts": "now"}}, path=wpath)
    loaded = SP.load_watermarks(path=wpath)
    assert loaded["t08"]["corpus_sha"] == "abc"


def test_real_templates_dir_all_sha_verify():
    """Every tracked template under templates/ (T01-T05, incl. the mlb/soccer/
    tennis claims_regen additions) loads ok=True -- a real content edit
    without a re-shai would show up here as PREREG_TAMPER."""
    tpls = SP.load_all_templates()
    by_id = {t.template_id: t for t in tpls}
    expected = {
        "T01_claims_regen": "basketball_nba",
        "T02_reclaim_fit": "nba",
        "T03_claims_regen_mlb": "mlb",
        "T04_claims_regen_soccer": "soccer",
        "T05_claims_regen_tennis": "tennis",
    }
    for template_id, sport in expected.items():
        assert template_id in by_id, "%s missing from templates/" % template_id
        tpl = by_id[template_id]
        assert tpl.ok is True, "%s failed to load: %s" % (template_id, tpl.reason)
        assert tpl.sport == sport
        assert tpl.kind in SP.VALID_KINDS


def test_new_claims_regen_templates_content_sha_and_due():
    """The 3 new claims_regen templates (mlb/soccer/tennis) resolve a real
    per-family source-parquet content sha and evaluate is_due() cleanly --
    the same dry-run the daemon does before ever calling run_claims_regen."""
    tpls = {t.template_id: t for t in SP.load_all_templates()}
    for template_id in ("T03_claims_regen_mlb", "T04_claims_regen_soccer",
                        "T05_claims_regen_tennis"):
        tpl = tpls[template_id]
        assert tpl.kind == "claims_regen"
        sha = SP.template_content_sha(tpl)
        assert sha, "%s: no content sha resolved (source parquet missing?)" % template_id
        assert SP.is_due(tpl.template_id, sha, {}) is True
        assert SP.is_due(tpl.template_id, sha, {tpl.template_id: {"corpus_sha": sha}}) is False

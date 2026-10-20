import json

from scripts.platformkit.eval_gate import desk_uptime_report as m


def _fixture(root):
    f = root / "docs/evidence/forward"
    for sub in ("schedules", "nights", "live_shadow", "paper_result"):
        (f / sub).mkdir(parents=True)
    runs = {"2026-09-24": "2026-09-24T10:00:00Z", "2026-09-26": "2026-09-26T22:00:00Z"}
    for d, t in runs.items():
        (f / "schedules" / f"{d}_maker_forward.json").write_text(json.dumps([{"game_id": "a"}, {"game_id": "b"}]))
        (f / "schedules" / f"{d}_run.json").write_text(json.dumps({"completed_at": t}))
    (f / "nights" / "2026-09-24.json").write_text(json.dumps({"status": "PARTIAL", "reasons": ["free_ram_below_floor"]}))
    return root


def test_table_and_dark_spell(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "START", "2026-09-24")
    monkeypatch.setattr(m, "END", "2026-09-26")
    r = m.write(_fixture(tmp_path))
    assert (r["days"], r["scheduled"], r["served"], r["scored"]) == (3, 2, 2, 1)
    assert r["dark_spells"][0] == {"start": "2026-09-24T10:00Z", "end": "2026-09-26T22:00Z", "hours": 60.0}
    assert r["partial_reasons"] == {"free_ram_below_floor": 1}
    assert [x["night"] for x in r["table"]] == ["PARTIAL", None, None]
    assert m.check(tmp_path)


def test_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "START", "2026-09-24")
    monkeypatch.setattr(m, "END", "2026-09-26")
    _fixture(tmp_path)
    m.write(tmp_path)
    md = tmp_path / "docs/evidence/DESK_UPTIME_2026-10-20.md"
    a = md.read_text()
    md.write_text("intro\n" + a + "outro\n")
    m.write(tmp_path)
    assert md.read_text() == "intro\n" + a + "outro\n"

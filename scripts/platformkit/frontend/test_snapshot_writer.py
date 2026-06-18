"""Per-file test for scripts.platformkit.frontend.snapshot_writer (network-free).

Injects fake slate/live builders + a tmp out_dir so nothing touches the corpus or the
network. Covers: a healthy write + round-trip, the degrade path (slate raises ->
status='unavailable', no raise), read_snapshot round-trips and misses, write_all over
several sports, and the <=300 LOC budget.

Run:  cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/frontend/test_snapshot_writer.py -q
"""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit.frontend import snapshot_writer as sw

_REQUIRED_KEYS = {"sport", "generated_at", "status", "slate", "live", "props",
                  "freshness", "honest_note"}


def _fake_props(sport, **kw):
    return {"sport": sport, "status": "ok",
            "edges": [{"player": "X", "stat": "shots", "reliable": True}],
            "unresolved": [], "unresolved_count": 0}


def _fake_slate(sport, **kw):
    return {"sport": sport, "status": "ok", "rows": [{"matchup": "A vs B"}],
            "saw_odds": kw.get("odds_lookup") is not None}


def _fake_live(sport, **kw):
    return {"sport": sport, "status": "ok", "games": [], "n_live": 0}


def _fake_odds_factory(sport):
    return lambda s, h, a: {"bookX": {h: 1.9, a: 2.0}}


def test_writes_and_round_trips(tmp_path: Path):
    env = sw.build_snapshot("nba", slate_builder=_fake_slate,
                            live_builder=_fake_live,
                            odds_lookup_factory=_fake_odds_factory,
                            prop_builder=_fake_props,
                            out_dir=tmp_path)
    assert _REQUIRED_KEYS <= set(env)
    assert env["status"] == "ok"
    assert env["sport"] == "nba"
    assert env["freshness"]["source"] == "snapshot"
    # file actually written + JSON round-trips
    path = tmp_path / "nba.json"
    assert path.exists()
    loaded = sw.read_snapshot("nba", out_dir=tmp_path)
    assert loaded == env
    # odds_lookup from the factory reached the slate builder
    assert env["slate"]["saw_odds"] is True


def test_props_section_present_when_builder_supplied(tmp_path: Path):
    env = sw.build_snapshot("soccer_intl", slate_builder=_fake_slate,
                            live_builder=_fake_live, prop_builder=_fake_props,
                            out_dir=tmp_path)
    assert "props" in env and env["props"]["status"] == "ok"
    assert env["props"]["edges"][0]["reliable"] is True
    # round-trips through disk unchanged
    loaded = sw.read_snapshot("soccer_intl", out_dir=tmp_path)
    assert loaded["props"] == env["props"]


def test_props_builder_raising_degrades_not_blocks(tmp_path: Path):
    def boom_props(sport, **kw):
        raise RuntimeError("provider down")

    env = sw.build_snapshot("soccer_intl", slate_builder=_fake_slate,
                            live_builder=_fake_live, prop_builder=boom_props,
                            out_dir=tmp_path)  # must NOT raise
    assert env["status"] == "ok"  # slate fine; props degrade independently
    assert env["props"]["status"] == "unavailable"
    assert "error" in env["props"]["reason"].lower()
    assert env["props"]["edges"] == []


def test_props_none_when_no_builder(tmp_path: Path):
    # prop_builder explicitly None AND no module default reachable here would yield
    # None; we pass a builder=None and rely on the real default. Either way it must
    # be a dict-or-None, never a raise.
    env = sw.build_snapshot("nba", slate_builder=_fake_slate,
                            live_builder=_fake_live, out_dir=tmp_path)
    assert "props" in env
    assert env["props"] is None or isinstance(env["props"], dict)


def test_degrade_when_slate_raises(tmp_path: Path):
    def boom(sport, **kw):
        raise RuntimeError("corpus missing")

    env = sw.build_snapshot("mlb", slate_builder=boom, live_builder=_fake_live,
                            out_dir=tmp_path)  # must NOT raise
    assert env["status"] == "unavailable"
    assert env["sport"] == "mlb"
    assert _REQUIRED_KEYS <= set(env)
    # still written to disk despite the failure
    assert (tmp_path / "mlb.json").exists()
    loaded = sw.read_snapshot("mlb", out_dir=tmp_path)
    assert loaded["status"] == "unavailable"


def test_degrade_when_live_raises(tmp_path: Path):
    def boom_live(sport, **kw):
        raise RuntimeError("feed down")

    env = sw.build_snapshot("nba", slate_builder=_fake_slate,
                            live_builder=boom_live, out_dir=tmp_path)
    assert env["status"] == "ok"  # slate is fine; live degrades independently
    assert env["live"]["status"] == "unavailable"
    assert "error" in env["live"]["note"].lower()


def test_odds_factory_failure_does_not_block(tmp_path: Path):
    def boom_odds(sport):
        raise RuntimeError("odds down")

    env = sw.build_snapshot("nba", slate_builder=_fake_slate,
                            live_builder=_fake_live,
                            odds_lookup_factory=boom_odds, out_dir=tmp_path)
    assert env["status"] == "ok"
    assert env["slate"]["saw_odds"] is False  # built without odds


def test_read_missing_returns_none(tmp_path: Path):
    assert sw.read_snapshot("tennis", out_dir=tmp_path) is None


def test_read_corrupt_returns_none(tmp_path: Path):
    (tmp_path / "soccer.json").write_text("{not valid json", encoding="utf-8")
    assert sw.read_snapshot("soccer", out_dir=tmp_path) is None


def test_write_all_multiple_sports(tmp_path: Path):
    sports = ["nba", "mlb", "soccer"]
    paths = sw.write_all(sports, slate_builder=_fake_slate,
                         live_builder=_fake_live, out_dir=tmp_path)
    assert set(paths) == set(sports)
    for sport in sports:
        assert Path(paths[sport]).exists()
        assert sw.read_snapshot(sport, out_dir=tmp_path)["status"] == "ok"


def test_write_all_one_sport_failing_does_not_stop_others(tmp_path: Path):
    def maybe_boom(sport, **kw):
        if sport == "mlb":
            raise RuntimeError("only mlb broken")
        return _fake_slate(sport, **kw)

    paths = sw.write_all(["nba", "mlb", "soccer"], slate_builder=maybe_boom,
                         live_builder=_fake_live, out_dir=tmp_path)
    # all three attempted + written (mlb as unavailable); none stopped the loop
    assert set(paths) == {"nba", "mlb", "soccer"}
    assert sw.read_snapshot("mlb", out_dir=tmp_path)["status"] == "unavailable"
    assert sw.read_snapshot("nba", out_dir=tmp_path)["status"] == "ok"


def test_loc_budget():
    src = Path(sw.__file__)
    n = sum(1 for _ in src.open("r", encoding="utf-8"))
    assert n <= 300, f"snapshot_writer.py is {n} LOC (>300)"

"""Per-file test for scripts.platformkit.props.props_pred_tick_runner.

Focus: the ALWAYS-FRESH cache invariant -- EVERY m13 tick must write a
fresh-stamped prop_cards_cache (atomic), even when the compute returns empty or
raises, so the cache can never read perpetually-stale while m13 is alive. An
honest fresh-but-empty cache beats a stale 472-card cache that gets omitted.

Run: cd /c/Users/neelj/nba-ai-system && \
     python -m pytest scripts/platformkit/props/test_props_pred_tick_runner.py -q
"""
from __future__ import annotations

import json

import scripts.platformkit.props.props_pred_tick_runner as runner
import scripts.platformkit.bestbets.prop_cards_cache as cache


def _card(sport="mlb", model_only=True):
    return {
        "sport": sport, "market_type": "prop", "prop_player": "P",
        "prop_stat": "Hits", "line": 1.5, "side": "over", "model_prob": 0.6,
        "proj": 2.0, "market_prob": None if model_only else 0.55,
        "edge_vs_market": None if model_only else 0.05, "units": 1.0,
        "model_only": model_only, "edge_claimed": False, "status": "pregame",
    }


def _patch_cache_path(monkeypatch, tmp_path):
    p = tmp_path / "prop_cards_cache.json"
    monkeypatch.setattr(cache, "_DEFAULT_PATH", p)
    return p


def test_tick_writes_fresh_cache_with_cards(monkeypatch, tmp_path):
    cache_p = _patch_cache_path(monkeypatch, tmp_path)
    snap_p = tmp_path / "snap.json"
    monkeypatch.setattr(runner, "_score_props_bounded",
                        lambda now: ([_card()], {"mlb": 3}))
    env = runner.tick(now=12345.0, output_path=snap_p)
    assert env["overall"] == "ok"
    # the m10-read cache exists, is fresh-stamped at NOW, and has the card.
    doc = json.loads(cache_p.read_text(encoding="ascii"))
    assert doc["generated_at"] == 12345.0
    assert doc["card_count"] == 1
    rd = cache.read(now_epoch=12345.0 + 10.0, sla_sec=600.0)
    assert rd["status"] == "fresh" and rd["card_count"] == 1


def test_empty_compute_genuinely_empty_writes_fresh_unavailable(monkeypatch, tmp_path):
    # Empty compute AND no pregame games on disk -> honest fresh UNAVAILABLE cache at
    # NOW (not stale). pregame_fn=False makes the "genuinely empty slate" explicit so
    # the anti-flicker guard does NOT fill. (Old bug: empty -> no fresh cache -> aged
    # out -> omitted; fix: still stamp fresh.)
    cache_p = _patch_cache_path(monkeypatch, tmp_path)
    snap_p = tmp_path / "snap.json"
    monkeypatch.setattr(runner, "_score_props_bounded", lambda now: ([], {}))
    env = runner.tick(now=999.0, output_path=snap_p,
                      pregame_fn=lambda now: False)
    assert env["overall"] == "UNAVAILABLE"
    doc = json.loads(cache_p.read_text(encoding="ascii"))
    assert doc["generated_at"] == 999.0          # fresh stamp, not stale
    assert doc["overall"] == "UNAVAILABLE"
    assert doc["card_count"] == 0
    # a read right after is FRESH (honest empty), never "stale".
    rd = cache.read(now_epoch=999.0 + 10.0, sla_sec=600.0)
    assert rd["status"] == "fresh"


def test_score_raises_genuinely_empty_writes_fresh_unavailable(monkeypatch, tmp_path):
    # A hard failure inside scoring + no pregame games on disk must still write a
    # fresh UNAVAILABLE cache (heartbeat-honest empty, not a stale omit).
    cache_p = _patch_cache_path(monkeypatch, tmp_path)
    snap_p = tmp_path / "snap.json"

    def boom(now):
        raise RuntimeError("429 / engine blew up")
    monkeypatch.setattr(runner, "_score_props_bounded", boom)
    env = runner.tick(now=555.0, output_path=snap_p,
                      pregame_fn=lambda now: False)
    assert env["overall"] == "UNAVAILABLE"
    doc = json.loads(cache_p.read_text(encoding="ascii"))
    assert doc["generated_at"] == 555.0          # still fresh-stamped
    assert doc["card_count"] == 0


def test_every_tick_advances_cache_generated_at(monkeypatch, tmp_path):
    # Across ticks the cache generated_at must always advance to the latest NOW,
    # so it can never read perpetually-stale while m13 is alive.
    cache_p = _patch_cache_path(monkeypatch, tmp_path)
    snap_p = tmp_path / "snap.json"
    monkeypatch.setattr(runner, "_score_props_bounded", lambda now: ([], {}))
    for t in (100.0, 460.0, 820.0):
        runner.tick(now=t, output_path=snap_p, pregame_fn=lambda now: False)
        doc = json.loads(cache_p.read_text(encoding="ascii"))
        assert doc["generated_at"] == t


def test_no_dollar_fields_in_cache(monkeypatch, tmp_path):
    cache_p = _patch_cache_path(monkeypatch, tmp_path)
    snap_p = tmp_path / "snap.json"
    monkeypatch.setattr(runner, "_score_props_bounded",
                        lambda now: ([_card(model_only=False)], {}))
    runner.tick(now=1.0, output_path=snap_p)
    raw = cache_p.read_text(encoding="ascii")
    for banned in ("dollar_pnl", "pnl_usd", '"usd"', '"pnl"', '"roi"'):
        assert banned not in raw


# ---------------------------------------------------------------------------
# ANTI-FLICKER guard: a transient empty while pregame games exist must NOT zero
# the board -- it recomputes a model-only synth-only fill (the /bets 526<->0 fix).
# ---------------------------------------------------------------------------

def test_transient_empty_with_pregame_games_fills_from_synth(monkeypatch, tmp_path):
    # Full score transiently returns 0 cards, BUT pregame games exist on disk, AND
    # the synth-only fill produces cards -> the tick serves the fill, NOT an empty.
    cache_p = _patch_cache_path(monkeypatch, tmp_path)
    snap_p = tmp_path / "snap.json"
    monkeypatch.setattr(runner, "_score_props_bounded", lambda now: ([], {}))
    env = runner.tick(now=42.0, output_path=snap_p,
                      pregame_fn=lambda now: True,
                      synth_fill_fn=lambda now: ([_card()], {"mlb": 4}))
    assert env["overall"] == "ok"
    assert env["card_count"] == 1
    doc = json.loads(cache_p.read_text(encoding="ascii"))
    assert doc["overall"] == "ok"
    assert doc["card_count"] == 1                 # board did NOT flicker to 0
    assert doc["n_more_model_only"] == {"mlb": 4}
    # every served card is the honest model-only kind (no $ edge)
    assert doc["cards"][0]["model_only"] is True
    assert doc["cards"][0]["edge_claimed"] is False


def test_genuinely_empty_slate_reads_unavailable(monkeypatch, tmp_path):
    # No pregame games on disk -> even with a transient empty, the synth fill is not
    # consulted (or returns nothing) -> honest fresh UNAVAILABLE, never a fabricated
    # card. This is the only path that may write an empty cache.
    cache_p = _patch_cache_path(monkeypatch, tmp_path)
    snap_p = tmp_path / "snap.json"
    monkeypatch.setattr(runner, "_score_props_bounded", lambda now: ([], {}))
    calls = {"synth": 0}

    def synth(now):
        calls["synth"] += 1
        return ([], {})
    env = runner.tick(now=7.0, output_path=snap_p,
                      pregame_fn=lambda now: False, synth_fill_fn=synth)
    assert env["overall"] == "UNAVAILABLE"
    assert calls["synth"] == 0                    # no pregame games -> no fill attempt
    doc = json.loads(cache_p.read_text(encoding="ascii"))
    assert doc["overall"] == "UNAVAILABLE"
    assert doc["card_count"] == 0
    assert cache.read(now_epoch=7.0 + 5.0)["status"] == "fresh"  # honest empty


def test_multi_tick_board_never_drops_to_zero_with_injected_transient(
        monkeypatch, tmp_path):
    # Simulate several m13 ticks where SOME ticks suffer a transient feed failure
    # (score -> 0) while pregame games exist. The cache card_count must NEVER hit 0
    # across the run; it stays populated via either the full score or the synth fill.
    cache_p = _patch_cache_path(monkeypatch, tmp_path)
    snap_p = tmp_path / "snap.json"

    # ticks 0,2,4 = healthy full score (3 cards); ticks 1,3 = transient empty.
    seq = iter([3, 0, 3, 0, 3])

    def score(now):
        n = next(seq)
        return ([_card() for _ in range(n)], {"mlb": n})
    monkeypatch.setattr(runner, "_score_props_bounded", score)
    # pregame games always exist; the synth fill always supplies 2 model-only cards.
    counts = []
    for t in (100.0, 400.0, 700.0, 1000.0, 1300.0):
        runner.tick(now=t, output_path=snap_p,
                    pregame_fn=lambda now: True,
                    synth_fill_fn=lambda now: ([_card(), _card()], {}))
        doc = json.loads(cache_p.read_text(encoding="ascii"))
        counts.append(doc["card_count"])
    # 3 on healthy ticks, 2 on the transient ticks -- NEVER 0.
    assert counts == [3, 2, 3, 2, 3]
    assert 0 not in counts


def test_guard_skipped_when_score_fn_injected(monkeypatch, tmp_path):
    # When a test injects score_fn (raw-path determinism), the anti-flicker guard is
    # SKIPPED entirely -- an injected empty stays empty regardless of pregame_fn.
    cache_p = _patch_cache_path(monkeypatch, tmp_path)
    snap_p = tmp_path / "snap.json"
    fill_called = {"n": 0}

    def synth(now):
        fill_called["n"] += 1
        return ([_card()], {})
    env = runner.tick(now=1.0, output_path=snap_p, score_fn=lambda now: [],
                      pregame_fn=lambda now: True, synth_fill_fn=synth)
    assert env["overall"] == "UNAVAILABLE"
    assert fill_called["n"] == 0                  # guard not consulted on raw path
    doc = json.loads(cache_p.read_text(encoding="ascii"))
    assert doc["card_count"] == 0


def test_real_score_timeout_falls_back_to_synth_not_zero(monkeypatch, tmp_path):
    # 2026-07-05 LANE m13-zero-cards diagnosis: production observed (live probe,
    # wave-39/wave-40) the REAL board (build_bounded_prop_cards) taking 365-481s
    # wall-clock -- longer than SCORE_TIMEOUT_SEC (240s) -- so EVERY tick times out
    # and must fall back to the synth-only path. This test locks in that the
    # timeout path (not just an injected score_fn returning []) still reaches the
    # anti-flicker guard and serves synth cards instead of degrading to 0, using
    # the REAL default (score_fn=None) code path through score_with_timeout.
    cache_p = _patch_cache_path(monkeypatch, tmp_path)
    snap_p = tmp_path / "snap.json"

    def hangs_past_timeout(now):
        import time as _t
        _t.sleep(5.0)  # >> the tiny score_timeout_sec used below
        return ([_card()], {"mlb": 999})  # never observed by the caller

    monkeypatch.setattr(runner, "_score_props_bounded", hangs_past_timeout)
    env = runner.tick(now=99.0, output_path=snap_p,
                      pregame_fn=lambda now: True,
                      synth_fill_fn=lambda now: ([_card()], {"mlb": 7}),
                      score_timeout_sec=0.05)
    assert env["overall"] == "ok"
    assert env["card_count"] == 1                  # synth fill served, not 0
    assert env["n_more_model_only"] == {"mlb": 7}   # the SYNTH tally, not the hung one
    doc = json.loads(cache_p.read_text(encoding="ascii"))
    assert doc["card_count"] == 1
    assert doc["cards"][0]["model_only"] is True
    assert doc["cards"][0]["edge_claimed"] is False

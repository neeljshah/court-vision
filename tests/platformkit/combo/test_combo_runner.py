"""tests.platformkit.combo.test_combo_runner -- INERT + checkpoint-resume + STALE + replay.

The five Lane-L invariants, per-file (full pytest freezes the box):
  * sentinel ABSENT  -> a full cycle is NO_CANDIDATE (proposes/records nothing, ships nothing).
  * checkpoint resume -> a restart re-derives the cursor losslessly (processed monotone).
  * null-ship freeze  -> a gate that SHIPs a null-tagged spec freezes the family in the bandit.
  * --replay          -> re-runs the SINGLE frozen spec through the gate, does NOT re-enumerate,
                         and does NOT advance the checkpoint.
  * STALE feed        -> decision DEGRADED, cursor NOT advanced (never reads green).

ASCII; stdlib + numpy deps.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.combo import combo_bandit as B  # noqa: E402
from scripts.platformkit.combo import combo_runner as RUN  # noqa: E402
from scripts.platformkit.combo.combination_families import CombinationSpec  # noqa: E402
from scripts.platformkit.improve import pipeline_flag as PF  # noqa: E402


def _settled_fn(n=14):
    def _fn(name, since="", seen_ids=None, **kw):
        games = []
        for i in range(n):
            det0 = {"run_diff": float(i - n / 2), "pace": float(1 + (i % 3))}
            det1 = {"run_diff": float(i - n / 2 + 1), "pace": float(1 + ((i + 1) % 3))}
            games.append({"sport": name, "game_id": "G%02d" % i, "outcome": 1.0,
                          "states": [{"p0": 0.55, "outcome": 1.0, "detail": det0},
                                     {"p0": 0.40, "outcome": 0.0, "detail": det1}]})
        return games
    return _fn


def _paths(tmp_path):
    # ledger_path pins the SECOND K source (S40b / RT-20) to an empty tmp ledger, so these
    # tests read K from their own checkpoint only and never from the canonical repo ledger.
    return dict(ckpt_path=str(tmp_path / "ckpt.json"),
                state_path=str(tmp_path / "bandit.json"),
                proposals_path=str(tmp_path / "prop.jsonl"),
                reject_path=str(tmp_path / "rej.jsonl"),
                status_path=str(tmp_path / "stat.jsonl"),
                ledger_path=str(tmp_path / "fwer.jsonl"))


def test_inert_no_candidate_when_sentinel_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(PF, "SENTINEL_PATH", tmp_path / "ABSENT")
    res = RUN.combo_cycle("nba", settled_games_fn=_settled_fn(14), **_paths(tmp_path))
    assert res.decision == RUN.NO_CANDIDATE
    assert res.n_built == 0          # the build choke returned None for every spec.
    assert res.n_proposed == 0       # nothing ships / is served.
    assert res.n_enumerated > 0      # it DID propose specs + record reject-lessons (inert, not dead).
    assert len(res.proposals) == 0


def test_checkpoint_resume_is_lossless(monkeypatch, tmp_path):
    monkeypatch.setattr(PF, "SENTINEL_PATH", tmp_path / "ABSENT")
    p = _paths(tmp_path)
    r1 = RUN.combo_cycle("nba", settled_games_fn=_settled_fn(10), now=1.0, **p)
    from scripts.platformkit.improve.checkpoint import load_checkpoint
    c1 = load_checkpoint(p["ckpt_path"]).cursor("nba")
    assert c1["processed"] == 10 and c1["combo_k"] == r1.k_cumulative
    # Restart: same settled feed (all already seen) -> processed does NOT double-count.
    r2 = RUN.combo_cycle("nba", settled_games_fn=_settled_fn(10), now=2.0, **p)
    c2 = load_checkpoint(p["ckpt_path"]).cursor("nba")
    assert c2["combo_k"] >= c1["combo_k"]          # cumulative K only grows.
    assert c2["last_decision"] == r2.decision
    assert set(c1["seen_ids"]).issubset(set(c2["seen_ids"]))  # seen-ids monotone.


def test_stale_feed_is_degraded_never_green(monkeypatch, tmp_path):
    monkeypatch.setattr(PF, "SENTINEL_PATH", tmp_path / "ABSENT")
    p = _paths(tmp_path)
    # No injected settled_games_fn -> real ingest with an injected DEAD http_get (STALE).
    def _dead_http(url):
        raise OSError("feed down")
    res = RUN.combo_cycle("nba", http_get=_dead_http, dates=["20260101"], **p)
    assert res.status in ("STALE", "DEGRADED")
    assert res.decision == RUN.SHIPPED_DEGRADED        # never NO_CANDIDATE-green
    from scripts.platformkit.improve.checkpoint import load_checkpoint
    cur = load_checkpoint(p["ckpt_path"]).cursor("nba")
    assert cur.get("processed", 0) == 0                # cursor FROZEN (dead feed).
    # The combo status block reads DEGRADED, never ok.
    from scripts.platformkit.combo import combo_status as ST
    blk = ST.combo_block(status_path=p["status_path"])
    assert blk["severity"] == ST.DEGRADED


def test_replay_reruns_frozen_spec_without_enumerating(monkeypatch, tmp_path):
    monkeypatch.setattr(PF, "SENTINEL_PATH", tmp_path / "ABSENT")
    p = _paths(tmp_path)
    spec = CombinationSpec(family="COMB_DETAIL_x_DETAIL", sport="nba", target="winprob",
                           signature="comb_detail_x_detail=a:pace|b:run_diff",
                           params={"a": "pace", "b": "run_diff"})
    res = RUN.combo_cycle("nba", settled_games_fn=_settled_fn(12),
                          replay_spec=spec, now=5.0, **p)
    assert res.n_enumerated == 1                       # exactly the frozen spec, no enumeration.
    # Replay does NOT advance the checkpoint (deterministic reproduction, not progress).
    assert not Path(p["ckpt_path"]).exists()
    assert not Path(p["state_path"]).exists()


def test_null_ship_freezes_family_through_runner(monkeypatch, tmp_path):
    """A NON-replay cycle whose gate SHIPs a null-tagged spec must FREEZE that family in the
    PERSISTED bandit (proving the runner's B.update(is_null=...) wiring, not just the bandit)."""
    sentinel = tmp_path / "PIPELINE_ENABLED"
    sentinel.write_text("on", encoding="ascii")
    monkeypatch.setattr(PF, "SENTINEL_PATH", sentinel)
    p = _paths(tmp_path)

    class NullSpec(CombinationSpec):
        is_null = True

    # Enumeration yields plain specs; tag the first built spec as null by patching the family
    # producer so the runner's is_null read (getattr(spec, "is_null")) fires on a real cycle.
    import scripts.platformkit.combo.combo_runner as RUNMOD
    orig = RUNMOD.all_combination_specs

    def _one_null_spec(sport, target, handles):
        # A buildable detail_x_detail combo over the two legs the settled feed carries,
        # tagged null so the runner's is_null read fires on a real (non-replay) cycle.
        return [NullSpec("COMB_DETAIL_x_DETAIL", sport, target,
                         "comb_detail_x_detail=a:pace|b:run_diff",
                         {"a": "pace", "b": "run_diff"})]
    monkeypatch.setattr(RUNMOD, "all_combination_specs", _one_null_spec)

    def _ship_gate(cand, *, k, n_corpora):
        return {"verdict": B.SHIP, "reason": "test-null-ship", "layer": "L6"}
    res = RUN.combo_cycle("nba", settled_games_fn=_settled_fn(16), gate_fn=_ship_gate,
                          now=7.0, **p)
    assert res.n_proposed == 1
    st = B.load_state(p["state_path"])
    fam = res.proposals[0]["family"]
    assert B.is_frozen(st, fam) is True            # null shipped -> family FROZEN, persisted.
    assert fam in __import__(
        "scripts.platformkit.improve.prioritizer", fromlist=["frozen_families"]
    ).frozen_families(B.frozen_ledger(st))


def test_s40b_rt20_deleted_checkpoint_cannot_restore_the_bar(monkeypatch, tmp_path):
    """RT-20: prior_k came ONLY from the per-sport checkpoint, so deleting one JSON
    restored the per-test bar. Measured before the fix, with the ledger at K=240:
    warm checkpoint -> k_cumulative 240 (eps_eff 0.0002083); fresh checkpoint -> 0
    (eps_eff 0.05), a 240x looser bar. K is now max(checkpoint, ledger)."""
    from scripts.platformkit.combo.fwer_budget import eps_eff

    monkeypatch.setattr(PF, "SENTINEL_PATH", tmp_path / "ABSENT")
    p = _paths(tmp_path)
    Path(p["ledger_path"]).write_text('{"k_cumulative": 240}\n', encoding="ascii")

    def _no_games(name, since="", seen_ids=None, **kw):
        return []

    res = RUN.combo_cycle("nba", settled_games_fn=_no_games, **p)   # no checkpoint at all
    assert res.k_cumulative == 240
    # the bar the ledger's own K implies, derived here rather than copied from the runner.
    assert eps_eff(0.05, res.k_cumulative) == 0.05 / 240

    # an ADVANCED checkpoint still wins over a lagging ledger (the larger of the two).
    Path(p["ckpt_path"]).write_text(
        '{"cycle": 0, "cursors": {"nba": {"combo_k": 900}}}', encoding="ascii")
    assert RUN.combo_cycle("nba", settled_games_fn=_no_games, **p).k_cumulative == 900


def test_s40b_rt20_unreadable_ledger_never_blocks_a_cycle(tmp_path):
    """The ledger is a SECOND opinion, not a dependency: an absent one falls back to
    the checkpoint rather than raising (combo_cycle never raises)."""
    from scripts.platformkit.combo.combo_runner import _ledger_k

    assert _ledger_k(str(tmp_path / "nope.jsonl")) == 0
    Path(tmp_path / "torn.jsonl").write_text("{not json\n", encoding="ascii")
    assert _ledger_k(str(tmp_path / "torn.jsonl")) == 0

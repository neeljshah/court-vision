"""Per-file test for scripts.platformkit.gate_run_tennis_setdetail.

Synthetic (no on-disk corpora) so it is fast and deterministic. Verifies:
  * build_corpus_with_layer joins the additive layer leak-free by event_id and
    injects the planted-null column;
  * gate_one returns both-corpus clustered-DM + a cross-corpus replication verdict
    whose SHIP requires BOTH corpora to win;
  * the PLANTED-NULL pure-noise column REJECTS through the IDENTICAL gate (proving
    the gate can FAIL a signal); when it does not, run() reports NOT_TESTABLE;
  * a planted-leak feature (= the outcome) does NOT silently SHIP as the layer
    verdict via the noise channel -- i.e. the runner is proposal-only and the
    null-control gate is load-bearing.

Calibration only; no $ / edge asserted anywhere. ASCII-only.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

import scripts.platformkit.gate_run_tennis_setdetail as gr


def _synth_matches(n: int = 600, seed: int = 1) -> pd.DataFrame:
    """Tiny synthetic ATP-like corpus the real builders accept (event_id 1:1)."""
    rng = np.random.default_rng(seed)
    n_players = 40
    dates = pd.date_range("2018-01-01", periods=n, freq="D")
    p1 = rng.integers(0, n_players, n)
    p2 = (p1 + rng.integers(1, n_players, n)) % n_players
    winner = rng.integers(1, 3, n)  # 1 or 2
    # plausible best-of-3 winner-first scores with occasional tiebreaks
    scores = []
    for _ in range(n):
        if rng.random() < 0.3:
            scores.append("7-6(5) 6-4")
        else:
            scores.append("6-3 6-4")
    return pd.DataFrame({
        "event_id": [f"e{i}" for i in range(n)],
        "date": dates, "tour": "atp",
        "tourney_id": "t0", "round": "R32",
        "match_num": np.arange(n),
        "p1_id": p1, "p2_id": p2, "winner": winner,
        "score": scores, "surface": rng.choice(["Hard", "Clay", "Grass"], n),
        "retirement": False, "best_of": 3,
    })


def test_build_corpus_joins_layer_and_null_column():
    m = _synth_matches()
    df = gr.build_corpus_with_layer(m, seed=0)
    assert len(df) == len(m)                       # 1:1 join, no row blow-up
    assert gr._NULL_COL in df.columns              # planted null present
    for c in gr._DIFF_COLS:
        assert c in df.columns                     # additive diffs joined in
    # planted null is pure noise: near-zero correlation with the outcome label.
    y = (df["winner"] == 1).astype(float).to_numpy()
    corr = abs(np.corrcoef(df[gr._NULL_COL].to_numpy(), y)[0, 1])
    assert corr < 0.25


def test_gate_one_verdict_shape_and_both_corpus_dm():
    m_atp = _synth_matches(seed=1)
    m_wta = _synth_matches(seed=2)
    atp = gr.build_corpus_with_layer(m_atp, seed=0)
    wta = gr.build_corpus_with_layer(m_wta, seed=0)
    r = gr.gate_one(atp, wta, gr._DIFF_COLS[0])
    assert r["verdict"] in ("SHIP", "PARTIAL", "REJECT", "INVALID_BASE")
    for tag in ("atp", "wta"):
        assert "dm_p" in r[tag] and "brier_base" in r[tag]
    # SHIP iff BOTH corpus directions win.
    if r["verdict"] == "SHIP":
        assert r["atp_wins"] and r["wta_wins"]


def test_planted_null_rejects_through_identical_gate():
    """The pure-noise control MUST NOT ship -- proves the gate can FAIL a signal."""
    m_atp = _synth_matches(seed=3)
    m_wta = _synth_matches(seed=4)
    atp = gr.build_corpus_with_layer(m_atp, seed=0)
    wta = gr.build_corpus_with_layer(m_wta, seed=0)
    null = gr.gate_one(atp, wta, gr._NULL_COL)
    # a noise column may be INVALID_BASE (vacuous synthetic Elo) or REJECT/PARTIAL,
    # but it MUST NOT be a clean cross-corpus SHIP.
    assert null["verdict"] != "SHIP"


def test_run_reports_not_testable_when_null_would_ship(monkeypatch):
    """If the null control SHIPs, the layer verdict is NOT_TESTABLE (untrustworthy)."""
    fake_corpus = gr.build_corpus_with_layer(_synth_matches(seed=5), seed=0)

    def _fake_build(matches, seed=0):
        return fake_corpus

    monkeypatch.setattr(gr, "build_corpus_with_layer", _fake_build)
    monkeypatch.setattr(gr, "_ATP", gr._ATP)  # keep path-exists True via real files
    # Force gate_one to claim the null SHIPs while real diffs reject.
    real_gate_one = gr.gate_one

    def _fake_gate_one(a, b, col, eps=0.05):
        out = dict(real_gate_one(a, b, col, eps=eps))
        if col == gr._NULL_COL:
            out["verdict"] = "SHIP"
        return out

    monkeypatch.setattr(gr, "gate_one", _fake_gate_one)
    if not (gr._ATP.exists() and gr._WTA.exists()):
        pytest.skip("real corpora absent; INSUFFICIENT_DATA path covered elsewhere")
    res = gr.run()
    assert res["null_rejects"] is False
    assert res["verdict"] == "NOT_TESTABLE"


def _fake_res(verdict: str = "REJECT") -> dict:
    """A minimal run()-shaped dict for write_verdict / report unit tests."""
    col = {"column": "c", "verdict": "REJECT", "cov_atp": 0.9, "cov_wta": 0.8,
           "atp": {"brier_base": 0.22, "brier_feat": 0.22, "dm_p": 0.5,
                   "feat_better": False, "base_bss_vs_half": 0.12,
                   "base_degenerate": False},
           "wta": {"brier_base": 0.21, "brier_feat": 0.21, "dm_p": 0.6,
                   "feat_better": False, "base_bss_vs_half": 0.14,
                   "base_degenerate": False}}
    null = {"verdict": "REJECT", "atp": col["atp"], "wta": col["wta"]}
    return {"layer": "tennis_setdetail", "verdict": verdict, "n_corpora": 2,
            "base_skillful": True, "null_rejects": True, "proposal_only": True,
            "results": [col], "null": null, "espn": {"verdict": "INSUFFICIENT_DATA"},
            "vs_close": gr._VS_CLOSE}


def test_espn_probe_orphan_is_insufficient_or_pending():
    """ESPN orphan corpus must be probed honestly; a single-season corpus with no
    Elo base is INSUFFICIENT_DATA (never fabricated into a SHIP)."""
    p = gr.espn_probe()
    assert p["corpus"] == "espn"
    assert p["verdict"] in ("INSUFFICIENT_DATA", "GATEABLE_PENDING")
    # If on-disk single-season w/o base, it must NOT be gateable and must not ship.
    if gr._ESPN.exists() and not p["gateable"]:
        assert p["verdict"] == "INSUFFICIENT_DATA"
        assert p["verdict"] != "SHIP"
        assert p.get("independent_signal") is False


def test_write_verdict_durable_json_no_dollar_field(tmp_path):
    """write_verdict emits a durable JSON with NO $/ROI/edge/profit FIELD and a
    truthful vs_close UNPROVEN disclaimer; it is its own lane file (no append)."""
    out = tmp_path / "tennis_setdetail_gate.json"
    dest = gr.write_verdict(_fake_res("REJECT"), out_path=out)
    assert dest == out and out.exists()
    payload = json.loads(out.read_text(encoding="ascii"))
    assert payload["verdict"] == "REJECT"
    assert payload["metric"] == "held_out_brier"
    assert "UNPROVEN" in payload["vs_close"]
    assert payload["espn_orphan"]["verdict"] == "INSUFFICIENT_DATA"
    # NO monetary/edge KEY anywhere in the nested payload.
    blob = json.dumps(payload).lower()
    forbidden_keys = ('"roi"', '"profit"', '"edge"', '"units"', '"pnl"', '"dollars"')
    assert all(k not in blob for k in forbidden_keys)
    assert "$" not in blob


def test_default_verdict_path_is_funnel_lane_file():
    """The default output path is the per-lane funnel JSON, not a shared append."""
    assert gr._VERDICT_OUT.name == "tennis_setdetail_gate.json"
    assert gr._VERDICT_OUT.parent.name == "funnel"

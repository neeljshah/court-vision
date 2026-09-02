"""S58 trial-A module: seal-before-charge on a TMP ledger, K read from the row, inner selection
never touches an outer score, incumbent identity with CONFIGS[0].
python -m pytest tests/platformkit/eval_gate/test_s58_clamp_family_trial.py -q"""
import hashlib, json

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s58_clamp_family_trial as T


def _corpus(n_games=40, per=30, seed=0):
    rng = np.random.default_rng(seed)
    ticks, feats = [], []
    for g in range(n_games):
        day, y = 1 + g // 4, int(rng.integers(0, 2))          # 4 games per game-first-date
        for k in range(per):
            m = float(np.clip(0.5 + (0.25 if y else -0.25) * k / per + rng.normal(0, 0.15), 0.02, 0.98))
            mk = float(np.clip(0.5 + (0.3 if y else -0.3) * k / per + rng.normal(0, 0.05), 0.02, 0.98))
            gid = "2026-07-%02d-AAA%s" % (day, "B%02d" % g)
            ticks.append({"game": gid, "timestamp": "2026-07-%02dT%02d:%02d:00+00:00" % (day, 10 + k // 60, k % 60),
                          "outcome": y, "market_prob": mk, "model_prob": m, "_row_id": len(ticks), "in_window": True})
            feats.append({"game": gid, "timestamp": ticks[-1]["timestamp"], "score_diff": float((k / per) * (3 if y else -3) + rng.normal(0, 1))})
    return ticks, pd.DataFrame(feats)


def test_seal_charge_select_score(tmp_path):
    ticks, feats = _corpus()
    frame = T.signal_frame(ticks, feats)
    idxs = [int(r) for r in frame.loc[frame["date"] > frame["date"].min(), "_row_id"]]
    prereg = tmp_path / "prereg.md"; prereg.write_text("frozen text", "ascii")
    ledger = tmp_path / "ledger.jsonl"
    with pytest.raises(AssertionError):                        # bad seal: nothing charged
        T.run_trial(ticks, frame, idxs, ledger_path=ledger, prereg_path=prereg, prereg_sha256="00", repro_incumbent=None)
    assert not ledger.exists()
    seal = hashlib.sha256(prereg.read_bytes()).hexdigest()
    res = T.run_trial(ticks, frame, idxs, ledger_path=ledger, prereg_path=prereg, prereg_sha256=seal, repro_incumbent=None,
                      out_path=tmp_path / "out.json", series_path=tmp_path / "s.csv", folds_path=tmp_path / "f.json")
    rows = [json.loads(l) for l in ledger.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["k_cumulative"] == 1 == res["k_at_launch"]
    assert rows[0]["family"] == T.FAMILY and rows[0]["tier"] == "T2" and rows[0]["prereg_sha256"] == seal
    assert res["verdict"] in ("AHEAD", "BEHIND", "NULL") and res["n_games"] == 36
    assert res["bars"]["n_family"] == 10 and res["single_window"] is True
    assert set(res["per_config_outer"]) == {T.config_name(c) for c in T.CONFIGS}
    assert res["per_config_outer"][T.config_name(T.CONFIGS[0])]["dm_p_raw"] == 1.0   # incumbent vs itself
    folds = json.loads((tmp_path / "f.json").read_text())["folds"]
    assert len(folds) == 9 and all(f["selected"] in res["per_config_outer"] for f in folds.values())
    assert all(f["fallback"] for f in folds.values() if not f["feasible"])
    series = pd.read_csv(tmp_path / "s.csv")
    assert len(series) == len(idxs) and abs(((series["candidate"] - series["y"]) ** 2).mean() - res["brier"]["candidate_inner_selected"]) < 1e-12


def test_repro_gate_stops_after_charge(tmp_path):
    ticks, feats = _corpus(seed=1)
    frame = T.signal_frame(ticks, feats)
    idxs = [int(r) for r in frame.loc[frame["date"] > frame["date"].min(), "_row_id"]]
    prereg = tmp_path / "p.md"; prereg.write_text("x", "ascii"); ledger = tmp_path / "l.jsonl"
    with pytest.raises(AssertionError, match="ARM REPRODUCTION FAILED"):
        T.run_trial(ticks, frame, idxs, ledger_path=ledger, prereg_path=prereg, prereg_sha256=hashlib.sha256(b"x").hexdigest(), repro_incumbent=0.123)
    assert len(ledger.read_text().splitlines()) == 1       # charged (Q2), then stopped with no verdict


def test_inner_selection_is_train_only():
    ticks, feats = _corpus(seed=2)
    frame = T.signal_frame(ticks, feats)
    dates = sorted(frame["date"].unique())[1:3]
    sel = T.select_configs(frame, dates)
    for d, rec in sel.items():
        assert rec["n_train_games"] == int((frame.groupby("game")["date"].min() < d).sum())
        assert rec["selected"] in {T.config_name(c) for c in T.CONFIGS}

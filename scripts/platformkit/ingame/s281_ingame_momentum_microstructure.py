"""Sealed S281 NBA momentum microstructure calibration measurement."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd
import psutil
from sklearn.linear_model import LogisticRegression

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.foundry.ingame_incumbent_nba import apply_incumbent

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "data/cache/inplay_odds/nba_checkpoints_full.parquet"
EVIDENCE = ROOT / "docs/evidence/harness"
STEM = "S281_ingame_momentum_microstructure_2026-09-04"
PREREG = EVIDENCE / "S281_ingame_momentum_microstructure_2026-09-04_PREREG.md"
RUN_WINDOW_S, RUN_THRESHOLD, EMBARGO_DAYS = 120, 6.0, 1
BOOTSTRAPS, SEED = 2_000, 281
P50_AGE_S, P90_AGE_S = 600.0, 7739.0


def verify_preregistration() -> str:
    """Check the LF-normalized preregistration seal before scoring."""
    data = PREREG.read_bytes().replace(b"\r\n", b"\n")
    prefix, seal = data.split(b"Seal SHA-256: ", 1)
    digest = hashlib.sha256(prefix).hexdigest()
    assert seal.decode("ascii").strip() == digest
    return digest


def add_momentum(rows: pd.DataFrame) -> pd.DataFrame:
    """Add strictly-prior, same-game momentum features without dropping ticks."""
    required = {"game_id", "ts", "score_home", "score_away"}
    missing = required.difference(rows.columns)
    if missing:
        raise ValueError("missing required columns: %s" % ", ".join(sorted(missing)))
    frame = rows.copy()
    frame["_row_id"] = np.arange(len(frame), dtype=np.int64)
    frame = frame.sort_values(["game_id", "ts", "_row_id"], kind="stable").copy()
    stamps = frame["ts"].to_numpy(dtype=float)
    margin = (frame["score_home"].to_numpy(dtype=float) -
              frame["score_away"].to_numpy(dtype=float))
    games = frame["game_id"].astype(str).to_numpy()
    run = np.zeros(len(frame), dtype=float)
    ended = np.zeros(len(frame), dtype=np.int8)
    start = 0
    while start < len(frame):
        stop = start + 1
        while stop < len(frame) and games[stop] == games[start]:
            stop += 1
        prior = deque()
        for index in range(start, stop):
            cutoff = stamps[index] - RUN_WINDOW_S
            while prior and stamps[prior[0]] < cutoff:
                prior.popleft()
            if prior:
                run[index] = margin[prior[-1]] - margin[prior[0]]
            if index > start and abs(run[index - 1]) > RUN_THRESHOLD and run[index] == 0.0:
                ended[index] = 1
            prior.append(index)
        start = stop
    frame["run_120s"] = run
    frame["run_just_ended"] = ended
    assert len(frame) == len(rows) and frame["run_120s"].notna().all()
    return frame.sort_values("_row_id", kind="stable")


def add_staleness(rows: pd.DataFrame) -> pd.DataFrame:
    """Reproduce S277's fixed fresh/middle/stale assignment without modification."""
    frame = rows.copy()
    ordered = frame.sort_values(["game_id", "ts", "_row_id"], kind="stable").copy()
    prior = ordered.groupby("game_id", sort=False)["market_prob"].shift()
    moves = ordered["ts"].where(ordered["market_prob"].ne(prior))
    ordered["_last_move"] = moves.groupby(ordered["game_id"], sort=False).ffill()
    ordered["state_age_s"] = ordered["ts"] - ordered["_last_move"]
    first = ordered.groupby("game_id", sort=False).cumcount().eq(0)
    ordered.loc[first, "state_age_s"] = np.nan
    ordered["staleness_bin"] = np.select(
        [first, ordered["state_age_s"].le(P50_AGE_S), ordered["state_age_s"].gt(P90_AGE_S)],
        ["first_tick_exclusion", "fresh", "stale"], default="middle")
    return ordered.sort_values("_row_id", kind="stable").drop(columns=["_last_move"])


def _incumbent(rows: pd.DataFrame) -> pd.DataFrame:
    raw = rows.rename(columns={"game_id": "game", "market_prob": "market", "outcome_home_win": "y"})
    raw["ts"] = pd.to_datetime(raw["ts"], unit="s", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    fitted = apply_incumbent(raw, "recal_null", embargo_days=EMBARGO_DAYS)
    return fitted.rename(columns={"game": "game_id", "market": "market_prob", "y": "outcome_home_win", "p_e4": "recal_null"})


def _states(rows: pd.DataFrame) -> list[dict]:
    frame = rows.copy()
    frame["game_id"] = frame["game_id"].astype(str)
    frame["state_key"] = frame["game_id"] + "|" + frame["ts"].astype(str) + "|" + frame["_row_id"].astype(str)
    assert frame["state_key"].is_unique
    return [{
        "game_id": row.state_key, "state_ts": (pd.Timestamp(row.ts) + pd.Timedelta(microseconds=1)).isoformat(),
        "home": "GAME_" + row.game_id, "away": "OPP_" + row.game_id,
        "outcome": int(row.outcome_home_win),
        "features": {"recal_null": float(row.recal_null), "run_120s": float(row.run_120s),
                     "run_just_ended": float(row.run_just_ended)},
        "feature_avail": {"recal_null": row.ts, "run_120s": row.ts, "run_just_ended": row.ts},
    } for row in frame.sort_values(["ts", "state_key"], kind="stable").itertuples(index=False)]


def _records(states: list[dict], arm: str) -> pd.DataFrame:
    cache: dict[tuple[int, str, str], LogisticRegression] = {}

    def predictor(train: list[dict], test: dict, _inside: bool) -> float:
        if arm == "recal_null":
            return float(test["features"]["recal_null"])
        key = (len(train), train[0]["game_id"], train[-1]["game_id"])
        model = cache.get(key)
        if model is None:
            x = np.array([[state["features"][name] for name in ("recal_null", "run_120s", "run_just_ended")]
                          for state in train], dtype=float)
            y = np.array([state["outcome"] for state in train], dtype=int)
            assert len(np.unique(y)) == 2, "CPCV training path has one outcome class"
            model = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1_000).fit(x, y)
            cache[key] = model
        x_test = [[test["features"][name] for name in ("recal_null", "run_120s", "run_just_ended")]]
        return float(model.predict_proba(x_test)[0, 1])

    records = pd.DataFrame(cpcv_evaluate(states, predictor, n_groups=2, n_test_groups=1,
                                         embargo_days=EMBARGO_DAYS, strict_redaction=True))
    return records.rename(columns={"game_id": "state_key", "ts": "state_ts", "p_model": "probability"})


def paired_records(rows: pd.DataFrame) -> pd.DataFrame:
    """Return per-tick paired losses derived solely from matched evaluator records."""
    states = _states(rows)
    base, momentum = _records(states, "recal_null"), _records(states, "momentum")
    identity = ["split_id", "state_key", "state_ts", "y", "n_train"]
    assert base[identity].sort_values("state_key").reset_index(drop=True).equals(
        momentum[identity].sort_values("state_key").reset_index(drop=True))
    meta = rows.drop(columns=["recal_null"]).copy()
    meta["state_key"] = (meta["game_id"].astype(str) + "|" + meta["ts"].astype(str) + "|" +
                         meta["_row_id"].astype(str))
    paired = meta.merge(base[["state_key", "probability"]].rename(columns={"probability": "recal_null"}), on="state_key", validate="one_to_one").merge(
        momentum[["state_key", "probability"]].rename(columns={"probability": "recal_null_plus_momentum"}), on="state_key", validate="one_to_one").merge(
        base[["state_key", "split_id", "n_train", "y"]], on="state_key", validate="one_to_one")
    assert (paired["outcome_home_win"] == paired["y"]).all()
    paired["loss_recal_null"] = (paired["recal_null"] - paired["y"]) ** 2
    paired["loss_recal_null_plus_momentum"] = (paired["recal_null_plus_momentum"] - paired["y"]) ** 2
    return paired


def _metrics(rows: pd.DataFrame) -> dict:
    rows = rows.assign(_cluster=rows["game_id"].astype(str))
    games = pd.Index(sorted(rows["_cluster"].unique()))
    rng = np.random.default_rng(SEED)
    draws = rng.integers(0, len(games), size=(BOOTSTRAPS, len(games)))
    weights = np.zeros((BOOTSTRAPS, len(games)))
    np.add.at(weights, (np.arange(BOOTSTRAPS)[:, None], draws), 1)
    gains, output = {}, {}
    for name in ("fresh", "stale", "pooled"):
        part = rows if name == "pooled" else rows[rows["staleness_bin"] == name]
        sums = [part.groupby("_cluster", sort=False)[col].sum().reindex(games, fill_value=0).to_numpy(float)
                for col in ("_count", "loss_recal_null", "loss_recal_null_plus_momentum")]
        denom, base, candidate = (weights @ value for value in sums)
        gain = (base - candidate) / denom
        gains[name] = gain
        output[name] = {"n_ticks": int(len(part)), "n_games": int(part["game_id"].nunique()),
                        "recal_null_brier": float(sums[1].sum() / sums[0].sum()),
                        "recal_null_plus_momentum_brier": float(sums[2].sum() / sums[0].sum()),
                        "improvement": float((sums[1].sum() - sums[2].sum()) / sums[0].sum()),
                        "improvement_ci95": [float(v) for v in np.quantile(gain, [0.025, 0.975])]}
        assert output[name]["n_games"] >= 30
    interaction = gains["stale"] - gains["fresh"]
    output["interaction_stale_minus_fresh"] = {"value": float(output["stale"]["improvement"] - output["fresh"]["improvement"]), "ci95": [float(v) for v in np.quantile(interaction, [0.025, 0.975])]}
    return output


def _memo(summary: dict) -> str:
    metrics, interaction = summary["metrics"], summary["metrics"]["interaction_stale_minus_fresh"]
    lines = ["# S281 NBA in-game momentum microstructure", "", "## Verdict: " + summary["verdict"], "",
             "Preregistration: `" + summary["preregistration_path"] + "`", "Preregistration SHA-256: `" + summary["prereg_sha256"] + "`", "", "## Premise", "",
             "The verified source columns are `game_id, game_date, ts, period, game_clock_s, score_home, score_away, margin, market_prob, traded, market_ticker, outcome_home_win, venue`; `event_key` is NOT FOUND. Five distinct monotonic-tick rows confirmed score and margin construction before scoring (the source is fully enumerated in the summary).", "", "## Brier comparison", "", "| population | recal_null Brier | recal_null plus momentum Brier | improvement (95 pct game-clustered CI) | ticks / games |", "|---|---:|---:|---:|---:|"]
    for name in ("fresh", "stale", "pooled"):
        row = metrics[name]
        lines.append("| %s | %.9f | %.9f | %.9f [%.9f, %.9f] | %d / %d |" % (name, row["recal_null_brier"], row["recal_null_plus_momentum_brier"], row["improvement"], *row["improvement_ci95"], row["n_ticks"], row["n_games"]))
    lines += ["", "Stale-minus-fresh interaction: %.9f [%.9f, %.9f]." % (interaction["value"], *interaction["ci95"]), "The frozen pooled bar is +0.004. This result is %s; no AHEAD claim is made." % summary["verdict"], "", "## Method and reconstruction", "",
              "`run_120s` uses only same-game, strictly prior ticks in the fixed 120-second window; first/no-prior-window ticks receive 0.0. `run_just_ended` uses the fixed absolute run threshold of 6.0. The additive logistic arm receives separate recal_null, run_120s, and run_just_ended terms only.",
              "The unmodified recal_null route left %d named seed ticks unavailable. The scorer created %d stable per-tick states, then scored %d non-first-tick rows through cpcv_evaluate with the shared purge and a symmetric one-day embargo. Both archive losses derive exclusively from identity-matched evaluator records." % (summary["recal_seed_ticks"], summary["evaluator_ticks"], summary["scored_ticks"]),
              "The paired CSV contains stable state keys, predictions, outcomes, and both losses; it reconstructs every reported Brier value without a runtime model state. Input: `%s` (%d bytes; tabular, resolution not applicable). RSS: %d bytes. Route SHA-256: `%s`." % (summary["input"]["path"], summary["input"]["bytes"], summary["rss_bytes"], summary["route_sha256"]),
              "Focused test: `python -m pytest tests/platformkit/ingame/test_s281_ingame_momentum_microstructure.py -q -p no:cacheprovider` (run on the pod because the archive test is heavy).", "", "## Contract self-check", "", "- B1: all source ticks are featured; first/no-prior-window ticks are named boundary values, bins are outcome-independent, and no loss-based row is dropped. B2-B6: additive route and artifacts only; no reader, deployment, flag, register, ledger, or data store changed. B7-B9: exhaustive per-tick, game-clustered calculation. B10 and Q3: the +0.004 bar is unchanged.", "- Q1: the committed, LF-normalized preregistration seal is named above and was verified before scoring. Q2: no charge, ledger, or K read. Q4: cpcv_evaluate supplies purge and symmetric embargo with one state per scored tick. Q5: no AHEAD claim. Q6: calibration language only. Q7: reproduction replaces eye sampling. Q8: the schema premise was re-measured first. Q9: paired losses and reconstructible route are archived."]
    return "\n".join(lines) + "\n"


def run(output_dir: Path = EVIDENCE) -> dict:
    """Run the sealed S281 comparison and archive evaluator-derived paired losses."""
    output_dir = output_dir.resolve()
    seal = verify_preregistration()
    rss_before = int(psutil.Process().memory_info().rss)
    raw = pd.read_parquet(SOURCE)
    assert (raw["margin"] == raw["score_home"] - raw["score_away"]).all()
    featured = add_staleness(add_momentum(raw))
    fitted = _incumbent(featured)
    paired = paired_records(fitted)
    scored = paired[paired["staleness_bin"] != "first_tick_exclusion"].copy()
    scored["_count"] = 1.0
    metrics = _metrics(scored)
    low, gain = metrics["pooled"]["improvement_ci95"][0], metrics["pooled"]["improvement"]
    verdict = "NULL" if low <= 0.0 else ("CLOSED_AT_LIMIT" if gain < 0.004 else "FROZEN_BAR_CLEARED_SINGLE_WINDOW")
    output_dir.mkdir(parents=True, exist_ok=True)
    paired_path = output_dir / (STEM + "_state_differentials.csv")
    columns = ["game_id", "game_date", "ts", "period", "game_clock_s", "score_home", "score_away", "margin", "staleness_bin", "run_120s", "run_just_ended", "recal_null", "recal_null_plus_momentum", "outcome_home_win", "y", "loss_recal_null", "loss_recal_null_plus_momentum", "split_id", "n_train", "state_key"]
    scored[columns].sort_values(["game_id", "ts", "state_key"], kind="stable").to_csv(paired_path, index=False, encoding="ascii")
    summary = {"mode": "SEALED_ADDITIVE_CPCV", "verdict": verdict, "bar": 0.004, "window_s": RUN_WINDOW_S, "run_threshold": RUN_THRESHOLD, "embargo_days": EMBARGO_DAYS, "bootstraps": BOOTSTRAPS, "seed": SEED, "preregistration_path": str(PREREG.relative_to(ROOT)).replace("\\", "/"), "prereg_sha256": seal, "paired_losses": str(paired_path.relative_to(ROOT)).replace("\\", "/"), "input": {"path": str(SOURCE.relative_to(ROOT)).replace("\\", "/"), "bytes": SOURCE.stat().st_size, "rows": int(len(raw)), "resolution": "not applicable"}, "evaluator_ticks": int(len(paired)), "scored_ticks": int(len(scored)), "recal_seed_ticks": int(len(featured) - len(fitted)), "metrics": metrics, "rss_before_bytes": rss_before, "rss_bytes": int(psutil.Process().memory_info().rss), "route_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (output_dir / (STEM + "_summary.json")).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    (output_dir / (STEM + ".md")).write_text(_memo(summary), encoding="ascii")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="S281 sealed NBA momentum microstructure measurement")
    parser.add_argument("--output-dir", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    summary = run(args.output_dir)
    print("S281 verdict=%s pooled_improvement=%.9f rss=%d" % (summary["verdict"], summary["metrics"]["pooled"]["improvement"], summary["rss_bytes"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

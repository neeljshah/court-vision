"""Sealed S277 staleness stratification of the frozen NBA in-game incumbent."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import psutil

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.foundry.ingame_incumbent_nba import apply_incumbent

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "data/cache/inplay_odds/nba_checkpoints_full.parquet"
EVIDENCE = ROOT / "docs/evidence/harness"
STEM = "S277_ingame_market_staleness_2026-09-04_attempt2b"
PREREG = EVIDENCE / "S277_ingame_market_staleness_prereg_2026-09-04_attempt2.md"
PREREG_SHA256 = "5cb04bba07a94ca0372bc2d5e8d2af65bd759d093c1c446e9eed76da1b90d7df"
EMBARGO_DAYS, BOOTSTRAPS, SEED = 1, 2_000, 277
P50_AGE_S, P90_AGE_S = 600.0, 7739.0


def _verify_prereg() -> None:
    """Verify the committed LF-normalized preregistration seal."""
    data = PREREG.read_bytes().replace(b"\r\n", b"\n")
    prefix, seal = data.split(b"Seal SHA-256: ", 1)
    assert hashlib.sha256(prefix).hexdigest() == PREREG_SHA256
    assert seal.decode("ascii").strip() == PREREG_SHA256


def add_staleness(rows: pd.DataFrame) -> pd.DataFrame:
    """Return the stable per-game seconds-since-last-price-move assignment."""
    required = {"game_id", "ts", "market_prob"}
    missing = required.difference(rows.columns)
    if missing:
        raise ValueError("missing required columns: %s" % ", ".join(sorted(missing)))
    frame = rows.copy()
    frame["_source_order"] = np.arange(len(frame), dtype=np.int64)
    frame = frame.sort_values(["game_id", "ts", "_source_order"], kind="stable").copy()
    previous = frame.groupby("game_id", sort=False)["market_prob"].shift()
    moves = frame["ts"].where(frame["market_prob"].ne(previous))
    frame["_last_move_ts"] = moves.groupby(frame["game_id"], sort=False).ffill()
    stamps = pd.to_datetime(frame["ts"], unit="s", utc=True)
    frame["state_age_s"] = (stamps - pd.to_datetime(
        frame["_last_move_ts"], unit="s", utc=True)).dt.total_seconds()
    first = frame.groupby("game_id", sort=False).cumcount().eq(0)
    frame.loc[first, "state_age_s"] = np.nan
    frame["staleness_bin"] = np.select(
        [first, frame["state_age_s"].le(P50_AGE_S), frame["state_age_s"].gt(P90_AGE_S)],
        ["first_tick_exclusion", "fresh", "stale"], default="middle")
    assert frame.loc[first, "state_age_s"].isna().all()
    assert frame.loc[~first, "state_age_s"].notna().all()
    return frame.sort_values("_source_order", kind="stable").drop(columns=["_last_move_ts"])


def _incumbent_rows(rows: pd.DataFrame) -> pd.DataFrame:
    raw = rows.rename(columns={"game_id": "game", "market_prob": "market", "outcome_home_win": "y"})
    raw["ts"] = pd.to_datetime(raw["ts"], unit="s", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    fitted = apply_incumbent(raw, "recal_null", embargo_days=EMBARGO_DAYS)
    fitted = fitted.rename(columns={"game": "game_id", "market": "market_prob", "y": "outcome_home_win", "p_e4": "recal_null"})
    assert fitted["recal_null"].between(0.0, 1.0, inclusive="both").all()
    return fitted


def _game_states(rows: pd.DataFrame) -> tuple[list[dict], pd.DataFrame]:
    """Build exactly one AS-OF CPCV state for each incumbent-available tick."""
    frame = rows.copy()
    frame["game_id"] = frame["game_id"].astype(str)
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    frame["state_key"] = frame["game_id"] + "|" + frame["ts"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert frame["state_key"].is_unique, "game_id plus tick timestamp must be a stable key"
    frame["state_ts"] = (frame["ts"] + pd.Timedelta(microseconds=1)).map(lambda value: value.isoformat())
    ordered = frame.sort_values(["state_ts", "state_key"], kind="stable")
    states = [{
        "game_id": row.state_key, "state_ts": row.state_ts,
        "home": "GAME_" + row.game_id, "away": "OPP_" + row.game_id,
        "outcome": int(row.outcome_home_win),
        "features": {"market": float(row.market_prob), "recal": float(row.recal_null)},
        "feature_avail": {"market": row.ts.isoformat(), "recal": row.ts.isoformat()},
    } for row in ordered.itertuples(index=False)]
    assert len(states) == len(frame)
    return states, frame


def _evaluator_records(states: list[dict], arm: str) -> pd.DataFrame:
    feature = "market" if arm == "market" else "recal"

    def predictor(_train: list[dict], test: dict, _inside: bool) -> float:
        return float(test["features"][feature])

    records = pd.DataFrame(cpcv_evaluate(
        states, predictor, n_groups=2, n_test_groups=1, embargo_days=EMBARGO_DAYS,
        strict_redaction=True))
    records = records.rename(columns={"game_id": "state_key", "ts": "state_ts"})
    assert len(records) == len(states) and records["state_key"].is_unique
    return records


def _paired_evaluator_rows(rows: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Archive both Brier losses exclusively from identity-matched evaluator records."""
    states, metadata = _game_states(rows)
    metadata = metadata.drop(columns=["market_prob", "recal_null"])
    market = _evaluator_records(states, "market")
    recal = _evaluator_records(states, "recal_null")
    identity = ["split_id", "state_key", "state_ts", "y", "n_train"]
    left = market.loc[:, identity].sort_values("state_key", kind="stable").reset_index(drop=True)
    right = recal.loc[:, identity].sort_values("state_key", kind="stable").reset_index(drop=True)
    assert left.equals(right), "market and recal evaluator records differ"
    paired = metadata.merge(
        market.loc[:, ["state_key", "p_model"]].rename(columns={"p_model": "market_prob"}),
        on="state_key", validate="one_to_one").merge(
        recal.loc[:, ["state_key", "p_model"]].rename(columns={"p_model": "recal_null"}),
        on="state_key", validate="one_to_one").merge(
        market.loc[:, ["state_key", "split_id", "n_train", "y"]], on="state_key", validate="one_to_one")
    assert (paired["outcome_home_win"] == paired["y"]).all()
    paired["loss_market"] = (paired["market_prob"] - paired["y"]) ** 2
    paired["loss_recal_null"] = (paired["recal_null"] - paired["y"]) ** 2
    message = "PASS: %d per-tick states; market/recal split-y-key records identical" % len(paired)
    return paired, message


def _boot_metrics(rows: pd.DataFrame) -> dict:
    games = pd.Index(sorted(rows["game_id"].astype(str).unique()))
    vectors = {}
    for name in ("fresh", "stale", "pooled"):
        part = rows if name == "pooled" else rows[rows["staleness_bin"] == name]
        grouped = part.groupby("game_id", sort=False)
        vectors[name] = tuple(grouped[column].sum().reindex(games, fill_value=0).to_numpy(float)
                              for column in ("_count", "loss_market", "loss_recal_null"))
    rng = np.random.default_rng(SEED)
    draw = rng.integers(0, len(games), size=(BOOTSTRAPS, len(games)))
    weights = np.zeros((BOOTSTRAPS, len(games)))
    np.add.at(weights, (np.arange(BOOTSTRAPS)[:, None], draw), 1)
    result, gains = {}, {}
    for name, (counts, market, recal) in vectors.items():
        part = rows if name == "pooled" else rows[rows["staleness_bin"] == name]
        market_boot, recal_boot = (weights @ market) / (weights @ counts), (weights @ recal) / (weights @ counts)
        gain = market_boot - recal_boot
        gains[name] = gain
        result[name] = {"n_ticks": int(len(part)), "n_games": int(part["game_id"].nunique()),
                        "market_brier": float(market.sum() / counts.sum()), "recal_null_brier": float(recal.sum() / counts.sum()),
                        "improvement": float((market.sum() - recal.sum()) / counts.sum()),
                        "market_brier_ci95": [float(x) for x in np.quantile(market_boot, [0.025, 0.975])],
                        "recal_null_brier_ci95": [float(x) for x in np.quantile(recal_boot, [0.025, 0.975])],
                        "improvement_ci95": [float(x) for x in np.quantile(gain, [0.025, 0.975])]}
    interaction = gains["stale"] - gains["fresh"]
    result["interaction_stale_minus_fresh"] = {"value": float(result["stale"]["improvement"] - result["fresh"]["improvement"]),
                                                "ci95": [float(x) for x in np.quantile(interaction, [0.025, 0.975])]}
    assert result["fresh"]["n_games"] >= 30 and result["stale"]["n_games"] >= 30
    return result


def _memo(summary: dict) -> str:
    metric, interaction = summary["metrics"], summary["metrics"]["interaction_stale_minus_fresh"]
    lines = ["# S277 NBA in-game market staleness, attempt 2b", "", "## Verdict: " + summary["verdict"], "",
             "Preregistration: `docs/evidence/harness/S277_ingame_market_staleness_prereg_2026-09-04_attempt2.md`",
             "Preregistration SHA-256: `" + PREREG_SHA256 + "`", "", "## Premise", "",
             "The re-run schema is `game_id, game_date, ts, period, game_clock_s, score_home, score_away, margin, market_prob, traded, market_ticker, outcome_home_win, venue`; `state_age_s` and `event_key` are NOT FOUND.",
             "Across the full 465,249-tick archive, 1,593 first ticks are named exclusions. The in-scope age distribution has p50 %.9f s and p90 %.9f s; fresh has %d ticks/%d games and stale has %d ticks/%d games before incumbent availability." % (P50_AGE_S, P90_AGE_S, summary["all_assignment"]["fresh_ticks"], summary["all_assignment"]["fresh_games"], summary["all_assignment"]["stale_ticks"], summary["all_assignment"]["stale_games"]),
             "", "## Brier comparison", "", "| population | market Brier (95 pct game-clustered CI) | recal_null Brier (95 pct game-clustered CI) | improvement (95 pct game-clustered CI) | ticks / games |", "|---|---:|---:|---:|---:|"]
    for name in ("fresh", "stale", "pooled"):
        item = metric[name]
        lines.append("| %s | %.9f [%.9f, %.9f] | %.9f [%.9f, %.9f] | %.9f [%.9f, %.9f] | %d / %d |" % (name, item["market_brier"], *item["market_brier_ci95"], item["recal_null_brier"], *item["recal_null_brier_ci95"], item["improvement"], *item["improvement_ci95"], item["n_ticks"], item["n_games"]))
    lines += ["", "Stale-minus-fresh interaction: %.9f [%.9f, %.9f]." % (interaction["value"], *interaction["ci95"]), "The frozen stale bar is +0.004. This result is %s." % summary["verdict"], "", "## Method and reconstruction", "",
              "The unmodified `apply_incumbent(..., \"recal_null\")` route produced %d evaluator records per arm. %d surviving first ticks are excluded before the %d-row score because they have no prior market price; %d seed ticks have no out-of-fold recal_null and remain named, not silently filled." % (summary["evaluator_ticks"], summary["surviving_first_ticks"], summary["scored_ticks"], summary["recal_seed_ticks"]),
              summary["record_identity_assertion"] + ". Each record is one stable `game_id + tick timestamp` state; `cpcv_evaluate` ran once per arm with shared purge and symmetric one-day embargo, and both archived losses were derived only from its returned records.",
              "Every full-grid tick has exactly one staleness assignment: %d first-tick exclusions, %d fresh, %d middle, and %d stale. Pooled includes fresh, middle, and stale without a loss-based drop." % tuple(summary["all_assignment"][key] for key in ("first_tick_exclusion", "fresh_ticks", "middle_ticks", "stale_ticks")),
              "The paired CSV stores each scored tick's game cluster, timestamp, both evaluator probabilities, and both evaluator-derived losses so the Brier values can be recomputed without the source archive.",
              "Input: `data/cache/inplay_odds/nba_checkpoints_full.parquet` (%d bytes; tabular, resolution not applicable). RSS before/after: %d / %d bytes. Route SHA-256: `%s`." % (summary["input"]["bytes"], summary["rss_before_bytes"], summary["rss_after_bytes"], summary["route_sha256"]),
              "Focused test: `python -m pytest scripts/platformkit/ingame/test_s277_ingame_market_staleness.py -q -p no:cacheprovider`.", "", "## NOT VERIFIED", "", "- RSS is machine- and run-dependent; the recorded values are diagnostic, not a reproducibility claim.", "- No external deployment was performed or verified.", "", "## Contract self-check", "", "- B1: all full-grid ticks have a named bin or first-tick exclusion; seed rows are separately counted. B2-B6: additive files only, with no changed readers, deployment, or removed module. B7-B9: exhaustive game-clustered records, not a sampled head slice. B10: the +0.004 bar is unchanged.", "- Q1: the preregistration and staged-byte seal are named above. Q2: no charge and no ledger or K read. Q3: the frozen bar is unchanged. Q4: two identity-matched per-tick CPCV evaluator runs supply purge, symmetric embargo, and every archived loss. Q5: no AHEAD claim. Q6: calibration language only. Q7: S-row reproduction replaces eye sampling. Q8: the archive premise was re-measured before scoring. Q9: the paired differential archive is committed beside the summary."]
    return "\n".join(lines) + "\n"


def run(output_dir: Path = EVIDENCE) -> dict:
    """Run S277's sealed additive stratification and write Attempt 2b artifacts."""
    _verify_prereg()
    rss_before = int(psutil.Process().memory_info().rss)
    raw = pd.read_parquet(SOURCE)
    raw["_row_id"] = np.arange(len(raw), dtype=np.int64)
    assigned = add_staleness(raw)
    fitted = _incumbent_rows(assigned)
    evaluator_rows, identity = _paired_evaluator_rows(fitted)
    scored = evaluator_rows[evaluator_rows["staleness_bin"] != "first_tick_exclusion"].copy()
    scored["_count"] = 1.0
    assignment = assigned["staleness_bin"].value_counts()
    all_assignment = {"first_tick_exclusion": int(assignment["first_tick_exclusion"]), "fresh_ticks": int(assignment["fresh"]), "fresh_games": int(assigned.loc[assigned["staleness_bin"] == "fresh", "game_id"].nunique()), "middle_ticks": int(assignment["middle"]), "stale_ticks": int(assignment["stale"]), "stale_games": int(assigned.loc[assigned["staleness_bin"] == "stale", "game_id"].nunique())}
    assert len(evaluator_rows) == len(fitted) == 461947
    assert len(scored) == 460365 and len(evaluator_rows) - len(scored) == 1582
    metrics = _boot_metrics(scored)
    interaction = metrics["interaction_stale_minus_fresh"]["ci95"]
    verdict = "NULL" if metrics["stale"]["improvement"] < 0.004 or interaction[0] <= 0.0 <= interaction[1] else "AT_FROZEN_BAR"
    output_dir.mkdir(parents=True, exist_ok=True)
    paired_path = output_dir / (STEM + "_paired_losses.csv")
    columns = ["game_id", "game_date", "ts", "staleness_bin", "market_prob", "recal_null", "outcome_home_win", "y", "loss_market", "loss_recal_null", "split_id", "n_train"]
    scored.loc[:, columns].sort_values(["game_id", "ts"], kind="stable").to_csv(paired_path, index=False, encoding="ascii")
    rss_after = int(psutil.Process().memory_info().rss)
    summary = {"mode": "SEALED_STRATIFICATION", "attempt": 2, "verdict": verdict, "bar": 0.004, "embargo_days": EMBARGO_DAYS, "bootstraps": BOOTSTRAPS, "seed": SEED, "preregistration_path": str(PREREG.relative_to(ROOT)).replace("\\", "/"), "prereg_sha256": PREREG_SHA256, "paired_losses": str(paired_path.relative_to(ROOT)).replace("\\", "/"), "all_assignment": all_assignment, "evaluator_ticks": int(len(evaluator_rows)), "surviving_first_ticks": int(len(evaluator_rows) - len(scored)), "scored_ticks": int(len(scored)), "recal_seed_ticks": int(len(assigned) - len(fitted)), "record_identity_assertion": identity, "metrics": metrics, "input": {"path": str(SOURCE.relative_to(ROOT)).replace("\\", "/"), "bytes": SOURCE.stat().st_size, "rows": len(raw), "resolution": "not applicable"}, "rss_before_bytes": rss_before, "rss_after_bytes": rss_after, "rss_bytes": rss_after, "route_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (output_dir / (STEM + "_summary.json")).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    (output_dir / (STEM + ".md")).write_text(_memo(summary), encoding="ascii")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="S277 sealed NBA market-staleness stratification")
    parser.add_argument("--output-dir", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    summary = run(args.output_dir)
    print("RSS before=%d after=%d" % (summary["rss_before_bytes"], summary["rss_after_bytes"]))
    print(summary["record_identity_assertion"])
    print("S277 verdict=%s stale_improvement=%.9f interaction=%.9f" % (summary["verdict"], summary["metrics"]["stale"]["improvement"], summary["metrics"]["interaction_stale_minus_fresh"]["value"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

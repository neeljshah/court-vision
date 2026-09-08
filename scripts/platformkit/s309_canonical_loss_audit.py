"""S309 canonical in-game loss audit; compute-only evidence route."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import psutil

from scripts.platformkit.s309_design_evaluators import evaluate_designs

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/harness"
CHECKPOINTS = ROOT / "data/cache/inplay_odds/nba_checkpoints_full.parquet"
PRICES = ROOT / "data/cache/inplay_odds/nba_price_series.parquet"
BRIDGE = ROOT / "data/domains/basketball_nba/espn_nba_game_bridge.parquet"
HISTORICAL = EVIDENCE / "S272_ingame_tail_recal_screen_2026-09-04_paired_losses.csv"
S280 = EVIDENCE / "S280_ingame_cross_venue_disagreement_2026-09-04_ticks.csv"
STEM = "S309_canonical_loss_audit_2026-09-07c"
PREREG = EVIDENCE / "S309_canonical_loss_audit_2026-09-07b_preregistration.md"
SEAL = "cd9e157abc95c2e699228069bfa40292621fc26f6e48fa0352b3d992e5f69cad"
SUPPLEMENT = EVIDENCE / (STEM + "_supplement.md")
SUPPLEMENT_SEAL = "b6d7bc237d9863838a852c82929fc107185d3263924bddb15070c2c8be19d6a7"
BAR, SEED, BOOTSTRAPS, EMBARGO_DAYS = 0.004, 901, 10_000, 1
BULK = ("train_game_ids", "test_game_ids", "isotonic_low_x", "isotonic_low_y", "isotonic_high_x", "isotonic_high_y")
POLY = re.compile(r"^nba-([a-z]{3})-([a-z]{3})-([0-9]{4}-[0-9]{2}-[0-9]{2})$")
KALSHI = re.compile(r"^KXNBA(?:GAME|SPREAD)-([0-9]{2}[A-Z]{3}[0-9]{2})([A-Z]{6})-")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _meta(path: Path, rows: pd.DataFrame, ident: str) -> dict:
    return {"path": path.relative_to(ROOT).as_posix(), "absolute_path": str(path),
            "bytes": path.stat().st_size,
            "sha256": _sha(path), "rows": int(len(rows)), "columns": list(rows.columns),
            "first_3_ids": [str(x) for x in rows[ident].head(3)]}


def _parse(ticker: object) -> tuple[str, str, str] | None:
    text = str(ticker)
    match = POLY.match(text)
    if match:
        return match.group(3), match.group(1).upper(), match.group(2).upper()
    match = KALSHI.match(text)
    if match:
        date = datetime.strptime(match.group(1), "%y%b%d").date().isoformat()
        teams = match.group(2)
        return date, teams[:3], teams[3:]
    return None


def _verify_seal(path: Path, expected: str) -> None:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    prefix, seal = data.split(b"Seal SHA-256: ", 1)
    assert hashlib.sha256(prefix).hexdigest() == expected
    assert seal.decode("ascii").strip() == expected


def _canonical(prices: pd.DataFrame, checkpoints: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    games: dict[tuple[str, str, str], str] = {}
    for row in checkpoints[["game_id", "market_ticker"]].drop_duplicates().itertuples(index=False):
        triple = _parse(row.market_ticker)
        if triple is not None:
            games.setdefault(triple, str(row.game_id))
    source = prices.loc[prices["market_type"].eq("moneyline")].copy()
    parsed = source["ticker_or_slug"].map(_parse)
    source["parsed_date"] = parsed.map(lambda x: x[0] if x else "")
    source["parsed_away"] = parsed.map(lambda x: x[1] if x else "")
    source["parsed_home"] = parsed.map(lambda x: x[2] if x else "")
    source["game_id_alias"] = parsed.map(lambda x: games.get(x, "") if x else "")
    source["canonical_home_prob"] = np.nan
    source["accounting_reason"] = "UNPARSEABLE_EVENT"
    valid = source["game_id_alias"].ne("")
    source.loc[valid, "accounting_reason"] = "MISSING_PROB"
    usable = valid & source["prob"].notna()
    home, away = source["parsed_home"].str.upper(), source["parsed_away"].str.upper()
    side, venue = source["side"].astype(str).str.upper(), source["venue"].astype(str).str.lower()
    # Polymarket labels its sides "home"/"away"; Kalshi labels them with the team tricode.
    is_home = usable & ((venue.eq("polymarket") & side.eq("HOME")) | (venue.eq("kalshi") & side.eq(home)))
    is_away = usable & ((venue.eq("polymarket") & side.eq("AWAY")) | (venue.eq("kalshi") & side.eq(away)))
    keys = ["game_id_alias", "venue", "event_key", "ts"]
    # "side == parsed home, ELSE complement the away side": the complement is a fallback, used
    # only where the key carries no home-side row (both sides are quoted at one ts otherwise).
    away_only = is_away & ~pd.MultiIndex.from_frame(source[keys]).isin(pd.MultiIndex.from_frame(source.loc[is_home, keys]))
    source["canonical_branch"] = ""
    source.loc[usable, "accounting_reason"] = "NONCANONICAL_SIDE"
    source.loc[is_away, "accounting_reason"] = "COMPLEMENT_UNUSED_HOME_PRESENT"
    source.loc[is_home | away_only, "accounting_reason"] = "CANONICAL"
    source.loc[is_home, "canonical_branch"] = "DIRECT_HOME"
    source.loc[away_only, "canonical_branch"] = "COMPLEMENT_AWAY"
    source.loc[is_home, "canonical_home_prob"] = source.loc[is_home, "prob"]
    source.loc[away_only, "canonical_home_prob"] = 1.0 - source.loc[away_only, "prob"]
    chosen = source.loc[source["accounting_reason"].eq("CANONICAL")].copy()
    # the price store repeats whole ticks; collapse identical (key, probability) copies to one row.
    # a key left with two DIFFERENT probabilities is still an error and raises below.
    repeated = chosen.duplicated(keys + ["canonical_home_prob"], keep="first")
    source.loc[chosen.index[repeated], "accounting_reason"] = "EXACT_DUPLICATE_TICK"
    chosen = chosen.loc[~repeated]
    duplicate = chosen.duplicated(keys, keep=False)
    if duplicate.any():
        bad = pd.MultiIndex.from_frame(chosen.loc[duplicate, keys])
        source.loc[pd.MultiIndex.from_frame(source[keys]).isin(bad), "accounting_reason"] = "DUPLICATE_CANONICAL_KEY"
        chosen = source.loc[source["accounting_reason"].eq("CANONICAL")].copy()
        raise AssertionError("duplicate canonical home-side keys")
    assert source["accounting_reason"].notna().all()
    return source, chosen


def _score(checkpoints: pd.DataFrame) -> tuple[pd.DataFrame, list[dict], dict]:
    """Build one evaluator state per tick, then score BOTH designs through the shared gate."""
    rows = checkpoints.copy()
    rows["game_date"] = pd.to_datetime(rows["game_date"]).dt.date.astype(str)
    triples = rows["market_ticker"].map(_parse)
    rows["away"] = triples.map(lambda x: x[1] if x else "UNKNOWN_AWAY")
    rows["home"] = triples.map(lambda x: x[2] if x else "UNKNOWN_HOME")
    rows["state_ts"] = pd.to_datetime(rows["ts"], unit="s", utc=True).astype(str)
    rows["game_id"] = rows["game_id"].astype(str)
    rows["state_key"] = rows["game_id"] + "|" + rows["state_ts"]
    assert rows["state_key"].is_unique, "one evaluator state per scored tick"
    return evaluate_designs(rows)


def _metric(rows: pd.DataFrame, baseline: str, candidate: str, seed_offset: int, prob: str = "p_forward_candidate") -> dict:
    group = rows.groupby("game_id", sort=False)
    counts = group.size().to_numpy(float)
    base, cand = group[baseline].sum().to_numpy(float), group[candidate].sum().to_numpy(float)
    rng = np.random.default_rng(SEED + seed_offset)
    draws = rng.integers(0, len(counts), size=(BOOTSTRAPS, len(counts)))
    boot = np.array([(base[x].sum() - cand[x].sum()) / counts[x].sum() for x in draws])
    delta = (base.sum() - cand.sum()) / counts.sum()
    clip = np.clip(rows[prob].to_numpy(float), 1e-6, 1 - 1e-6)
    y = rows.outcome_home_win.to_numpy(float)
    return {"n_ticks": int(len(rows)), "n_games": int(len(counts)), "baseline_brier": float(base.sum() / counts.sum()),
            "candidate_brier": float(cand.sum() / counts.sum()), "improvement_baseline_minus_candidate": float(delta),
            "improvement_ci95": [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))],
            "candidate_mde": float(1.96 * np.std(boot, ddof=1)), "candidate_log_loss": float(-np.mean(y*np.log(clip)+(1-y)*np.log(1-clip))),
            "candidate_ece_10bin": _ece(clip, y)}


def _ece(p: np.ndarray, y: np.ndarray) -> float:
    bins = np.minimum((p * 10).astype(int), 9)
    return float(sum(np.mean(bins == i) * abs(p[bins == i].mean() - y[bins == i].mean()) for i in range(10) if (bins == i).any()))


def _historical() -> dict:
    """Replay S272: paired-loss Brier AND the RETAINED tail ECE change (spec VERSION line 49)."""
    summary_path = EVIDENCE / "S272_ingame_tail_recal_screen_2026-09-04_summary.json"
    old = pd.read_csv(HISTORICAL)
    game = old.loc[old.record_type.eq("all_game")]
    n = game.n_ticks.sum()
    candidate, baseline = game.loss_candidate_sum.sum() / n, game.loss_incumbent_sum.sum() / n
    expected = json.loads(summary_path.read_text())
    replay, tail_expected = expected["metrics"]["all"], expected["metrics"]["tail"]
    tail = old.loc[old.record_type.eq("tail_tick")]
    y = tail.outcome_home_win.to_numpy(float)
    tail_cand, tail_inc = _ece(tail.candidate.to_numpy(float), y), _ece(tail.incumbent.to_numpy(float), y)
    return {"input": _meta(HISTORICAL, old, "game_id"), "summary_input": {"path": summary_path.relative_to(ROOT).as_posix(), "absolute_path": str(summary_path), "bytes": summary_path.stat().st_size, "sha256": _sha(summary_path)},
            "n_ticks": int(n), "n_games": int(len(game)), "candidate_brier": float(candidate), "baseline_brier": float(baseline),
            "candidate_replay_error": float(abs(candidate-replay["candidate_brier"])), "baseline_replay_error": float(abs(baseline-replay["incumbent_brier"])),
            "retained_candidate_improvement": float(baseline - candidate),
            "retained_tail_n_ticks": int(len(tail)), "retained_tail_n_games": int(tail.game_id.nunique()),
            "retained_tail_ece_incumbent": tail_inc, "retained_tail_ece_candidate": tail_cand,
            "retained_tail_ece_change_candidate_minus_incumbent": float(tail_cand - tail_inc),
            "tail_ece_replay_error": float(max(abs(tail_cand - tail_expected["candidate_ece"]),
                                               abs(tail_inc - tail_expected["incumbent_ece"])))}


def _poly_replay(keys: pd.DataFrame) -> float:
    """Alias metric kept from the pre-attempt-2 schema: Polymarket raw minus canonical."""
    poly = keys.loc[keys.venue.astype(str).str.lower().eq("polymarket")]
    if poly.empty:
        return float("inf")
    return float(np.max(np.abs(poly.prob.to_numpy(float) - poly.canonical_home_prob.to_numpy(float))))


def _s280_replay() -> dict:
    rows = pd.read_csv(S280)
    delta = rows.loss_recal_null - rows.loss_augmented
    return {"input": _meta(S280, rows, "game_id"), "n_ticks": int(len(rows)), "n_games": int(rows.game_id.nunique()), "tick_weighted_improvement": float(delta.mean()),
            "equal_game_improvement": float(delta.groupby(rows.game_id).mean().mean()),
            "tick_minus_game": float(delta.mean() - delta.groupby(rows.game_id).mean().mean())}


def run(output_dir: Path) -> dict:
    """Run the one-state-per-tick audit and write only requested evidence."""
    _verify_seal(PREREG, SEAL)
    _verify_seal(SUPPLEMENT, SUPPLEMENT_SEAL)
    # STOP GATE, ahead of _score and of every source read: S272 must replay to 1e-12 or the run stops.
    historical = _historical()
    assert historical["baseline_replay_error"] <= 1e-12, "NOT REPRODUCED: S272 baseline paired-loss replay"
    assert historical["candidate_replay_error"] <= 1e-12, "NOT REPRODUCED: S272 candidate paired-loss replay"
    assert historical["tail_ece_replay_error"] <= 1e-12, "NOT REPRODUCED: S272 retained tail ECE replay"
    s280 = _s280_replay()
    checkpoints, prices, bridge = pd.read_parquet(CHECKPOINTS), pd.read_parquet(PRICES), pd.read_parquet(BRIDGE)
    inputs = [_meta(CHECKPOINTS, checkpoints, "game_id"), _meta(PRICES, prices, "event_key"), _meta(BRIDGE, bridge, "game_id")]
    accounting, keys = _canonical(prices, checkpoints)
    scored, folds, design_provenance = _score(checkpoints)
    terminal = (scored.period >= 4) & (scored.game_clock_s == 0)
    cuts = {"all": (scored, 0), "positive_clock": (scored.loc[scored.game_clock_s > 0], 1),
            "zero_clock": (scored.loc[scored.game_clock_s == 0], 2), "unknown_status": (scored.loc[terminal], 3)}
    # forward-only is the deployment headline; the CPCV tables are the labelled robustness
    # companion and are published as NAMED SECONDARY paired design scores.
    tables = {name: _metric(part, "loss_forward_baseline", "loss_forward_candidate", off) for name, (part, off) in cuts.items()}
    tables_cpcv = {name: _metric(part, "loss_cpcv_baseline", "loss_cpcv_candidate", off + 40, "p_cpcv_candidate") for name, (part, off) in cuts.items()}
    design_rows = scored.groupby("game_id").agg(n=("game_id", "size"), forward=("loss_forward_candidate", "sum"), cpcv=("loss_cpcv_candidate", "sum"))
    rng = np.random.default_rng(SEED + 99); picks = rng.integers(0, len(design_rows), size=(BOOTSTRAPS, len(design_rows)))
    d = design_rows.forward.to_numpy() - design_rows.cpcv.to_numpy(); n = design_rows.n.to_numpy()
    boot = np.array([d[x].sum()/n[x].sum() for x in picks]); value = float(d.sum()/n.sum())
    poly_games = keys.loc[keys.venue.astype(str).str.lower().eq("polymarket"), "game_id_alias"].nunique()
    counts = accounting.accounting_reason.value_counts().to_dict()
    venues = keys.groupby("game_id_alias").venue.nunique(); overlap = int((venues > 1).sum())
    # replay the documented construction on both branches: direct home, else 1 - away
    raw = keys.prob.to_numpy(float)
    expected = np.where(keys.canonical_branch.eq("COMPLEMENT_AWAY").to_numpy(), 1.0 - raw, raw)
    replay_error = float(np.max(np.abs(keys.canonical_home_prob.to_numpy(float) - expected))) if len(keys) else float("inf")
    canonical = {"source_moneyline_rows": int(len(accounting)), "canonical_rows": int(len(keys)),
                 "duplicate_keys": int(keys.duplicated(["game_id_alias", "venue", "event_key", "ts"]).sum()),
                 "unaccounted_rows": int(accounting.accounting_reason.isna().sum()), "reason_counts": counts,
                 "branch_counts": keys.canonical_branch.value_counts().to_dict(),
                 "polymarket_games_joined": int(poly_games), "cross_venue_games": overlap,
                 "cross_venue_verdict": "CLOSED AT LIMIT" if overlap < 30 else "REPORTED",
                 "probability_replay_max_abs_error": replay_error,
                 # B2 alias: the pre-2026-09-07b key name, retained with its ORIGINAL
                 # Polymarket-only semantics (raw side probability minus canonical).
                 "polymarket_probability_replay_max_abs_error": _poly_replay(keys)}
    summary = {"spec": "S309", "verdict": "SCREEN_ONLY", "bar": BAR, "seed": SEED, "bootstraps": BOOTSTRAPS, "embargo_days": EMBARGO_DAYS,
               "preregistration_path": PREREG.relative_to(ROOT).as_posix(), "prereg_sha256": SEAL,
               "supplement_path": SUPPLEMENT.relative_to(ROOT).as_posix(), "supplement_sha256": SUPPLEMENT_SEAL, "inputs": inputs,
               "historical": historical, "s280": s280, "canonical": canonical, "tables": tables, "tables_cpcv_secondary": tables_cpcv,
               "design": {"delta_forward_minus_cpcv": value, "ci95": [float(np.quantile(boot,.025)), float(np.quantile(boot,.975))], "design_sensitive": bool(np.quantile(boot,.025) > 0 or np.quantile(boot,.975) < 0), "provenance": design_provenance},
               "route_sha256": _sha(Path(__file__)), "shared_route_sha256": {"cpcv_engine": _sha(ROOT / "scripts/platformkit/eval_gate/cpcv_engine.py"), "walkforward": _sha(ROOT / "scripts/platformkit/eval_gate/walkforward.py")}, "rss_bytes": int(psutil.Process().memory_info().rss)}
    assert canonical["polymarket_games_joined"] == 1593 and canonical["unaccounted_rows"] == 0
    assert canonical["duplicate_keys"] == 0 and canonical["probability_replay_max_abs_error"] <= 1e-12
    assert canonical["polymarket_probability_replay_max_abs_error"] <= 1e-12
    output_dir.mkdir(parents=True, exist_ok=True)
    accounting.to_parquet(output_dir / (STEM + "_accounting.parquet"), index=False)
    keys.to_parquet(output_dir / (STEM + "_keys.parquet"), index=False)
    # the folds JSON keeps the attempt-1 scalar schema; the exact membership and the fitted
    # isotonic (X, y) go beside it in a parquet, which is columnar rather than 30 MB of JSON.
    fold_frame = pd.DataFrame(folds)
    fold_frame.drop(columns=list(BULK)).to_json(output_dir / (STEM + "_folds.json"), orient="records", indent=2)
    fold_frame[["arm", "fit_index", "fold_date", "n_train_games", "test_games"] + list(BULK)].to_parquet(
        output_dir / (STEM + "_fold_members.parquet"), index=False)
    # B2: the attempt-1 probability column names are RETAINED as aliases of the forward (headline) arm.
    scored["p_baseline"], scored["p_candidate"] = scored["p_forward_baseline"], scored["p_forward_candidate"]
    keep = ["state_key","game_id","state_ts","home","away","game_date","period","game_clock_s","outcome_home_win","p_baseline","p_candidate","p_forward_baseline","p_forward_candidate","p_cpcv_baseline","p_cpcv_candidate","loss_forward_baseline","loss_forward_candidate","loss_cpcv_baseline","loss_cpcv_candidate","evaluator_records"]
    scored[keep].to_parquet(output_dir / (STEM + "_paired_losses.parquet"), index=False)
    (output_dir / (STEM + ".json")).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    # the memo is authored by the lane, not by the route: an artifact cannot carry a correct
    # hash of a file the lane rewrites afterwards (that was the attempt-1 stale-hash defect).
    hashes = {p.name: _sha(p) for p in sorted(output_dir.glob(STEM + "*")) if p.is_file()}
    (output_dir / (STEM + "_hashes.json")).write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="S309 canonical loss audit")
    parser.add_argument("--output-dir", type=Path, default=EVIDENCE)
    args = parser.parse_args(); summary = run(args.output_dir)
    print("S309 verdict=%s all_improvement=%.12f design_delta=%.12f fits=%d/%d rss_bytes=%d" % (
        summary["verdict"], summary["tables"]["all"]["improvement_baseline_minus_candidate"],
        summary["design"]["delta_forward_minus_cpcv"], summary["design"]["provenance"]["forward"]["fits"],
        summary["design"]["provenance"]["cpcv"]["fits"], summary["rss_bytes"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

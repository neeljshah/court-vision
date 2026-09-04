"""S266 bounded construct-scale, snapshot-only NBA simulator measurement."""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import brier, ece

ROOT = Path(__file__).resolve().parents[3]
ARCHIVE = ROOT / "data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_all.csv"
S255 = ROOT / "docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04"
OUT = ROOT / "docs/evidence/harness/S266_nba_sim_third_arm_construct_2026-09-04"
MEMO = ROOT / "docs/evidence/harness/S266_nba_sim_third_arm_construct_2026-09-04.md"
GRID_SECONDS = (120, 600, 1080, 1560, 2040, 2520)
SEED, N_GAMES, N_SIMS, MEMORY_CAP_MB = 2561001, 30, 32, 600
BAR = 0.004
BASE = {"use_per_min": .08, "tov_share": .12, "ft_share": .08, "z_rim": .25,
        "z_paint": .25, "z_mid": .25, "z_3": .25, "fg_rim": .625,
        "fg_paint": .455, "fg_mid": .4, "fg3_pct": .355, "ft_pct": .75,
        "ast_per_min": .08, "oreb_per_min": .03, "dreb_per_min": .12,
        "stl_per_min": .02, "blk_per_min": .01, "pf_per_min": .08,
        "self_create": .4, "height": 78.4, "int_d": 50., "perim_d": 50., "supp": 0.}


@dataclass(frozen=True)
class Inputs:
    """Read-only inputs approved by the sealed S266 preregistration."""

    archive: Path = ARCHIVE
    player: Path = S255 / "player_rate_snapshots.parquet"
    team: Path = S255 / "team_rate_snapshots.parquet"
    qualification: Path = S255 / "cluster_qualification.csv"


class MemoryLimit(RuntimeError):
    """Stop immediately when process RSS passes the local construct rail."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _src_sha() -> str:
    digest = hashlib.sha256()
    names = subprocess.check_output(["git", "ls-files", "src"], cwd=ROOT, text=True).splitlines()
    for name in names:
        digest.update(name.encode("utf-8") + b"\0")
        digest.update((ROOT / name).read_bytes())
    return digest.hexdigest()


def _rss() -> float:
    import psutil
    return float(psutil.Process().memory_info().rss) / 1048576.0


def _limit(where: str) -> float:
    rss = _rss()
    if rss > MEMORY_CAP_MB:
        print(f"MEMORY LIMIT RSS {rss:.2f} MB allocation={where}", flush=True)
        raise MemoryLimit(f"RSS {rss:.2f} MB at {where}")
    return rss


def _five(value: str) -> tuple[int, ...]:
    values = tuple(int(part) for part in str(value).split("|"))
    if len(values) != 5 or len(set(values)) != 5:
        raise ValueError(f"invalid five-player lineup {value}")
    return values


def select_games(qualification: pd.DataFrame, game_ids: Sequence[str] | None = None) -> pd.DataFrame:
    """Return exactly the preregistered whole-game sample under strict S255 dates."""
    frame = qualification.copy()
    frame["game"] = frame["game"].astype(str)
    dates = {name: pd.to_datetime(frame[name], errors="coerce") for name in
             ("game_date", "player_snapshot_date", "team_snapshot_date")}
    strict = ((dates["player_snapshot_date"] < dates["game_date"])
              & (dates["team_snapshot_date"] < dates["game_date"]))
    if not (strict == frame["qualifies"].astype(bool)).all():
        raise AssertionError("S255 qualification disagrees with strict dates")
    eligible = sorted(frame.loc[strict, "game"].unique())
    if len(eligible) != 355:
        raise AssertionError(f"expected 355 qualifying clusters, got {len(eligible)}")
    chosen = (sorted(np.random.default_rng(SEED).choice(eligible, N_GAMES, replace=False).tolist())
              if game_ids is None else sorted(set(map(str, game_ids))))
    if len(chosen) != N_GAMES or not set(chosen).issubset(eligible):
        raise ValueError("--game-ids must name exactly 30 qualifying whole-game clusters")
    result = frame[frame["game"].isin(chosen)].copy()
    if result["game"].nunique() != N_GAMES:
        raise AssertionError("selected game cluster was not retained whole")
    return result


def read_archive(game_ids: Sequence[str], archive: Path) -> pd.DataFrame:
    """Stream S92 and retain selected games before any grid or simulator input exists."""
    columns = ["game", "ts", "elapsed", "outcome_home_win", "home_five", "away_five",
               "market_prob", "p_null", "cluster_id"]
    kept, offset = [], 0
    for chunk in pd.read_csv(archive, usecols=columns, chunksize=5000, dtype={"game": str}):
        chunk["source_order"] = np.arange(offset, offset + len(chunk))
        offset += len(chunk)
        chosen = chunk[chunk["game"].isin(game_ids)]
        if not chosen.empty:
            kept.append(chosen)
    if not kept:
        raise RuntimeError("CLOSED AT LIMIT selected games absent from S92 archive")
    return pd.concat(kept, ignore_index=True)


def select_grid(archive: pd.DataFrame, selected: pd.DataFrame) -> pd.DataFrame:
    dates = selected.set_index("game")[["game_date", "player_snapshot_date", "team_snapshot_date"]]
    picks: list[pd.DataFrame] = []
    for game, block in archive.groupby("game", sort=True):
        for target in GRID_SECONDS:
            picked = block.assign(distance=(block["elapsed"] - target).abs()).sort_values(
                ["distance", "ts", "source_order"], kind="stable").iloc[[0]].copy()
            picked["grid_target_elapsed"] = target
            picks.append(picked)
    grid = pd.concat(picks, ignore_index=True).join(dates, on="game", how="left")
    grid["state_key"] = grid["game"] + ":" + grid["grid_target_elapsed"].astype(str)
    if len(grid) != N_GAMES * len(GRID_SECONDS) or not grid.state_key.is_unique:
        raise AssertionError("frozen grid is not 30 complete game clusters x 6 ticks")
    return grid.sort_values(["ts", "game", "grid_target_elapsed"], kind="stable").reset_index(drop=True)


def read_snapshots(inputs: Inputs, selected: pd.DataFrame) -> tuple[dict[str, float], dict[str, float]]:
    dates = sorted(set(selected.player_snapshot_date.astype(str)) | set(selected.team_snapshot_date.astype(str)))
    predicate = [("as_of_date", "in", [pd.Timestamp(date) for date in dates])]
    player = pd.read_parquet(inputs.player, columns=["as_of_date", "ft_rate_q50"], filters=predicate)
    team = pd.read_parquet(inputs.team, columns=["as_of_date", "team_tempo_z"], filters=predicate)
    if player.empty or team.empty:
        raise RuntimeError("CLOSED AT LIMIT selected snapshot-date predicate returned no rows")
    pmean = player.groupby(player.as_of_date.dt.strftime("%Y-%m-%d")).ft_rate_q50.mean().to_dict()
    tmean = team.groupby(team.as_of_date.dt.strftime("%Y-%m-%d")).team_tempo_z.mean().to_dict()
    del player, team
    gc.collect()
    return {str(k): float(v) for k, v in pmean.items()}, {str(k): float(v) for k, v in tmean.items()}


def make_states(grid: pd.DataFrame, pmean: dict[str, float], tmean: dict[str, float]) -> tuple[list[dict], list[dict]]:
    states, fills = [], []
    for row in grid.itertuples(index=False):
        pdate, tdate = str(row.player_snapshot_date), str(row.team_snapshot_date)
        if pdate not in pmean or tdate not in tmean:
            raise RuntimeError("CLOSED AT LIMIT selected game did not join both S255 snapshots")
        scale = float(np.clip(pmean[pdate] / 2.5, .5, 1.5))
        rates = {key: value * scale for key, value in BASE.items()}
        rates["ft_share"] = float(np.clip(pmean[pdate] / 25.0, .01, .5))
        fills.append({"game": row.game, "player_snapshot_date": pdate,
                      "team_snapshot_date": tdate, "league_mean_field": "ft_rate_q50",
                      "filled_fast_sim_fields": ",".join(sorted(BASE)),
                      "transform": "date_mean_ft_rate_q50_scaled_baseline"})
        features = {"home_ids": _five(row.home_five), "away_ids": _five(row.away_five), "rates": rates,
                    "pace": max(1., 100. * (1. - row.elapsed / 2880.) * (1. + np.clip(tmean[tdate], -.2, .2))),
                    "seed": int(row.game) % 2147483647 + int(row.grid_target_elapsed)}
        states.append({"game_id": row.state_key, "state_ts": pd.Timestamp(int(row.ts), unit="s", tz="UTC").isoformat(),
                       "home": str(row.home_five), "away": str(row.away_five), "outcome": int(row.outcome_home_win),
                       "devig_close_prob": float(row.market_prob), "features": features,
                       "feature_avail": {key: f"{pdate}T00:00:00+00:00" for key in features}})
    return states, fills


def price(features: dict[str, Any]) -> float:
    """Price one snapshot-only simulator state."""
    from src.sim import fast_sim as fast_sim

    def team(ids: tuple[int, ...], side: str) -> Any:
        rates = {pid: {**features["rates"], "team": side, "player": f"S255_{pid}"} for pid in ids}
        return fast_sim.TeamModel(side, rates, features["pace"], .55, .25, [ids], np.array([1.]))
    result = fast_sim.simulate_game_fast(team(features["home_ids"], "HOME"),
                                        team(features["away_ids"], "AWAY"), n_sims=N_SIMS,
                                        seed=int(features["seed"]), anchor=False, defense=False,
                                        dispersion=False, dev="cpu")
    home, away = np.asarray(result.home_total), np.asarray(result.away_total)
    return float((home > away).mean() + .5 * (home == away).mean())


def score(game_ids: Sequence[str] | None = None, inputs: Inputs = Inputs()) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Score only the sealed 30-game construct route; no full-set path is exposed."""
    before = {name: _sha(path) for name, path in asdict(inputs).items()}
    src_before = _src_sha()
    selected = select_games(pd.read_csv(inputs.qualification), game_ids)
    archive = read_archive(selected.game.tolist(), inputs.archive)
    grid = select_grid(archive, selected)
    del archive
    pmean, tmean = read_snapshots(inputs, selected)
    states, fills = make_states(grid, pmean, tmean)
    del selected, pmean, tmean
    gc.collect()
    print(f"RSS BEFORE SCORING {_limit('before_cpcv'):.2f} MB", flush=True)
    peak = _rss()

    def callback(_train: list[dict], test: dict, _inside: bool) -> float:
        nonlocal peak
        _limit("simulator_callback")
        value = price(test["features"])
        peak = max(peak, _limit("simulator_callback"))
        return value

    records = cpcv_evaluate(states, callback, n_groups=8, n_test_groups=1, embargo_days=3,
                            strict_redaction=True)
    print(f"RSS AFTER SCORING {_limit('after_cpcv'):.2f} MB", flush=True)
    pred = pd.DataFrame(records).rename(columns={"game_id": "state_key", "p_model": "p_simulator"})
    if len(pred) != len(grid) or not pred.state_key.is_unique:
        raise AssertionError("shared evaluator did not emit one probability per frozen tick")
    scored = grid.merge(pred[["state_key", "p_simulator", "n_train"]], on="state_key", validate="one_to_one")
    y = scored.outcome_home_win.to_numpy(float)
    arms = {"market": scored.market_prob.to_numpy(float), "recal_null": scored.p_null.to_numpy(float),
            "simulator": scored.p_simulator.to_numpy(float)}
    for name, values in arms.items():
        scored[f"loss_{name}"] = (values - y) ** 2
    scored["paired_loss_recal_null_minus_simulator"] = scored.loss_recal_null - scored.loss_simulator
    per_game = scored.groupby("game", as_index=False).agg(cluster_id=("cluster_id", "first"),
        timestamp=("state_key", "first"), n_ticks=("state_key", "size"), loss_recal_null=("loss_recal_null", "mean"),
        loss_simulator=("loss_simulator", "mean"), paired_loss_recal_null_minus_simulator=("paired_loss_recal_null_minus_simulator", "mean"))
    dm = diebold_mariano(scored.paired_loss_recal_null_minus_simulator, scored.game)
    after = {name: _sha(path) for name, path in asdict(inputs).items()}
    src_after = _src_sha()
    if before != after or src_before != src_after:
        raise AssertionError("S255/S92 or src identity changed during construct scoring")
    verdict = "BEHIND" if dm.mean_diff < 0 else "SCREEN_NULL"
    summary = {"attempt": "S266 construct", "seed": SEED, "n_games": int(per_game.game.nunique()),
        "n_ticks": int(len(scored)), "grid_seconds": list(GRID_SECONDS), "sample_games": sorted(per_game.game.tolist()),
        "arms": {name: {"brier": brier(values, y), "ece_10": ece(values, y, bins=10)} for name, values in arms.items()},
        "improvement_vs_recal_null": float(dm.mean_diff), "ci95_game_clustered": list(dm.ci95), "bar": BAR,
        "verdict": verdict, "status": verdict, "peak_rss_mb": peak, "fills": fills,
        "input_sha256_before": before, "input_sha256_after": after,
        "src_sha256_before": src_before, "src_sha256_after": src_after}
    return summary, scored, per_game


def _write(summary: dict, scored: pd.DataFrame, per_game: pd.DataFrame, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    outputs = {"S266_selected_tick_series.csv": scored, "S266_per_game_paired_loss_series.csv": per_game,
               "S256_selected_tick_series_construct.csv": scored,
               "S256_per_game_paired_loss_series_construct.csv": per_game}
    for name, frame in outputs.items():
        frame.to_csv(out / name, index=False)
    encoded = json.dumps(summary, indent=2, sort_keys=True)
    for name in ("S266_summary.json", "S256_summary_construct.json"):
        (out / name).write_text(encoded, encoding="ascii")


select_sample = select_games
price_snapshot_only = price
evaluate = score


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-ids", help="comma-separated exactly-30 qualifying S255 game IDs")
    parser.add_argument("--out-dir", type=Path, default=OUT)
    args = parser.parse_args()
    ids = args.game_ids.split(",") if args.game_ids else None
    try:
        summary, scored, per_game = score(ids)
    except MemoryLimit as error:
        print(f"CLOSED AT LIMIT {error}")
        return 2
    _write(summary, scored, per_game, args.out_dir)
    for name, data in summary["arms"].items():
        print(f"ARM {name} BRIER {data['brier']:.9f} ECE {data['ece_10']:.9f}")
    print("CI95 %.9f %.9f" % tuple(summary["ci95_game_clustered"]))
    print("FINAL SHA " + _sha(args.out_dir / "S266_summary.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

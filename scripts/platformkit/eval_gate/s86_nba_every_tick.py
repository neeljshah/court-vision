"""scripts.platformkit.eval_gate.s86_nba_every_tick -- S86: price EVERY NBA in-play tick.

data/cache/inplay_odds/nba_checkpoints_full.parquet holds 465,249 ticks / 1,593 games with
state (period, game_clock_s, score, margin), the in-play `market_prob` and `outcome_home_win`.
S58 trial B scored ONE tick per game (halftime_checkpoints :46 keeps `elapsed <= 24` and
`.tail(1)`). `nba_checkpoint_benchmark.price_checkpoint(p0, home, away, period, clock)` is a
PURE state function, so the same code prices every tick off the same AS-OF Elo prior
(domains.basketball_nba.ratings.replay(games, until=game_date) -- games strictly BEFORE the
tick's own game_date).

A SCREEN is a NON-FINDING: no prereg seal, no ledger charge, no K read, no ledger write.
SINGLE-WINDOW (one corpus, NBA 2024-10-22..2026-06-13). Calibration language only. ASCII only.
Per-file test: python -m pytest tests/platformkit/ingame/test_s86_nba_every_tick.py -q
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.calib_decomp import bin_edges
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import ece
from scripts.platformkit.foundry.tiers import partition_corpus
from scripts.platformkit.ingame.gap_effective_n import effective_sample_size
from scripts.platformkit.ingame.nba_checkpoint_benchmark import _elapsed_minutes, price_checkpoint
from scripts.platformkit.wp_diagnostics import max_loser_wp, reliability

REPO = Path(__file__).resolve().parents[3]
CHECKPOINTS = REPO / "data" / "cache" / "inplay_odds" / "nba_checkpoints_full.parquet"
GAMES = REPO / "data" / "domains" / "basketball_nba" / "games.parquet"
S58_PERGAME = REPO / "data" / "cache" / "eval_gate" / "s58_trialB_nba_halftime_asof_pergame_2026-09-03.csv"
OUT_DIR = REPO / "data" / "cache" / "eval_gate"
STEM = "s86_nba_every_tick_2026-09-03"
ALIASES = {"PHO": "PHX", "WSH": "WAS"}
UNIT_BOUNDARY = "2025-08-01"
PARTITION_SEED = 0          # same rule + seed as the sibling screens S80 / S84
EPS_INFORMATIVE = 1e-9


class AsOfLeak(ValueError):
    """A model probability moved when a row at or after its own tick was withheld."""


def rem_minutes(period: int, game_clock_s: float) -> float:
    """Minutes remaining: in regulation to the end of Q4; in OT to the end of that period."""
    s = max(0.0, float(game_clock_s)) / 60.0
    return round(s if int(period) >= 5 else (4 - int(period)) * 12.0 + s, 4)


def period_bucket(period: int) -> str:
    return "OT" if int(period) >= 5 else "P%d" % int(period)


def margin_bucket(margin: float) -> str:
    m = abs(float(margin))
    return "close_le5" if m <= 5 else ("mid_06_12" if m <= 12 else "blowout_gt12")


def rem_bucket(rem: float) -> str:
    r = float(rem)
    if r > 12.0:
        return "rem_gt12"
    if r > 6.0:
        return "rem_06_12"
    return "rem_02_06" if r > 2.0 else "rem_le02"


def load_ticks(path: Path = CHECKPOINTS) -> pd.DataFrame:
    """Every traded tick, ordered per game, with buckets and the informative flag."""
    df = pd.read_parquet(path)
    df = df[df["traded"] == True].copy()  # noqa: E712 -- untraded ticks are reset/stale quotes
    df = df.sort_values(["game_id", "ts"]).reset_index(drop=True)
    parts = df["market_ticker"].str.split("-")
    df["away"] = parts.str[1].str.upper().map(lambda c: ALIASES.get(c, c))
    df["home"] = parts.str[2].str.upper().map(lambda c: ALIASES.get(c, c))
    df["unit"] = np.where(pd.to_datetime(df["game_date"]) < pd.Timestamp(UNIT_BOUNDARY), "2024-25", "2025-26")
    df["y"] = df["outcome_home_win"].astype(float)
    df["elapsed"] = [_elapsed_minutes(int(p), float(c)) for p, c in zip(df["period"], df["game_clock_s"])]
    df["rem"] = [rem_minutes(p, c) for p, c in zip(df["period"], df["game_clock_s"])]
    df["period_bucket"] = df["period"].map(period_bucket)
    df["margin_bucket"] = df["margin"].map(margin_bucket)
    df["rem_bucket"] = df["rem"].map(rem_bucket)
    prev = df.groupby("game_id")["market_prob"].shift(1)
    df["informative"] = prev.isna() | ((df["market_prob"] - prev).abs() > EPS_INFORMATIVE)
    return df


def screen_side(frame: pd.DataFrame, seed: int = PARTITION_SEED):
    """foundry partition_corpus on game blocks -> the SCREEN-side ticks and the record."""
    states = [{"game_id": str(g), "corpus_unit": str(g), "state_ts": str(d) + "T00:00:00"}
              for g, d in frame.groupby("game_id")["game_date"].min().items()]
    part = partition_corpus(states, seed=seed)
    keep = frame["game_id"].astype(str).isin(part.screen_ids)
    return frame[keep].reset_index(drop=True), part


def asof_priors(frame: pd.DataFrame, games: pd.DataFrame) -> Dict[int, Tuple[float, str]]:
    """p0 per game = _p_home over ratings.replay(games, until=game_date) -- strictly BEFORE."""
    from domains.basketball_nba.adapter import _season_to_int
    from domains.basketball_nba.elo_config import ELO_MEAN
    from domains.basketball_nba.ratings import _p_home, replay
    g = games.copy()
    g["season"] = g["season"].apply(_season_to_int)
    cache: Dict[dt.date, Any] = {}
    out: Dict[int, Tuple[float, str]] = {}
    keys = frame.groupby("game_id")[["game_date", "home", "away"]].first()
    for gid, row in keys.iterrows():
        d = pd.Timestamp(row["game_date"]).date()
        if d not in cache:
            cache[d] = replay(g, until=d)
        st = cache[d]
        p = float(_p_home(st.elo.get(str(row["home"]), ELO_MEAN), st.elo.get(str(row["away"]), ELO_MEAN)))
        out[gid] = (p, d.isoformat())
    return out


def price(frame: pd.DataFrame, priors: Dict[int, Tuple[float, str]]) -> pd.DataFrame:
    """Row-wise pure pricing: model_t = f(p0_asof, score_t, period_t, clock_t). No cross-row read."""
    out = frame.copy()
    out["p0_asof"] = out["game_id"].map(lambda g: priors[g][0])
    out["elo_until_date"] = out["game_id"].map(lambda g: priors[g][1])
    assert (pd.to_datetime(out["elo_until_date"]) == pd.to_datetime(out["game_date"])).all(), "prior not as-of"
    rows = zip(out["p0_asof"], out["score_home"], out["score_away"], out["period"], out["game_clock_s"])
    out["model"] = [price_checkpoint(p, h, a, per, c) for p, h, a, per, c in rows]
    out["market"] = out["market_prob"].astype(float)
    out["loss_model"] = (out["model"] - out["y"]) ** 2
    out["loss_market"] = (out["market"] - out["y"]) ** 2
    out["d"] = out["loss_market"] - out["loss_model"]      # d > 0 -> the model lost less
    return out


def assert_no_future_read(scored: pd.DataFrame, priors: Dict[int, Tuple[float, str]],
                          keep: int = 4) -> Dict[str, Any]:
    """THE guard: re-price each game's first `keep` ticks with every later tick WITHHELD.

    A same-tick or later read (a game-level max, a next-tick line, a full-game normaliser)
    would move these values; a row-wise as-of function cannot.
    """
    prefix = scored.groupby("game_id", sort=False).head(keep)
    redone = price(prefix.drop(columns=["p0_asof", "elo_until_date", "model"]), priors)["model"].to_numpy()
    delta = float(np.max(np.abs(redone - prefix["model"].to_numpy()))) if len(prefix) else 0.0
    if delta != 0.0:
        raise AsOfLeak("truncation moved %d model probabilities (max |delta| %.3g)" % (len(prefix), delta))
    return {"n_ticks_repriced": int(len(prefix)), "max_abs_delta": delta, "ticks_per_game_withheld_after": keep}


def _cell(sub: pd.DataFrame) -> Dict[str, Any]:
    y = sub["y"].to_numpy(dtype=float)
    games = sub["game_id"].astype(str)
    row: Dict[str, Any] = {
        "n": int(len(sub)), "n_games": int(games.nunique()),
        "n_informative": int(sub["informative"].sum()),
        "brier_model": float(sub["loss_model"].mean()), "brier_market": float(sub["loss_market"].mean()),
        "improvement_vs_market": float(sub["loss_market"].mean() - sub["loss_model"].mean()),
        "outcome_rate": float(y.mean()), "market_mean_prob": float(sub["market"].mean()),
    }
    ess = effective_sample_size(sub.rename(columns={"game_id": "game", "d": "loss_differential"}))
    row["icc_by_game"], row["design_effect"], row["n_eff"] = ess["rho"], ess["design_effect"], ess["n_eff"]
    if row["n_games"] >= 2:
        dm = diebold_mariano(sub["d"].tolist(), games.tolist())
        row["dm_stat"], row["dm_p_raw"] = float(dm.dm_stat), float(dm.p_value)
        row["dm_ci95"] = [float(dm.ci95[0]), float(dm.ci95[1])]
        row["model_matches_or_ahead"] = bool(dm.ci95[1] >= 0.0)
    else:
        row["dm_stat"] = row["dm_p_raw"] = row["dm_ci95"] = None
        row["model_matches_or_ahead"] = None
    return row


def bucket_table(scored: pd.DataFrame, keys: Sequence[str]) -> List[Dict[str, Any]]:
    rows = []
    for values, sub in scored.groupby(list(keys), sort=True):
        cell = dict(zip(keys, values if isinstance(values, tuple) else (values,)))
        cell.update(_cell(sub))
        rows.append(cell)
    return sorted(rows, key=lambda r: tuple(str(r[k]) for k in keys))


def market_reliability(scored: pd.DataFrame, by: Sequence[str] = ("period_bucket",)) -> Dict[str, Any]:
    """The MARKET's own reliability per phase: 10 equal-width bins + max-loser-WP (S43 style)."""
    out: Dict[str, Any] = {}
    edges = bin_edges(10)
    for key, sub in scored.groupby(list(by), sort=True):
        key = "|".join(key) if isinstance(key, tuple) else key
        ticks = [{"game": str(g), "model_prob": float(p), "outcome": float(o)}
                 for g, p, o in zip(sub["game_id"], sub["market"], sub["y"])]
        loser = max_loser_wp(ticks)
        out[str(key)] = {
            "n": int(len(sub)), "n_games": int(sub["game_id"].nunique()),
            "ece_market": float(ece(sub["market"].to_numpy(), sub["y"].to_numpy())),
            "ece_model": float(ece(sub["model"].to_numpy(), sub["y"].to_numpy())),
            "bins_market": reliability(ticks, edges=edges),
            "max_loser_wp": {"n_loser_paths": len(loser["per_game"]), "quantiles": loser["quantiles"],
                             "above_0_8": loser["above_0_8"], "above_0_9": loser["above_0_9"]},
        }
    return out


def reproduce_s58(scored: pd.DataFrame, csv_path: Path = S58_PERGAME) -> Dict[str, Any]:
    """Independent check: the S58 trial-B per-game prior + price must reappear tick-for-tick."""
    if not Path(csv_path).exists():
        return {"status": "S58_ARTIFACT_ABSENT", "path": str(csv_path)}
    from scripts.platformkit.eval_gate.archive_read import read_series  # S147: seal-aware archive read
    ref = read_series(csv_path).set_index("game_id")
    cp = (scored[scored["elapsed"] <= 24.0].sort_values(["game_id", "elapsed", "ts"])
          .groupby("game_id").tail(1))                       # S58's own checkpoint selection
    join = cp.join(ref[["p0_asof", "model", "elapsed"]], on="game_id", rsuffix="_s58", how="inner")
    if join.empty:
        return {"status": "NO_OVERLAP", "n": 0}
    return {"status": "REPRODUCED", "n_games_matched": int(len(join)),
            "max_abs_elapsed_delta": float((join["elapsed"] - join["elapsed_s58"]).abs().max()),
            "max_abs_p0_delta": float((join["p0_asof"] - join["p0_asof_s58"]).abs().max()),
            "max_abs_model_delta": float((join["model"] - join["model_s58"]).abs().max())}


def summarize(scored: pd.DataFrame, part, guard: Dict[str, Any], repro: Dict[str, Any],
              n_all_ticks: int, n_all_games: int) -> Dict[str, Any]:
    return {
        "spec_id": "scripts.platformkit.eval_gate.s86_nba_every_tick:nba_every_tick_asof_v1",
        "sport": "nba", "tier": "SCREEN (uncharged, no prereg seal, no K read, no ledger write)",
        "label": "SINGLE-WINDOW", "edge_claimed": False,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "corpus": {"path": str(CHECKPOINTS), "n_ticks_total": n_all_ticks, "n_games_total": n_all_games,
                   "start": str(scored["game_date"].min()), "end": str(scored["game_date"].max())},
        "model": "nba_checkpoint_benchmark.price_checkpoint over ratings.replay(until=game_date)",
        "partition": {"rule": "foundry.tiers.partition_corpus (S58 trial B had NO screen/verdict "
                              "partition -- it charged the whole corpus; this is the sibling-screen rule)",
                      "basis": part.basis, "seed": part.seed, "screen_sha256": part.screen_sha256,
                      "verdict_sha256": part.verdict_sha256, "n_screen_games": len(part.screen_ids),
                      "n_verdict_games": len(part.verdict_ids)},
        "asof_guard": guard, "s58_reproduction": repro,
        "pooled": _cell(scored),
        "by_unit": {str(u): _cell(s) for u, s in scored.groupby("unit")},
        "by_period": bucket_table(scored, ["period_bucket"]),
        "by_period_margin": bucket_table(scored, ["period_bucket", "margin_bucket"]),
        "by_period_margin_rem": bucket_table(scored, ["period_bucket", "margin_bucket", "rem_bucket"]),
        "market_reliability_by_period": market_reliability(scored),
        "market_reliability_by_period_margin": market_reliability(scored, ["period_bucket", "margin_bucket"]),
        "note": "Calibration measurement only. The as-of state-priced prior is expected to TRAIL "
                "the in-play line; a BEHIND is an honest result.",
    }


def run(out_dir: Path = OUT_DIR, stem: str = STEM) -> Dict[str, Any]:
    ticks = load_ticks()
    n_all_ticks, n_all_games = int(len(ticks)), int(ticks["game_id"].nunique())
    frame, part = screen_side(ticks)
    priors = asof_priors(frame, pd.read_parquet(GAMES))
    scored = price(frame, priors)
    guard = assert_no_future_read(scored, priors)
    summary = summarize(scored, part, guard, reproduce_s58(scored), n_all_ticks, n_all_games)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    cols = ["game_id", "game_date", "unit", "ts", "period", "game_clock_s", "score_home", "score_away",
            "margin", "elapsed", "rem", "period_bucket", "margin_bucket", "rem_bucket", "informative",
            "p0_asof", "elo_until_date", "model", "market", "y", "loss_model", "loss_market", "d"]
    csv_path = Path(out_dir) / (stem + ".csv")
    scored[cols].to_csv(csv_path, index=False, encoding="ascii")
    summary["per_tick_csv"] = str(csv_path)
    (Path(out_dir) / (stem + ".json")).write_text(
        json.dumps(summary, indent=1, sort_keys=True, default=str), encoding="ascii")
    return summary


def main() -> int:
    s = run()
    p = s["pooled"]
    print("S86 SCREEN %s | screen ticks %d / %d games | model %.6f vs market %.6f | improvement %+.6f"
          % (s["label"], p["n"], p["n_games"], p["brier_model"], p["brier_market"], p["improvement_vs_market"]))
    print("  informative %d | icc %.4f deff %.1f n_eff %.1f | dm_ci95 %s" %
          (p["n_informative"], p["icc_by_game"], p["design_effect"], p["n_eff"], p["dm_ci95"]))
    print("  guard %s | s58 %s" % (s["asof_guard"], s["s58_reproduction"]))
    for r in s["by_period_margin"]:
        print("  %-3s %-13s n %6d inf %6d n_eff %7.1f model %.6f market %.6f impr %+.6f ci %s"
              % (r["period_bucket"], r["margin_bucket"], r["n"], r["n_informative"], r["n_eff"],
                 r["brier_model"], r["brier_market"], r["improvement_vs_market"], r["dm_ci95"]))
    for k, v in s["market_reliability_by_period"].items():
        print("  MARKET %-3s ece %.6f (model %.6f) loser paths %d p90 %s > 0.8 %d"
              % (k, v["ece_market"], v["ece_model"], v["max_loser_wp"]["n_loser_paths"],
                 v["max_loser_wp"]["quantiles"]["90"], v["max_loser_wp"]["above_0_8"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""scripts.platformkit.eval_gate.s58_nba_halftime_asof_trial -- S58 in-game trial B (S63):
NBA halftime checkpoint on the AS-OF Elo prior vs the Polymarket in-play price.

Model = nba_checkpoint_benchmark.price_checkpoint(p0, score, period, clock), a pure function
with p0 = adapter.baseline_probability's formula (ratings.replay strictly BEFORE game_date).
Nothing is fit on outcomes. Checkpoint = LAST tick with elapsed <= 24.0 (never later).
SEAL -> CHARGE -> compute (Q1/Q2); per-game deltas archived (Q9); two corpus_units through
replication_gate (Q5). Family `ingame_nba_halftime_asof` is NOT frozen (family of one).
Calibration language only. ASCII. Prereg: docs/evidence/harness/S58_TRIALB_PREREG_2026-09-03.md.
Per-file test: python -m pytest tests/platformkit/eval_gate/test_s58_nba_halftime_asof_trial.py -q
"""
from __future__ import annotations

import datetime as dt
import hashlib, json
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.backtest_runner import _charge_ledger
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.family_bars import dual_bar_verdict, render_bars
from scripts.platformkit.eval_gate.pbo import cscv_pbo
from scripts.platformkit.eval_gate.replication_gate import replication_fields
from scripts.platformkit.ingame.nba_checkpoint_benchmark import _elapsed_minutes, price_checkpoint

REPO = Path(__file__).resolve().parents[3]
LEDGER = REPO / "data" / "cache" / "eval_gate" / "backtest_fwer.jsonl"
PREREG = REPO / "docs" / "evidence" / "harness" / "S58_TRIALB_PREREG_2026-09-03.md"
PREREG_SHA256 = "5dbdff4299ccdc29672d65fb9b6495b3981f35a4c9b7e65a909091e496b30ecc"  # sealed first, a6f5e614f
SPEC_ID = "scripts.platformkit.eval_gate.s58_nba_halftime_asof_trial:nba_halftime_asof_v1"
FAMILY, TIER, START, END = "ingame_nba_halftime_asof", "T2", "2024-10-22", "2026-06-13"
BAR, ALPHA, ANCHOR, UNIT_BOUNDARY = 0.004, 0.05, 24.0, "2025-08-01"   # never move (Q3)
ALIASES = {"PHO": "PHX", "WSH": "WAS"}
COUNTS = (1593, 656, 937)                       # checkpoints, unit 2024-25, unit 2025-26; asserted BEFORE the charge
CHECKPOINTS = REPO / "data" / "cache" / "inplay_odds" / "nba_checkpoints_full.parquet"
GAMES = REPO / "data" / "domains" / "basketball_nba" / "games.parquet"


def halftime_checkpoints(df: pd.DataFrame) -> pd.DataFrame:
    """One row per game: the LAST traded tick with elapsed <= ANCHOR; teams parsed + aliased."""
    df = df[df["traded"] == True].copy()  # noqa: E712
    df["elapsed"] = [_elapsed_minutes(int(p), float(c)) for p, c in zip(df["period"], df["game_clock_s"])]
    cp = df[df["elapsed"] <= ANCHOR].sort_values(["game_id", "elapsed", "ts"]).groupby("game_id").tail(1).copy()
    parts = cp["market_ticker"].str.split("-")
    cp["away"] = parts.str[1].str.upper().map(lambda c: ALIASES.get(c, c))
    cp["home"] = parts.str[2].str.upper().map(lambda c: ALIASES.get(c, c))
    cp["unit"] = np.where(pd.to_datetime(cp["game_date"]) < pd.Timestamp(UNIT_BOUNDARY), "2024-25", "2025-26")
    cp["y"] = cp["outcome_home_win"].astype(float)
    assert (cp["elapsed"] <= ANCHOR).all(), "checkpoint past the anchor"
    return cp.sort_values(["game_date", "game_id"]).reset_index(drop=True)


def asof_priors(cp: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """p0 per game = adapter.baseline_probability's formula, replay strictly before game_date."""
    from domains.basketball_nba.adapter import _season_to_int
    from domains.basketball_nba.elo_config import ELO_MEAN
    from domains.basketball_nba.ratings import _p_home, replay
    g = games.copy(); g["season"] = g["season"].apply(_season_to_int)  # noqa: E702
    last_game_date = pd.to_datetime(g["date"]).max().date()
    out = cp.copy(); p0, until, stale = [], [], []  # noqa: E702
    cache: Dict[dt.date, object] = {}
    for _, r in out.iterrows():
        d = pd.Timestamp(r["game_date"]).date()
        if d not in cache: cache[d] = replay(g, until=d)  # noqa: E701
        st = cache[d]
        p0.append(float(_p_home(st.elo.get(str(r["home"]), ELO_MEAN), st.elo.get(str(r["away"]), ELO_MEAN))))
        until.append(d.isoformat()); stale.append(bool(d > last_game_date))  # noqa: E702
    out["p0_asof"], out["elo_until_date"], out["prior_stale"] = p0, until, stale
    return out


def price(cp: pd.DataFrame) -> pd.DataFrame:
    out = cp.copy()
    rows = zip(out["p0_asof"], out["score_home"], out["score_away"], out["period"], out["game_clock_s"])
    out["model"] = [price_checkpoint(p, h, a, per, c) for p, h, a, per, c in rows]
    out["neutral_0.5"] = [price_checkpoint(0.5, h, a, per, c) for h, a, per, c in zip(out["score_home"], out["score_away"], out["period"], out["game_clock_s"])]
    out["p0_only"] = out["p0_asof"]
    out["market"] = out["market_prob"].astype(float)
    out["loss_model"], out["loss_market"] = (out["model"] - out["y"]) ** 2, (out["market"] - out["y"]) ** 2
    out["d"] = out["loss_market"] - out["loss_model"]
    return out


def _ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    order = np.argsort(p); chunks = np.array_split(order, bins)  # noqa: E702
    return float(sum(len(c) * abs(p[c].mean() - y[c].mean()) for c in chunks if len(c)) / len(p))


def _unit_row(sub: pd.DataFrame) -> dict:
    y = sub["y"].to_numpy(); r = diebold_mariano(sub["d"].tolist(), sub["game_id"].astype(str).tolist())  # noqa: E702
    b = {k: float(((sub[k].to_numpy() - y) ** 2).mean()) for k in ("model", "market", "neutral_0.5", "p0_only")}
    return {"n": int(len(sub)), "brier": b, "improvement": b["market"] - b["model"], "dm_stat": float(r.dm_stat),
            "dm_p_raw": float(r.p_value), "dm_ci95": [float(r.ci95[0]), float(r.ci95[1])],
            "replicates": bool(b["market"] - b["model"] >= BAR and r.ci95[0] > 0.0)}


def score(cp: pd.DataFrame, k: int) -> dict:
    pooled = _unit_row(cp)
    units = {u: _unit_row(s) for u, s in cp.groupby("unit")}
    raw_p = pooled["dm_p_raw"]
    bars = dual_bar_verdict(raw_p, k, [raw_p], alpha=ALPHA, family=None)
    bars["bars_line"], bars["family"] = render_bars(bars), FAMILY + " (NOT frozen; family of one)"
    conds = {"improvement_ge_bar": pooled["improvement"] >= BAR, "dm_ci_excludes_0_favouring_model": pooled["dm_ci95"][0] > 0.0,
             "deflated_p_lt_alpha": bool(bars["global_pass"]), "family_bar_pass": bool(bars["family_pass"])}
    verdict = "AHEAD" if all(conds.values()) else ("BEHIND" if pooled["brier"]["model"] > pooled["brier"]["market"] else "NULL")
    n_corpora = sum(1 for u in units.values() if u["replicates"])
    rep = replication_fields(verdict, n_corpora, k)
    y = cp["y"].to_numpy()
    pbo = cscv_pbo(np.column_stack([cp[c].to_numpy() for c in ("model", "neutral_0.5", "p0_only")]), y.astype(int))
    stale = cp[cp["prior_stale"]]
    return {"n_games": int(len(cp)), "k_at_launch": int(k), "pooled": pooled, "units": units, "conditions": conds,
            "verdict_pooled": verdict, "verdict": rep["verdict_replicated"], "replication": rep, "n_corpora": n_corpora,
            "deflated_p": float(bars["deflated_p"]), "bars": bars,
            "ece_10bin": {"model": _ece(cp["model"].to_numpy(), y), "market": _ece(cp["market"].to_numpy(), y)},
            "pbo": {"pbo": float(pbo.pbo), "n_obs": int(pbo.n_obs), "n_splits": int(pbo.n_splits), "configs": ["model", "neutral_0.5", "p0_only"]},
            "prior_stale_slice": ({"n": int(len(stale)), **{k2: v for k2, v in _unit_row(stale).items() if k2 != "n"}} if len(stale) > 1 else {"n": int(len(stale))}),
            "ess_note": "one row per game; each game is its own cluster, n_eff = n_games",
            "tick_informative": {"grain": "event (one row per game at the halftime anchor)",  # S87
                                 "n_events": int(len(cp)), "n_informative": int(len(cp)),
                                 "n_eff": int(len(cp)), "note": "S87: event grain -- one row per game, so no tick can repeat the previous quote; the informative-tick filter does not apply and n_events IS n_informative."}}


def run_trial(cp: pd.DataFrame, games: pd.DataFrame, *, ledger_path: Path, prereg_path: Path = PREREG,
              prereg_sha256: str = PREREG_SHA256, out_path=None, pergame_path=None) -> dict:
    """SEAL -> CHARGE (one row, S13 fields) -> as-of priors -> price -> score. Nothing scored before the row."""
    seal = hashlib.sha256(Path(prereg_path).read_bytes()).hexdigest()
    if seal != prereg_sha256: raise AssertionError("prereg sha mismatch: %s != %s" % (seal, prereg_sha256))  # noqa: E701
    row = _charge_ledger(Path(ledger_path), SPEC_ID, "nba", START, END, family=FAMILY, tier=TIER,
                         hypothesis_hash=hashlib.sha256(SPEC_ID.encode()).hexdigest(), prereg_sha256=seal)
    k = int(row["k_cumulative"])                                       # the ONLY K used
    scored = price(asof_priors(cp, games))
    assert all(pd.Timestamp(u).date() == pd.Timestamp(d).date() for u, d in zip(scored["elo_until_date"], scored["game_date"])), "replay until != game_date"
    res = score(scored, k)
    res.update({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "prereg": str(prereg_path), "prereg_sha256": seal,
                "ledger_row": dict(row), "spec_id": SPEC_ID, "family": FAMILY, "tier": TIER, "anchor_elapsed": ANCHOR,
                "unit_boundary": UNIT_BOUNDARY, "aliases": ALIASES, "per_game_csv": str(pergame_path) if pergame_path else None})
    if pergame_path:
        cols = ["game_id", "game_date", "unit", "home", "away", "elapsed", "score_home", "score_away", "elo_until_date", "prior_stale",
                "p0_asof", "model", "neutral_0.5", "market", "y", "loss_model", "loss_market", "d"]
        with open(pergame_path, "w", encoding="ascii", newline="") as fh:
            fh.write("# prereg_sha256=%s k_at_launch=%d\n" % (seal, k)); scored[cols].to_csv(fh, index=False)  # noqa: E702
    if out_path: Path(out_path).write_text(json.dumps(res, indent=1, sort_keys=True, default=lambda o: o.item() if hasattr(o, "item") else str(o)), "ascii")  # noqa: E701
    return res


def main() -> int:
    """The REAL charged trial B (main repo, canonical ledger). Pre-charge work is counts-only."""
    cp = halftime_checkpoints(pd.read_parquet(CHECKPOINTS))
    games = pd.read_parquet(GAMES)
    codes = set(games["home_team"].astype(str)) | set(games["away_team"].astype(str))
    assert set(cp["home"]) <= codes and set(cp["away"]) <= codes, "unmapped team code"
    assert (len(cp), int((cp["unit"] == "2024-25").sum()), int((cp["unit"] == "2025-26").sum())) == COUNTS, "denominator drift"
    out = REPO / "data" / "cache" / "eval_gate"
    res = run_trial(cp, games, ledger_path=LEDGER, out_path=out / "s58_trialB_nba_halftime_asof_2026-09-03.json",
                    pergame_path=out / "s58_trialB_nba_halftime_asof_pergame_2026-09-03.csv")
    p = res["pooled"]
    print("S58 trialB %s (pooled %s) | model %.15f vs market %.15f | improvement %.6f | dm_ci95 %s | deflated_p %.6g | K %d | n_corpora %d floor %d" % (
        res["verdict"], res["verdict_pooled"], p["brier"]["model"], p["brier"]["market"], p["improvement"], p["dm_ci95"], res["deflated_p"], res["k_at_launch"], res["n_corpora"], res["replication"]["min_corpora_eff"]))
    print(res["bars"]["bars_line"])
    for u, r in res["units"].items(): print("  %s n %d model %.6f market %.6f neutral %.6f p0 %.6f impr %+.6f ci %s p %.3g" % (u, r["n"], r["brier"]["model"], r["brier"]["market"], r["brier"]["neutral_0.5"], r["brier"]["p0_only"], r["improvement"], r["dm_ci95"], r["dm_p_raw"]))
    print("pbo %.3f | ece %s | stale %s" % (res["pbo"]["pbo"], res["ece_10bin"], res["prior_stale_slice"]))
    return 0


if __name__ == "__main__": raise SystemExit(main())  # noqa: E701

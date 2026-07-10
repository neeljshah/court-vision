"""Entry-timing study computations (lane B1).

(a) drift_decomposition -- how much the consensus price still moves from each
    pregame horizon to the close, signed by the eventual close direction.
(b) leadlag_reuse -- REUSES data/frontend/ops/freshness_model_placement.json
    (frozen-model vs contemporaneous market, NBA + tennis); never rebuilt here.
(c) entry_clv -- realized CLV (prob points, within-feed) of actual paper
    entries vs the best-achievable horizon on the same consensus path.
(d) ingame_phase -- NBA in-game: market Brier vs outcome per game phase
    (how much uncertainty remains at each in-game checkpoint).

All CIs are game-clustered bootstrap. CLV / calibration language only --
no ROI or profit claims anywhere in this module.
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from scripts.platformkit.execution.entry_timing.assemble import (
    GAME_MARKETS, HORIZONS, INPLAY, ROOT, close_prob, parse_ts, prob_at,
)

LEDGER = ROOT / "data" / "frontend" / "clv_ledger.jsonl"
PLACEMENT = ROOT / "data" / "frontend" / "ops" / "freshness_model_placement.json"


def cluster_boot_ci(values: list[float], clusters: list, n_boot: int = 500,
                    seed: int = 7) -> tuple[float | None, float | None]:
    """95% CI for the mean, bootstrap resampling whole game clusters."""
    by_c: dict = defaultdict(list)
    for v, c in zip(values, clusters):
        by_c[c].append(v)
    keys = list(by_c)
    if len(keys) < 5:
        return (None, None)
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        samp = [v for k in rng.choices(keys, k=len(keys)) for v in by_c[k]]
        means.append(sum(samp) / len(samp))
    means.sort()
    return (means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1])


def drift_decomposition(paths: dict, horizons=HORIZONS) -> list[dict]:
    """Per horizon: n, mean |p_close - p_h| (pp), signed continuation (pp).

    signed = (p_close - p_h) * sign(p_close - p_earliest): positive means the
    early move tends to CONTINUE toward the close direction after horizon h;
    ~0 means the remaining move is direction-neutral (random-walk-like).
    """
    rows = []
    for h_name, h_s in horizons:
        absm, signed, clusters = [], [], []
        for path in paths.values():
            pc = close_prob(path)
            if pc is None:
                continue
            ph = prob_at(path["ticks"], path["commence"] - h_s)
            pe = prob_at(path["ticks"], path["commence"] - horizons[0][1])
            if pe is None:
                pe = path["ticks"][0][1]
            if ph is None:
                continue
            sign_e = 1.0 if pc >= pe else -1.0
            absm.append(abs(pc - ph) * 100)
            signed.append((pc - ph) * sign_e * 100)
            clusters.append(path["game_id"])
        n = len(absm)
        row = {"horizon": h_name, "n": n}
        if n:
            row["mean_abs_move_pp"] = round(sum(absm) / n, 3)
            row["signed_continuation_pp"] = round(sum(signed) / n, 3)
            lo, hi = cluster_boot_ci(signed, clusters)
            row["signed_ci95"] = [round(lo, 3), round(hi, 3)] if lo is not None else None
        if n < 30:
            row["label"] = "UNDERPOWERED"
        rows.append(row)
    return rows


def leadlag_reuse(placement: Path = PLACEMENT) -> dict:
    """Reuse the existing frozen-model-vs-contemporaneous-price artifact."""
    if not placement.exists():
        return {"status": "MISSING", "source": str(placement)}
    d = json.loads(placement.read_text(encoding="utf-8"))
    out = {"source": "data/frontend/ops/freshness_model_placement.json",
           "edge_claimed": False, "sports": {}}
    for sport, s in (d.get("sports") or {}).items():
        hs = s.get("horizons") or []
        if not hs:
            continue
        beats = [h["horizon"] for h in hs
                 if h.get("delta_ci95") and h["delta_ci95"][1] < 0]
        out["sports"][sport] = {
            "horizons": [{k: h.get(k) for k in
                          ("horizon", "n", "delta_model_minus_market", "delta_ci95")}
                         for h in hs],
            "horizons_model_beats_market": beats,
        }
    return out


def iter_ledger(ledger: Path = LEDGER):
    if not ledger.exists():
        return
    with open(ledger, encoding="utf-8") as fh:
        for line in fh:
            try:
                yield json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue


def entry_clv(paths: dict, sport: str, markets=GAME_MARKETS,
              ledger: Path = LEDGER) -> dict:
    """Realized CLV of actual pregame paper entries vs best-achievable horizon.

    Within-feed only: entry, horizon, and close probs all come from the SAME
    consensus path (cross-venue CLV is basis, not edge). clv_pp > 0 = the
    consensus price moved toward the taken side after entry (beat the close).
    left_on_table_pp = entry prob minus the cheapest horizon-grid prob.
    """
    rows = []
    for r in iter_ledger(ledger):
        if r.get("sport") != sport or r.get("market_type") not in markets:
            continue
        if r.get("taken_book") == "paper_ingame":
            continue
        key = (str(r.get("event_id")), r["market_type"], r.get("side"))
        path = paths.get(key)
        if path is None:
            continue
        t = parse_ts(r.get("ts") or "")
        if t is None or t > path["commence"]:
            continue  # in-game entries are out of scope for close-CLV
        pe, pc = prob_at(path["ticks"], t), close_prob(path)
        if pe is None or pc is None:
            continue
        grid = {h: prob_at(path["ticks"], path["commence"] - s)
                for h, s in HORIZONS}
        grid["last_pregame_tick"] = pc
        grid = {h: p for h, p in grid.items() if p is not None}
        best_h, best_p = min(grid.items(), key=lambda kv: kv[1])
        rows.append({"game": path["game_id"], "clv_pp": (pc - pe) * 100,
                     "left_pp": (pe - best_p) * 100, "best_h": best_h,
                     "lead_h": (path["commence"] - t) / 3600.0})
    n = len(rows)
    out = {"sport": sport, "n": n}
    if n:
        clv = [r["clv_pp"] for r in rows]
        cl = [r["game"] for r in rows]
        lo, hi = cluster_boot_ci(clv, cl)
        leads = sorted(r["lead_h"] for r in rows)
        out.update({
            "mean_clv_pp": round(sum(clv) / n, 3),
            "clv_ci95_pp": [round(lo, 3), round(hi, 3)] if lo is not None else None,
            "mean_left_on_table_pp": round(sum(r["left_pp"] for r in rows) / n, 3),
            "median_entry_lead_h": round(leads[n // 2], 2),
            "best_horizon_histogram": dict(Counter(r["best_h"] for r in rows)),
        })
    if n < 30:
        out["label"] = "UNDERPOWERED"
    return out


def ingame_phase(parquet_name: str = "nba_checkpoints_full.parquet",
                 inplay: Path = INPLAY) -> list[dict]:
    """NBA in-game: market Brier vs outcome per phase (one obs/game/phase)."""
    import pandas as pd
    fp = inplay / parquet_name
    if not fp.exists():
        return []
    df = pd.read_parquet(fp, columns=["game_id", "ts", "period", "game_clock_s",
                                      "market_prob", "outcome_home_win"])
    df = df[df["period"].astype("int64") >= 1]
    per = df["period"].astype("int64").clip(upper=5)
    half = (df["game_clock_s"].fillna(0) >= 360).map({True: "early", False: "late"})
    df["phase"] = per.map(lambda p: "OT" if p >= 5 else f"Q{p}") + "-" + half
    last = df.sort_values("ts").groupby(["game_id", "phase"]).tail(1)
    rows = []
    order = [f"Q{q}-{h}" for q in (1, 2, 3, 4) for h in ("early", "late")] + \
            ["OT-early", "OT-late"]
    for ph in order:
        g = last[last["phase"] == ph]
        if not len(g):
            continue
        err = (g["market_prob"] - g["outcome_home_win"]) ** 2
        rows.append({"phase": ph, "n_games": int(g["game_id"].nunique()),
                     "market_brier": round(float(err.mean()), 4)})
    return rows

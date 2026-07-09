"""Time-sliced PREGAME freshness-premium curve: market accuracy vs time-to-start.

WHAT (user reframe): "when we backtest we compare to live data -- predictions
get better right before games. The Brier, do we know it's accurate?" This module
measures the MARKET's own accuracy as a function of time-to-start (the freshness
premium) so every pregame Brier can be read against the right baseline: the
devigged price AT THE SAME HORIZON, not the (sharper) close.

DECLARED MEASUREMENT (all assumptions explicit):

Corpus:
  data/cache/inplay_odds/<sport>_price_series.parquet. We use KALSHI moneyline
  rows only -- each Kalshi game is a clean 2-sided binary market with per-side
  yes/no settlement and per-game event_key. Polymarket MLB/NBA rows are coarse
  date-bucket keys (e.g. 'mlb-dailies-2023-03-30' spans many games) and are NOT
  per-game sliceable, so they are excluded (counted in notes).

Start-time derivation (per sport, VALIDATED):
  - mlb: parsed from the ticker (KXMLBGAME-26APR26<HHMM>LAAKC = ET first pitch;
    ET->UTC as EDT -4, the MLB season is Apr-Sep). Validated: reconstructed start
    is close_time - 2.85h (median), IQR 2.66-3.10h -- matches ~3h games.
  - nba/wnba/soccer_intl/tennis: tickers carry date only, no time. Start proxy =
    close_time - median_duration (close_time = Kalshi market close ~= game end).
    Duration constants declared in _DURATION_H. This proxy is validated on MLB
    (we HAVE truth there): proxy-vs-ticker MAE is reported in the output. Coarse
    horizons (T-24h..T-1h) are robust to a +-30min start error; T-15m / last-tick
    are proxy-sensitive for non-mlb (flagged proxy_sensitive_horizons).

Devig:
  Two Kalshi sides each carry an implied prob (already 0-1). Where both sides have
  a tick at-or-before the horizon cutoff, we devig ref_prob/(ref_prob+other_prob).
  Where only one side is present we keep the raw single-sided implied prob (a
  binary contract price is already an implied prob). Reference side = the
  alphabetically-first side label (deterministic). outcome = 1 if the ref side
  settled 'yes' else 0. Games are dropped (counted) unless exactly 2 sides both
  settle in {yes,no}.

Horizons (seconds before start): T-24h,12h,6h,3h,1h,15m and last-pregame-tick.
  At each horizon we take the LAST tick AT OR BEFORE (start - horizon). A game
  missing any tick before a cutoff is EXCLUDED from that horizon's pool (counted
  per horizon). Only pregame ticks (ts <= start) are ever used.

Metrics: Brier + log-loss per horizon; game-clustered bootstrap 95% CI (resample
  games with replacement). THE CURVE = Brier vs time-to-start. Plus the open->close
  movement magnitude distribution and where movement concentrates.

Model placement: NO leak-free as-of historical pregame model prob is
  reconstructible on disk without recomputing a dated Elo through gated src/, so
  this is a MARKET-ONLY curve (edge_claimed False). Model crossover is left as a
  queued item -- see 'model_placement' in the output. The curve alone is the
  deliverable the reframe asked for.

Output: data/frontend/ops/freshness_premium_curve.json + a scoreboard_history row.
Run:  python -m scripts.platformkit.ingame.freshness_premium
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
_ODDS = _ROOT / "data" / "cache" / "inplay_odds"
_OUT = _ROOT / "data" / "frontend" / "ops" / "freshness_premium_curve.json"
_HIST = _ROOT / "data" / "frontend" / "ops" / "scoreboard_history.jsonl"

# horizon label -> seconds before start; last-pregame-tick = 0
HORIZONS: list[tuple[str, int]] = [
    ("T-24h", 24 * 3600), ("T-12h", 12 * 3600), ("T-6h", 6 * 3600),
    ("T-3h", 3 * 3600), ("T-1h", 3600), ("T-15m", 15 * 60), ("last_pregame_tick", 0),
]
_MON = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
# median game duration (hours), close_time - duration ~= start; mlb overridden by ticker.
_DURATION_H = {"mlb": 2.85, "nba": 2.30, "wnba": 2.05, "soccer_intl": 2.10, "tennis": 2.20}
_PROXY_SENSITIVE = {"nba", "wnba", "soccer_intl", "tennis"}  # T-15m/last-tick only


def _parse_close(s: str) -> float | None:
    if not isinstance(s, str) or not s:
        return None
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()


def mlb_start_from_ticker(ek: str) -> float | None:
    """ET first pitch embedded in KXMLBGAME-YYMONDDHHMM...; ET->UTC via EDT (-4)."""
    m = re.match(r"KXMLBGAME-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})", ek or "")
    if not m:
        return None
    yy, mon, dd, hh, mm = int(m[1]), _MON.get(m[2], 0), int(m[3]), int(m[4]), int(m[5])
    if not mon:
        return None
    naive = dt.datetime(2000 + yy, mon, dd, hh, mm, tzinfo=dt.timezone.utc)
    return (naive + dt.timedelta(hours=4)).timestamp()  # EDT local->UTC


def _game_start(sport: str, ek: str, close_ts: float | None) -> float | None:
    if sport == "mlb":
        s = mlb_start_from_ticker(ek)
        if s is not None:
            return s
    if close_ts is None:
        return None
    return close_ts - _DURATION_H.get(sport, 2.5) * 3600.0


def _last_at_or_before(ts: np.ndarray, prob: np.ndarray, cutoff: float) -> float | None:
    """LAST tick with ts <= cutoff (ts assumed ascending). None if none exist."""
    i = int(np.searchsorted(ts, cutoff, side="right")) - 1
    return float(prob[i]) if i >= 0 else None


def load_games(sport: str) -> tuple[list[dict], dict]:
    """Return per-game records + a diagnostics dict (exclusion counts)."""
    p = _ODDS / f"{sport}_price_series.parquet"
    df = pd.read_parquet(p, columns=["venue", "event_key", "market_type", "side",
                                     "ts", "prob", "close_time", "result_where_known"])
    total_rows = len(df)
    df = df[(df.venue == "kalshi") & (df.market_type == "moneyline")]
    df = df.dropna(subset=["event_key"])
    diag = {"total_rows": int(total_rows), "kalshi_ml_rows": int(len(df)),
            "polymarket_excluded": bool((df.venue == "polymarket").sum() == 0 and total_rows > len(df)),
            "games_seen": int(df.event_key.nunique()), "games_no_start": 0,
            "games_bad_sides": 0, "games_kept": 0, "start_source": "ticker" if sport == "mlb" else "close_minus_duration"}
    games: list[dict] = []
    for ek, g in df.groupby("event_key", sort=False):
        close_ts = _parse_close(g.close_time.iloc[0])
        start = _game_start(sport, ek, close_ts)
        if start is None:
            diag["games_no_start"] += 1
            continue
        sides = sorted(s for s in g.side.dropna().unique())
        res = g.groupby("side").result_where_known.last().to_dict()
        if len(sides) != 2 or any(res.get(s) not in ("yes", "no") for s in sides):
            diag["games_bad_sides"] += 1
            continue
        ref, other = sides[0], sides[1]
        outcome = 1 if res[ref] == "yes" else 0
        pre = g[g.ts <= start]
        rg = pre[pre.side == ref].sort_values("ts")
        og = pre[pre.side == other].sort_values("ts")
        if rg.empty:
            diag["games_bad_sides"] += 1
            continue
        games.append({
            "event_key": ek, "start": start, "close": close_ts, "outcome": outcome,
            "ref_ts": rg.ts.to_numpy(), "ref_p": rg.prob.to_numpy(),
            "oth_ts": og.ts.to_numpy(), "oth_p": og.prob.to_numpy(),
        })
    diag["games_kept"] = len(games)
    return games, diag


def _devig(ref: float | None, oth: float | None) -> float | None:
    if ref is None:
        return None
    if oth is None or (ref + oth) <= 0:
        return ref  # raw single-sided implied prob
    return ref / (ref + oth)


def _bootstrap_ci(probs: np.ndarray, outs: np.ndarray, b: int = 1000, seed: int = 0) -> tuple[float, float]:
    """Game-clustered bootstrap 95% CI on mean Brier (each game = one sample)."""
    if len(probs) < 3:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    n = len(probs)
    se = (probs - outs) ** 2
    means = [se[rng.integers(0, n, n)].mean() for _ in range(b)]
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def curve_for_sport(sport: str) -> dict:
    games, diag = load_games(sport)
    rows = []
    # movement anchors: devig prob at each horizon per game (for open->close movement)
    per_game_h: dict[str, list[float | None]] = {lbl: [] for lbl, _ in HORIZONS}
    for lbl, sec in HORIZONS:
        probs, outs = [], []
        for gm in games:
            cutoff = gm["start"] - sec
            r = _last_at_or_before(gm["ref_ts"], gm["ref_p"], cutoff)
            o = _last_at_or_before(gm["oth_ts"], gm["oth_p"], cutoff) if len(gm["oth_ts"]) else None
            dv = _devig(r, o)
            per_game_h[lbl].append(dv)
            if dv is None:
                continue
            dv = min(max(dv, 1e-6), 1 - 1e-6)
            probs.append(dv)
            outs.append(gm["outcome"])
        probs, outs = np.asarray(probs), np.asarray(outs)
        n = len(probs)
        if n == 0:
            rows.append({"horizon": lbl, "n": 0, "brier": None, "log_loss": None,
                         "ci95": [None, None], "excluded": len(games)})
            continue
        brier = float(np.mean((probs - outs) ** 2))
        ll = float(-np.mean(outs * np.log(probs) + (1 - outs) * np.log(1 - probs)))
        lo, hi = _bootstrap_ci(probs, outs)
        rows.append({"horizon": lbl, "n": int(n), "brier": round(brier, 5),
                     "log_loss": round(ll, 5), "ci95": [round(lo, 5), round(hi, 5)],
                     "excluded": int(len(games) - n)})
    # movement: |last_pregame - T-24h| per game where both exist; and per-interval abs delta
    move = _movement(per_game_h)
    note = {"edge_claimed": False, "market_only": True,
            "start_source": diag["start_source"]}
    if sport in _PROXY_SENSITIVE:
        note["proxy_sensitive_horizons"] = ["T-15m", "last_pregame_tick"]
    return {"sport": sport, "diagnostics": diag, "horizons": rows,
            "movement": move, "notes": note}


def _movement(per_game_h: dict[str, list[float | None]]) -> dict:
    labels = [l for l, _ in HORIZONS]
    close = per_game_h["last_pregame_tick"]
    open24 = per_game_h["T-24h"]
    tot = [abs(c - o) for c, o in zip(close, open24) if c is not None and o is not None]
    per_int = {}
    for a, b in zip(labels[:-1], labels[1:]):
        pa, pb = per_game_h[a], per_game_h[b]
        d = [abs(y - x) for x, y in zip(pa, pb) if x is not None and y is not None]
        if d:
            per_int[f"{a}->{b}"] = {"mean_abs_move": round(float(np.mean(d)), 5), "n": len(d)}
    where = max(per_int, key=lambda k: per_int[k]["mean_abs_move"]) if per_int else None
    return {"open24_to_close_abs": {
                "mean": round(float(np.mean(tot)), 5) if tot else None,
                "median": round(float(np.median(tot)), 5) if tot else None,
                "p90": round(float(np.percentile(tot, 90)), 5) if tot else None, "n": len(tot)},
            "per_interval_mean_abs_move": per_int,
            "most_movement_interval": where}


def proxy_validation() -> dict:
    """Validate the close-minus-duration start proxy on MLB, where we have ticker truth.

    Reconstruct MLB start via the proxy (close - 2.85h) and compare to the
    ticker-embedded first pitch. Reports MAE / p90 in minutes.
    """
    df = pd.read_parquet(_ODDS / "mlb_price_series.parquet",
                         columns=["venue", "event_key", "market_type", "close_time"])
    df = df[(df.venue == "kalshi") & (df.market_type == "moneyline")].dropna(subset=["event_key"])
    errs = []
    for ek, ct in df.groupby("event_key").close_time.first().items():
        truth = mlb_start_from_ticker(ek)
        close_ts = _parse_close(ct)
        if truth is None or close_ts is None:
            continue
        proxy = close_ts - _DURATION_H["mlb"] * 3600.0
        errs.append(abs(proxy - truth) / 60.0)
    e = np.asarray(errs)
    return {"n": int(len(e)), "mae_min": round(float(e.mean()), 1),
            "p90_min": round(float(np.percentile(e, 90)), 1),
            "note": "proxy start error on MLB truth; coarse horizons (>=T-1h) robust to this."}


def build(sports: list[str] | None = None) -> dict:
    sports = sports or ["mlb", "nba", "wnba", "soccer_intl", "tennis"]
    out = {"generated_at": "STABLE", "benchmark_name": "freshness_premium_curve",
           "edge_claimed": False, "market_only": True,
           "model_placement": "QUEUED: no leak-free as-of pregame model prob on disk; "
                              "market-only curve. Crossover horizon requires a dated leak-free "
                              "Elo backtest (gated src/) -- see human queue.",
           "sports": {}}
    try:
        out["start_proxy_validation_on_mlb"] = proxy_validation()
    except Exception as e:
        out["start_proxy_validation_on_mlb"] = {"error": str(e)}
    for sp in sports:
        try:
            out["sports"][sp] = curve_for_sport(sp)
        except Exception as e:  # a missing/odd parquet must not sink the whole run
            out["sports"][sp] = {"sport": sp, "error": str(e)}
    return out


def main() -> None:
    res = build()
    pv = res.get("start_proxy_validation_on_mlb", {})
    print(f"start-proxy validation on MLB truth: MAE {pv.get('mae_min')}min  p90 {pv.get('p90_min')}min\n")
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(res, indent=2), encoding="ascii")
    hist_row = {"generated_at": "STABLE", "benchmark_name": "freshness_premium_curve",
                "edge_claimed": False,
                "summary": {sp: {"kept": r.get("diagnostics", {}).get("games_kept"),
                                 "close_brier": next((h["brier"] for h in r.get("horizons", [])
                                                      if h["horizon"] == "last_pregame_tick"), None)}
                            for sp, r in res["sports"].items()}}
    with _HIST.open("a", encoding="ascii") as fh:
        fh.write(json.dumps(hist_row) + "\n")
    for sp, r in res["sports"].items():
        if "error" in r:
            print(f"{sp}: ERROR {r['error']}")
            continue
        d = r["diagnostics"]
        print(f"=== {sp}  kept {d['games_kept']}/{d['games_seen']} games (start={d['start_source']}) ===")
        for h in r["horizons"]:
            print(f"  {h['horizon']:>17}  n={h['n']:>4}  brier={h['brier']}  ci95={h['ci95']}  ll={h['log_loss']}")
        mv = r["movement"]
        print(f"  open24->close abs move: mean={mv['open24_to_close_abs']['mean']}  "
              f"most movement: {mv['most_movement_interval']}")
    print(f"wrote {_OUT}")


if __name__ == "__main__":
    main()

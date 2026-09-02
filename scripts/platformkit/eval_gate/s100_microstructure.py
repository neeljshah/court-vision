"""S100 -- order-book microstructure on the scored MLB ticks (STEP 0 PREMISE + descriptive).

Premise: that the depth stores overlap the scored MLB ticks richly enough to build tick-time
features.  Measured at TICK grain (not ticker grain) on the SCREEN side of the S82 partition --
the side an arm would use -- it does not survive, so the row's STEP 0 stop rule fires and only
the descriptive next-tick-sign table is produced.  NO arm, NO outcome Brier, NO recal null, NO
seal, NO charge, NO K read.  Only `depth_history` carries per-level ladders, and its `yes_asks`
is the RAW Kalshi `no_dollars` ladder (depth_capture.py:130), so imbalance at the touch is
derivable there and only there.  `ingame_grade/mlb` carries the KEYS spread_bp / book_thinness
/ stale_quote on 25,585 rows but every VALUE is null, so it is not a substrate.  A CENSUS IS A
NON-FINDING.  Calibration language only.  ASCII only.
Per-file test: python -m pytest tests/platformkit/ingame/test_s100_microstructure.py -q
"""
from __future__ import annotations

import bisect
import datetime as dt
import glob
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.foundry.tiers import partition_corpus

REPO = Path(__file__).resolve().parents[3]
JOINED = REPO / "data" / "cache" / "ingame_grade_joined" / "mlb"
BOOK = REPO / "data" / "cache" / "book_depth" / "_archive" / "kalshi"
TRADES = REPO / "data" / "cache" / "book_depth" / "_archive" / "kalshi_trades"
DEPTH_HISTORY = REPO / "data" / "cache" / "depth_history" / "mlb"
OUT_DIR = REPO / "data" / "cache" / "eval_gate"
STEM = "s100_microstructure_2026-09-03"

SERIES = "KXMLBGAME-"
MIN_GAMES_TO_ARM = 20        # the row's own STEP 0 stop rule; NEVER lowered (Q3)
IMPROVEMENT_BAR = 0.004      # the in-game bar the arm would have faced; NEVER lowered (Q3)
FRESHNESS_CAPS = (60, 300)   # seconds a feature row may predate the tick
FLOW_WINDOWS = (60, 300)     # signed trade-flow windows named by the row
FEATURES = ("depth_imbalance", "spread_bp", "last_trade_dir", "flow_60", "flow_300")
DIRECTIONAL = ("depth_imbalance", "last_trade_dir", "flow_60", "flow_300")
SPEC = {
    "spec_id": "scripts.platformkit.eval_gate.s100_microstructure:mlb_microstructure_asof_v1",
    "sport": "mlb", "tier": "STEP 0 PREMISE + descriptive (uncharged, no seal, no K read)",
    "label": "SINGLE-WINDOW", "edge_claimed": False,
    "min_games_to_arm": MIN_GAMES_TO_ARM, "improvement_bar": IMPROVEMENT_BAR,
    "features": "home-oriented, read strictly before the tick: depth_imbalance = (size at best "
                "YES bid - size at best YES ask) / their sum from the depth_history ladders; "
                "spread_bp / book_thinness / stale_quote = the last book_depth snapshot; "
                "last_trade_dir = +1 yes / -1 no; flow_w = the signed trade COUNT in (t-w, t), "
                "never a size (`count` null on 2.8 pct of rows)"}


class AsOfLeak(ValueError):
    """A microstructure row at or after the tick's own timestamp reached a feature."""


def _rows(directory: Path) -> Iterable[dict]:      # every object in a jsonl dir, name order
    for path in sorted(glob.glob(str(Path(directory) / "*.jsonl"))):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def epoch(stamp: Any) -> float:
    """UTC seconds for an ISO stamp; the stores mix `Z` and fractional seconds."""
    return dt.datetime.fromisoformat(str(stamp).replace("Z", "")).replace(
        tzinfo=dt.timezone.utc).timestamp()


def as_of(series: Sequence[tuple], when: float, max_age: float) -> Optional[tuple]:
    """The last (ts, payload) STRICTLY before `when` and no older than `max_age`.  THE guard:
    a row stamped AT the tick is a future read, so a feature never sees its own quote."""
    index = bisect.bisect_left(series, when, key=lambda row: row[0])
    if index == 0:
        return None
    stamp, payload = series[index - 1]
    if stamp >= when:
        raise AsOfLeak("as_of returned a row at or after the tick (%r >= %r)" % (stamp, when))
    return (stamp, payload) if when - stamp <= max_age else None


def touch_imbalance(yes_bids: Sequence[Sequence], yes_asks: Sequence[Sequence]) -> Optional[float]:
    """Size imbalance at the touch in [-1, 1]; `yes_asks` is the raw NO ladder."""
    if not yes_bids or not yes_asks:
        return None
    top = lambda ladder: float(max(ladder, key=lambda level: float(level[0]))[1])
    bid, ask = top(yes_bids), top(yes_asks)
    return (bid - ask) / (bid + ask) if bid + ask > 0 else None


def home_side(event: str, suffixes: Iterable[str]) -> Optional[str]:
    """The market-ticker suffix that is the HOME team (Kalshi names events <away><home>); a
    doubleheader's trailing G1/G2 is stripped first.  None when no unique home code."""
    blob = re.sub(r"G\d+$", "", str(event).split("-")[-1])
    matches = sorted({s for s in suffixes if blob.endswith(str(s)) and blob != str(s)})
    return matches[0] if len(matches) == 1 else None


def load_scored_ticks(joined: Path = JOINED) -> pd.DataFrame:
    """Scored ticks (settled outcome + in-play market line) with the NEXT market move."""
    frame = pd.DataFrame([
        {"game": str(r["game_id"]), "ts": str(r["ts"]), "market": float(r["market_prob"]),
         "y": float(r["outcome"])} for r in _rows(joined)
        if r.get("outcome") is not None and r.get("market_prob") is not None])
    if frame.empty:
        return frame
    frame["t"] = frame["ts"].map(epoch)
    frame = frame.sort_values(["game", "t"], kind="mergesort").reset_index(drop=True)
    frame["next_market"] = frame.groupby("game", sort=False)["market"].shift(-1)
    frame["d_market"] = frame["next_market"] - frame["market"]
    frame["date"] = frame["ts"].str[:10]
    return frame


def _series_by_ticker(records: Iterable[dict], ts_field: str, payload) -> Dict[str, List[tuple]]:
    out: Dict[str, List[tuple]] = {}
    for r in records:
        if str(r.get("ticker") or "").startswith(SERIES):
            out.setdefault(r["ticker"], []).append((epoch(r[ts_field]), payload(r)))
    return {k: sorted(v, key=lambda row: row[0]) for k, v in out.items()}


def load_stores(book: Path = BOOK, trades: Path = TRADES, depth: Path = DEPTH_HISTORY):
    """The three per-market-ticker timelines, each sorted by its own stamp."""
    mlb = lambda d: (r for r in _rows(d) if r.get("sport") == "mlb")
    return (_series_by_ticker(mlb(book), "ts", lambda r: (r.get("spread_bp"),
                r.get("book_thinness"), r.get("stale_quote_flag"))),
            _series_by_ticker(mlb(trades), "trade_ts", lambda r: (
                1.0 if str(r.get("taker_side")).lower() == "yes" else -1.0)),
            _series_by_ticker(_rows(depth), "ts", lambda r: touch_imbalance(
                r.get("yes_bids") or [], r.get("yes_asks") or [])))


def ticker_map(*stores: Dict[str, List[tuple]]) -> Dict[str, Dict[str, str]]:
    """event_ticker -> {"home": market ticker, "away": market ticker} where resolvable."""
    seen: Dict[str, set] = {}
    for ticker in [t for store in stores for t in store]:
        seen.setdefault(ticker.rsplit("-", 1)[0], set()).add(ticker.rsplit("-", 1)[1])
    resolved = {e: (home_side(e, ss), ss) for e, ss in seen.items()}
    return {e: {k: "%s-%s" % (e, v) for k, v in (("home", h),
                ("away", next((s for s in sorted(ss) if s != h), None))) if v}
            for e, (h, ss) in resolved.items() if h}


def _oriented(store: Dict[str, List[tuple]], sides: Dict[str, str]):
    """(timeline, sign) for the home ticker if captured, else the away ticker flipped."""
    for side, sign in (("home", 1.0), ("away", -1.0)):
        ticker = sides.get(side)
        if ticker and store.get(ticker):
            return store[ticker], sign
    return None, 0.0


def attach_features(ticks: pd.DataFrame, quotes, flow, ladders, sides_by_event,
                    max_age: float) -> pd.DataFrame:
    """As-of microstructure features, every one read STRICTLY before the tick."""
    out = ticks.copy()
    columns = ["depth_imbalance", "spread_bp", "book_thinness", "stale_quote", "last_trade_dir",
               "imbalance_age_s", "quote_age_s"] + ["flow_%d" % w for w in FLOW_WINDOWS]
    values, order = {name: [] for name in columns}, []   # type: Dict[str, List[Any]], List[Any]
    for game, block in out.groupby("game", sort=False):
        order.extend(block.index)
        sides = sides_by_event.get(game, {})   # {} -> every feature is None for this game
        ladder, l_sign = _oriented(ladders, sides)
        quote = _oriented(quotes, sides)[0]
        trade, t_sign = _oriented(flow, sides)
        for when in block["t"]:
            hit = as_of(ladder, when, max_age) if ladder else None
            values["depth_imbalance"].append(
                None if hit is None or hit[1] is None else l_sign * float(hit[1]))
            values["imbalance_age_s"].append(None if hit is None else when - hit[0])
            hit = as_of(quote, when, max_age) if quote else None
            for i, name in enumerate(("spread_bp", "book_thinness", "stale_quote")):
                values[name].append(None if hit is None else hit[1][i])
            values["quote_age_s"].append(None if hit is None else when - hit[0])
            hit = as_of(trade, when, max_age) if trade else None
            values["last_trade_dir"].append(None if hit is None else t_sign * float(hit[1]))
            for w in FLOW_WINDOWS:
                signed = [x for stamp, x in trade if when - w < stamp < when] if trade else []
                values["flow_%d" % w].append(t_sign * float(sum(signed)) if signed else None)
    return out.join(pd.DataFrame(values, index=order))   # index-keyed: group order is irrelevant


def sign_accuracy(frame: pd.DataFrame, feature: str) -> Dict[str, Any]:
    """Does sign(feature) call the sign of the market's NEXT move? Game-clustered CI vs 0.50."""
    sub = frame[frame[feature].fillna(0).ne(0) & frame["d_market"].fillna(0).ne(0)]
    row: Dict[str, Any] = {"n": int(len(sub)), "n_games": int(sub["game"].nunique()),
        "n_zero_move_dropped": int((frame[feature].notna() & (frame["d_market"] == 0)).sum())}
    if row["n_games"] < 2:
        return dict(row, accuracy=None, ci95_minus_half=None, absent_because="< 2 clusters")
    correct = (sub[feature].gt(0) == sub["d_market"].gt(0)).astype(float)
    dm = diebold_mariano((correct - 0.5).tolist(), sub["game"].astype(str).tolist())
    return dict(row, accuracy=float(correct.mean()), p_value=float(dm.p_value),
                ci95_minus_half=[float(dm.ci95[0]), float(dm.ci95[1])],
                excludes_half=bool(dm.ci95[0] > 0.0 or dm.ci95[1] < 0.0))


def screen_side(frame: pd.DataFrame, seed: int = 0):
    """S82 rule: foundry partition on game blocks -> SCREEN-side rows and the record."""
    states = [{"game_id": g, "corpus_unit": g, "state_ts": d + "T00:00:00"}
              for g, d in frame.groupby("game")["date"].min().items()]
    part = partition_corpus(states, seed=seed)
    return frame[frame["game"].isin(part.screen_ids)].reset_index(drop=True), {
        "basis": part.basis, "seed": part.seed, "screen_sha256": part.screen_sha256,
        "verdict_sha256": part.verdict_sha256, "n_screen_games": len(part.screen_ids),
        "n_verdict_games": len(part.verdict_ids)}


def premise(ticks: pd.DataFrame, featured: Dict[int, pd.DataFrame],
            screened: Dict[int, pd.DataFrame], partition: Dict[str, Any],
            quotes, flow, ladders, sides_by_event) -> Dict[str, Any]:
    """STEP 0: rows, tickers, time ranges, and the exact tick-grain overlap per store."""
    def coverage(frames):
        """Per freshness cap, the ticks and GAMES that actually carry each as-of feature."""
        return {str(c): {n: {"n_ticks": int(f[n].notna().sum()),
                             "n_games": int(f.loc[f[n].notna(), "game"].nunique())}
                         for n in FEATURES} for c, f in sorted(frames.items())}

    def store_block(store, label):
        stamps = [s for values in store.values() for s, _ in values] or [0.0]
        events = {t.rsplit("-", 1)[0] for t in store}
        iso = lambda v: dt.datetime.utcfromtimestamp(v).isoformat()
        return {"store": label, "n_rows": int(sum(len(v) for v in store.values())),
                "n_market_tickers": len(store), "n_event_tickers": len(events),
                "ts_min": iso(min(stamps)), "ts_max": iso(max(stamps)),
                "n_events_sharing_a_scored_game": len(events & set(ticks["game"]))}
    return {"scored_ticks": {"path": str(JOINED), "n_ticks": int(len(ticks)),
                             "n_games": int(ticks["game"].nunique()),
                             "ts_min": ticks["ts"].min(), "ts_max": ticks["ts"].max()},
            "stores": [store_block(quotes, "book_depth/_archive/kalshi"),
                       store_block(flow, "book_depth/_archive/kalshi_trades"),
                       store_block(ladders, "depth_history/mlb")],
            "home_side_resolved_events": len(sides_by_event),
            "screen_partition": partition,
            "tick_grain_coverage_by_freshness_cap_s": coverage(featured),
            "screen_side_coverage_by_freshness_cap_s": coverage(screened)}


def run(out_dir: Path = OUT_DIR, stem: str = STEM, ticks: Optional[pd.DataFrame] = None) -> dict:
    scored = load_scored_ticks() if ticks is None else ticks
    quotes, flow, ladders = load_stores()
    sides_by_event = ticker_map(quotes, flow, ladders)
    featured = {cap: attach_features(scored, quotes, flow, ladders, sides_by_event, cap)
                for cap in FRESHNESS_CAPS}
    screen, partition = screen_side(scored)
    census = premise(scored, featured, {c: f[f["game"].isin(set(screen["game"]))]
                                        for c, f in featured.items()},
                     partition, quotes, flow, ladders, sides_by_event)
    tables = {str(cap): {name: sign_accuracy(f, name) for name in DIRECTIONAL}
              for cap, f in sorted(featured.items())}
    best = max((c["n_games"] for cap in census["screen_side_coverage_by_freshness_cap_s"].values()
                for c in cap.values()), default=0)
    summary: Dict[str, Any] = dict(
        SPEC, generated_at=dt.datetime.now(dt.timezone.utc).isoformat(), next_tick_sign=tables,
        premise=census, max_games_screen_side=best, arm_run=False, prereg_draft_warranted=False,
        stop_rule="STEP 0: fewer than %d SCREEN-side games carry an as-of feature -- descriptive "
                  "only, no arm, no outcome Brier, no recal null, no charge" % MIN_GAMES_TO_ARM,
        verdict="PREMISE FALSIFIED AT TICK GRAIN" if best < MIN_GAMES_TO_ARM else "BUILDABLE")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    keep = ["game", "ts", "date", "market", "next_market", "d_market", "y", "book_thinness",
            "stale_quote", "imbalance_age_s", "quote_age_s", "freshness_cap_s"] + list(FEATURES)
    series = pd.concat([featured[c].assign(freshness_cap_s=c, is_screen=featured[c]["game"].isin(
        set(screen["game"]))) for c in sorted(featured)], ignore_index=True)
    series = series[series[list(FEATURES)].notna().any(axis=1)]
    csv = Path(out_dir) / (stem + "_series.csv")                                          # Q9
    series.assign(cluster_id=series["game"])[keep + ["is_screen", "cluster_id"]].to_csv(
        csv, index=False, encoding="ascii")
    summary["per_tick_series"] = str(csv)
    (Path(out_dir) / (stem + ".json")).write_text(
        json.dumps(summary, indent=1, sort_keys=True, default=str), encoding="ascii")
    return summary


def main() -> int:
    s = run()
    p, t = s["premise"], s["premise"]["scored_ticks"]
    print("SCORED %(n_ticks)d ticks / %(n_games)d games %(ts_min)s..%(ts_max)s" % t)
    for b in p["stores"]:
        print("  %(store)-34s rows %(n_rows)8d tickers %(n_market_tickers)5d events "
              "%(n_event_tickers)4d %(ts_min)s..%(ts_max)s shared "
              "%(n_events_sharing_a_scored_game)d" % b)
    for side in ("tick_grain", "screen_side"):
        for cap, block in sorted(p[side + "_coverage_by_freshness_cap_s"].items()):
            for name, cell in sorted(block.items()):
                g = s["next_tick_sign"][cap].get(name, {}) if side == "tick_grain" else {}
                print("  %-10s cap %4ss %-16s ticks %6d games %3d | sign n %5d acc %s ci %s" % (
                    side, cap, name, cell["n_ticks"], cell["n_games"], g.get("n", 0),
                    g.get("accuracy"), g.get("ci95_minus_half")))
    print("%s | %s | max SCREEN games any feature %d (bar %d) | arm_run %s" % (
        s["verdict"], p["screen_partition"]["screen_sha256"][:12], s["max_games_screen_side"],
        MIN_GAMES_TO_ARM, s["arm_run"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

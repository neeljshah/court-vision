"""Price-path assembler for the entry-timing study (lane B1).

Two corpora, one path shape:
  1) line_history: data/cache/line_history/<sport>/*.jsonl -- multi-book
     devigged quotes.  Consensus path = median devigged_prob across books in
     5-minute capture bins, per (game_id, market_type, side); spread/total
     paths are built per line and the modal line is kept.
  2) NBA parquet: data/cache/inplay_odds/nba_price_series.parquet with tip
     times joined EXACTLY from the checkpoints parquets (first in-game tick
     per event ticker) -- no heuristic tip inference.

Order-time discipline: prob_at() only looks backward (last tick <= t) and
consensus ticks are stamped at their bin END, so nothing peeks forward.
NBA line_history stale-repeat corruption (pre-b18ab45b): stale games are
re-broadcast weeks after commence -- killed by the [commence-LOOKBACK,
commence] window filter.
"""
from __future__ import annotations

import json
import statistics
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LINE_HISTORY = ROOT / "data" / "cache" / "line_history"
INPLAY = ROOT / "data" / "cache" / "inplay_odds"

BIN_S = 300
LOOKBACK_S = 30 * 3600  # widest horizon (24h) + slack
GAME_MARKETS = ("moneyline", "spread", "total")
HORIZONS = [
    ("T-24h", 86400), ("T-12h", 43200), ("T-6h", 21600), ("T-3h", 10800),
    ("T-1h", 3600), ("T-30m", 1800), ("T-10m", 600),
]


def parse_ts(s: str) -> float | None:
    """ISO timestamp (with 'Z' or offset, minutes-only ok) -> epoch seconds."""
    if not s:
        return None
    try:
        s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def prob_at(ticks: list[tuple[float, float]], t: float) -> float | None:
    """Last consensus prob at or before t (order-time only). ticks sorted."""
    i = bisect_right(ticks, (t, float("inf")))
    return ticks[i - 1][1] if i else None


def close_prob(path: dict) -> float | None:
    return prob_at(path["ticks"], path["commence"])


def assemble_line_history(sport: str, markets=GAME_MARKETS, max_days: int | None = None,
                          root: Path = LINE_HISTORY, stats: dict | None = None) -> dict:
    """Return {(game_id, market_type, side): path} consensus pregame paths.

    path = {game_id, market_type, side, line, commence, ticks:[(t, prob)...]}
    stats (optional dict) collects drop-reason counters for honest reporting.
    """
    files = sorted((root / sport).glob("*.jsonl"))
    if max_days:
        files = files[-max_days:]
    st = stats if stats is not None else {}
    for k in ("rows", "no_devig", "no_commence", "out_of_window"):
        st.setdefault(k, 0)
    bins: dict[tuple, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    commences: dict[str, float] = {}
    for fp in files:
        with open(fp, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if r.get("market_type") not in markets:
                    continue
                st["rows"] += 1
                if r.get("devigged_prob") is None:
                    st["no_devig"] += 1
                    continue
                gid = str(r.get("game_id"))
                cm = commences.get(gid)
                if cm is None:
                    cm = parse_ts(r.get("commence_time") or "")
                    if cm is None:
                        st["no_commence"] += 1
                        continue
                    commences[gid] = cm
                t = parse_ts(r.get("captured_at") or "")
                # stale-repeat + pregame window: quotes outside it are dropped
                if t is None or not (cm - LOOKBACK_S <= t <= cm):
                    st["out_of_window"] += 1
                    continue
                key = (gid, r["market_type"], r.get("side"), r.get("line"))
                bins[key][int(t // BIN_S)].append(float(r["devigged_prob"]))
    # pick modal line per (game, market, side) = the line with most bins
    best: dict[tuple, tuple] = {}
    for key, b in bins.items():
        short = key[:3]
        if short not in best or len(b) > len(bins[best[short]]):
            best[short] = key
    paths = {}
    for short, key in best.items():
        gid, mkt, side, ln = key
        ticks = sorted(((bn + 1) * BIN_S, statistics.median(v))
                       for bn, v in bins[key].items())
        if len(ticks) < 2:
            continue
        paths[short] = {"game_id": gid, "market_type": mkt, "side": side,
                        "line": ln, "commence": commences[gid], "ticks": ticks}
    return paths


def _event_key_of(ticker: str) -> str:
    return ticker.rsplit("-", 1)[0] if ticker.startswith("KX") else ticker


def load_nba_tips(inplay: Path = INPLAY) -> dict[str, float]:
    """{event_key: tip epoch s} = first in-game tick from checkpoints parquets."""
    import pandas as pd
    tips: dict[str, float] = {}
    for name in ("nba_checkpoints_full.parquet", "nba_checkpoints_2025_26_playoffs.parquet"):
        fp = inplay / name
        if not fp.exists():
            continue
        df = pd.read_parquet(fp, columns=["market_ticker", "ts"])
        g = df.groupby("market_ticker")["ts"].min()
        for tk, ts in g.items():
            ek = _event_key_of(str(tk))
            v = float(ts)
            if ek not in tips or v < tips[ek]:
                tips[ek] = v
    return tips


def assemble_nba_parquet(inplay: Path = INPLAY) -> dict:
    """NBA pregame paths from the kalshi/polymarket tick series parquet.

    Only events whose tip time is exactly known from the checkpoints parquets.
    One path per event (the venue x side series with the most pregame ticks).
    Keys: (event_key, 'moneyline', side).
    """
    import pandas as pd
    fp = inplay / "nba_price_series.parquet"
    if not fp.exists():
        return {}
    tips = load_nba_tips(inplay)
    df = pd.read_parquet(fp, columns=["event_key", "venue", "market_type", "side",
                                      "ts", "prob"])
    df = df[df["market_type"] == "moneyline"]
    df = df[df["event_key"].isin(tips)]
    df["tip"] = df["event_key"].map(tips)
    df = df[df["ts"].astype("int64") <= df["tip"]]  # pregame ticks only
    paths: dict = {}
    counts: dict[str, int] = {}
    for (ek, venue, side), g in df.groupby(["event_key", "venue", "side"]):
        n = len(g)
        if n < 2 or counts.get(ek, 0) >= n:
            continue
        counts[ek] = n
        ticks = sorted(zip(g["ts"].astype("int64").astype(float), g["prob"].astype(float)))
        paths[ek] = {"game_id": ek, "market_type": "moneyline", "side": str(side),
                     "line": None, "commence": tips[ek], "ticks": ticks,
                     "venue": str(venue)}
    return {(p["game_id"], "moneyline", p["side"]): p for p in paths.values()}

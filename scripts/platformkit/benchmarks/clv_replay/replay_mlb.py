"""scripts.platformkit.benchmarks.clv_replay.replay_mlb -- CLV REPLAY benchmark
(MLB totals): for every pregame snapshot in our own scraped line-history feed,
score the probability-space CLV a hypothetical bet on that snapshot would have
"had" versus that SAME book's own final pregame (close) snapshot.

HONESTY FRAME (binding, see .claude/rules/no-edge-claims.md): CLV here is a
probability-space ANTICIPATION-of-the-close diagnostic, not a dollar figure.
Positive CLV does NOT imply positive expected value against the true outcome
distribution -- it only says the snapshot's fair prob moved toward the close.
No outcome/PnL is ever computed. edge_claimed is always False.

DEVIG REUSE (binding -- ladder rung 2, "already in this codebase"): every raw
row already carries `devigged_prob`, and scripts.platformkit.odds_provider.
markets._devig_pair computes that exact field via odds_shop.devig_twoway
(verified live in markets.py: `fa, fb = devig_twoway(price_a, price_b)`,
returns (None, None) on a missing leg or exception). Re-devigging here would
duplicate that call for an identical result, so this module reads the
precomputed field directly -- that field IS devig_twoway's own output. A row
with devigged_prob is None is the "degenerate pair excluded honestly" case
(both-sides-priced check failed upstream); measured live, 0/624466 total-
market rows hit this in the current corpus, so a synthetic construction is
used in the unit test for that path (test_replay_mlb.py::test_degenerate_pair_excluded).

SAME-BOOK DISCIPLINE (binding): the close used for a snapshot's CLV is always
that SAME (game_id, book, side)'s own last pregame observation -- POLICY A
(every bet) never crosses books, and POLICY B (best execution -- best price
across books at each snapshot) still grades the taken book's own close, never
a blended/cross-book close (the known cross-venue-CLV-is-basis landmine).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/benchmarks/clv_replay/test_replay_mlb.py -q
CLI: python -m scripts.platformkit.benchmarks.clv_replay.replay_mlb
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

REPO = Path(__file__).resolve().parents[4]
_LINE_HISTORY_DIR = REPO / "data" / "cache" / "line_history" / "mlb"
OUT_PATH = REPO / "data" / "domains" / "mlb" / "clv_replay_benchmark.json"

_COARSE_EDGES = (1.0, 6.0, 24.0)  # -> "<1h","1-6h","6-24h",">24h"
_COARSE_LABELS = ("<1h", "1-6h", "6-24h", ">24h")
_SPEED_EDGES = (0.5, 1, 2, 3, 6, 12, 24, 48)  # hours-to-close bin upper edges


def load_total_snapshots(line_history_dir: Path = _LINE_HISTORY_DIR) -> pd.DataFrame:
    """Every priced total-market row (both sides), degenerate (devigged_prob
    None) rows dropped honestly -- see module docstring's DEVIG REUSE note."""
    rows: List[Dict[str, Any]] = []
    for fn in sorted(line_history_dir.glob("*.jsonl")):
        with open(fn, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if r.get("market_type") == "total" and r.get("devigged_prob") is not None:
                    rows.append(r)
    cols = ["game_id", "book", "side", "odds", "devigged_prob", "captured_at", "commence_time"]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows)[cols]


def parse_and_filter_pregame(df: pd.DataFrame) -> pd.DataFrame:
    """Adds captured_dt/commence_dt/time_to_close_hours; drops post-commence
    snapshots (the leak trap -- a bet 'placed' after lock is not hypothetical,
    it's hindsight)."""
    if df.empty:
        return df.assign(captured_dt=[], commence_dt=[], time_to_close_hours=[])
    d = df.copy()
    d["captured_dt"] = pd.to_datetime(d["captured_at"], format="ISO8601", utc=True)
    d["commence_dt"] = pd.to_datetime(d["commence_time"], format="ISO8601", utc=True)
    d = d.dropna(subset=["captured_dt", "commence_dt"])
    d = d[d["captured_dt"] <= d["commence_dt"]].copy()
    d["time_to_close_hours"] = (d["commence_dt"] - d["captured_dt"]).dt.total_seconds() / 3600.0
    return d


def compute_clv(df: pd.DataFrame) -> pd.DataFrame:
    """Adds clv_prob = close_prob - snapshot_prob, close taken from that SAME
    (game_id, book, side)'s own last pregame captured_dt (same-book discipline)."""
    if df.empty:
        return df.assign(clv_prob=[], close_prob=[])
    close_idx = df.groupby(["game_id", "book", "side"])["captured_dt"].idxmax()
    close = df.loc[close_idx, ["game_id", "book", "side", "devigged_prob"]].rename(
        columns={"devigged_prob": "close_prob"})
    d = df.merge(close, on=["game_id", "book", "side"], how="left")
    d["clv_prob"] = d["close_prob"] - d["devigged_prob"]
    return d


def bucket_time_to_close(hours: float, edges=_COARSE_EDGES, labels=_COARSE_LABELS) -> str:
    for edge, label in zip(edges, labels):
        if hours < edge:
            return label
    return labels[-1]


def policy_a(df_clv: pd.DataFrame) -> pd.DataFrame:
    """Every bet possible: every snapshot x both sides, as-is."""
    return df_clv


def policy_b(df_clv: pd.DataFrame) -> pd.DataFrame:
    """Best execution: at each (game_id, side, captured_at), the row with the
    highest decimal odds (best price for the side taken) across books present
    at that exact snapshot tick. Its own book's close still grades it."""
    if df_clv.empty:
        return df_clv
    idx = df_clv.groupby(["game_id", "side", "captured_at"])["odds"].idxmax()
    return df_clv.loc[idx]


def _agg_block(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty or df["clv_prob"].dropna().empty:
        return {"mean": None, "median": None, "pct_positive": None, "n": 0}
    c = df["clv_prob"].dropna()
    return {
        "mean": float(c.mean()), "median": float(c.median()),
        "pct_positive": float((c > 0).mean()), "n": int(len(c)),
    }


def aggregate(df_clv: pd.DataFrame) -> Dict[str, Any]:
    overall = _agg_block(df_clv)
    by_bucket = {}
    by_book = {}
    if not df_clv.empty:
        d = df_clv.copy()
        d["time_bucket"] = d["time_to_close_hours"].apply(bucket_time_to_close)
        for bucket, g in d.groupby("time_bucket"):
            by_bucket[bucket] = _agg_block(g)
        for book, g in d.groupby("book"):
            by_book[book] = _agg_block(g)
    return {"overall": overall, "by_time_bucket": by_bucket, "by_book": by_book}


def build_speed_curve(df_clv: pd.DataFrame, edges=_SPEED_EDGES) -> List[Dict[str, Any]]:
    """Mean CLV of a bet placed T-minus-X hours before close, as a function of
    X (policy A rows -- the full obtainable distribution). Quantifies how much
    CLV reaction speed buys."""
    if df_clv.empty:
        return []
    d = df_clv.dropna(subset=["clv_prob"]).copy()
    bin_edges = [0.0, *edges, float("inf")]
    labels = [f"<={e}h" for e in edges] + [f">{edges[-1]}h"]
    d["speed_bin"] = pd.cut(d["time_to_close_hours"], bins=bin_edges, labels=labels,
                             right=True, include_lowest=True)
    out = []
    for label in labels:
        g = d[d["speed_bin"] == label]
        block = _agg_block(g)
        out.append({"hours_before_close": label, **block})
    return out


def run(line_history_dir: Path = _LINE_HISTORY_DIR, out_path: Path = OUT_PATH) -> Dict[str, Any]:
    raw = load_total_snapshots(line_history_dir)
    pregame = parse_and_filter_pregame(raw)
    clv = compute_clv(pregame)
    a = policy_a(clv)
    b = policy_b(clv)
    doc = {
        "policy_a": aggregate(a),
        "policy_b": aggregate(b),
        "speed_curve": build_speed_curve(a),
        "n_games": int(pregame["game_id"].nunique()) if not pregame.empty else 0,
        "n_snapshots": int(len(pregame)),
        "honest_note": ("probability-space CLV vs same-book close; calibration/"
                         "execution diagnostics, not a dollar edge; positive CLV "
                         "does NOT imply positive expected value vs the true "
                         "outcome distribution"),
        "edge_claimed": False,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    return doc


def main() -> int:
    doc = run()
    print(json.dumps(doc, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

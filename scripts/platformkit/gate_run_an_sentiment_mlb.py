"""scripts.platformkit.gate_run_an_sentiment_mlb -- GATE-RUN for the Action Network
public-splits SENTIMENT axis (public bet%/money% per side) as an MLB moneyline
win-prob candidate ON TOP of the devigged close price.

QUESTION: does home_tickets_pct/home_money_pct (data/cache/public_splits/mlb/
*.jsonl, m41 daily capture) add held-out P(home win) Brier over price-only,
REPLICATED across 2 chronological corpora, DM clustered by event_id,
degenerate-base guarded, with a PLANTED-NULL that MUST reject -- via gate_one
reused VERBATIM from gate_run_soccer_espn28? BASE=logit(close price);
CANDIDATE=BASE+standardized sentiment diff -- "price+sentiment vs price-only",
for free, by setting p_poisson = the market close price.

JOIN CHAIN (3 feeds, no shared key): AN game_id --[date,abbr; CWS->CHW
override]--> espn_boxscores event_id+y_home --[event_id==line_history
game_id; same ESPN numbering]--> line_history devigged_prob (home, moneyline,
latest captured_at=close). Each join rate reported honestly; an unresolved
game is dropped, never guessed.

HONEST STATE (2026-07-09): 1 capture day, 13 AN games, one end-of-day snapshot
(closing sentiment, not live pregame). Far below _MIN_GATEABLE (600, mirrored
from gate_run_mlb_espn_box.py's identical floor) -> UNDERPOWERED w/ n_needed.
m41_public_splits accrues daily; re-run this module unchanged once enough
games join. EXPECTED once gateable: REJECT (sentiment already priced into the
close) -- kept as SCOUTING, never force-fed.

PROPOSAL-ONLY: writes ONLY the verdict JSON + one reject_ledger row
(source=funnel_gate, mirrors funnel_verdict_reconcile's call shape); no
registry write, no flag flip, no $/ROI/edge field. CALIBRATION only. ASCII;
<=300 LOC.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/test_gate_run_an_sentiment_mlb.py -q
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Reuse the PROVEN gate core verbatim (leak-free split, DM-by-event_id, degenerate guard).
from scripts.platformkit.gate_run_soccer_espn28 import gate_one, _NULL_COL
from scripts.platformkit import reject_ledger

_REPO = Path(__file__).resolve().parents[2]
_SPLITS_DIR = _REPO / "data" / "cache" / "public_splits" / "mlb"
_ESPN_BOX = _REPO / "data" / "domains" / "mlb" / "espn_boxscores.parquet"
_LINE_HIST_DIR = _REPO / "data" / "cache" / "line_history" / "mlb"
_VERDICT_OUT = _REPO / "data" / "frontend" / "funnel" / "mlb_an_sentiment_gate.json"

_LAYER = "mlb_an_sentiment_moneyline"
_SIGNAL = "an_sentiment_moneyline_mlb"

# AN -> espn_boxscores abbr, only where they differ (grounded 2026-07-09: AN's
# "CWS" vs espn's "CHW"; every other abbr on that slate matched directly).
_ABBR_OVERRIDE: Dict[str, str] = {"CWS": "CHW"}

_WARMUP, _MIN_TEST = 100, 200   # mirrors the proven gate core's leak-free warmup
_MIN_GATEABLE = 2 * (_WARMUP + _MIN_TEST)   # 600 joined games across 2 corpora
_FEATURE_COLS = ("sent_tickets_diff", "sent_money_diff")

def _norm_abbr(a: Any) -> str:
    a = str(a or "").strip().upper()
    return _ABBR_OVERRIDE.get(a, a)

def _iter_jsonl(fp: Path):
    """Yield each parsed JSON line in *fp*; a torn/malformed line is skipped."""
    for line in fp.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

def load_public_splits(splits_dir: Optional[Path] = None) -> pd.DataFrame:
    """Every captured row across all daily JSONL files."""
    d = Path(splits_dir) if splits_dir is not None else _SPLITS_DIR
    if not d.is_dir():
        return pd.DataFrame()
    return pd.DataFrame([r for fp in sorted(d.glob("*.jsonl")) for r in _iter_jsonl(fp)])

def aggregate_sentiment(splits: pd.DataFrame) -> pd.DataFrame:
    """One row per AN game_id (moneyline only), averaged across books (a book is
    not independent evidence of the same public split); home side direct, else
    100-away (never a guessed direction). No-side games are dropped."""
    cols = ["game_id", "date", "home_abbr", "away_abbr",
            "home_tickets_pct", "home_money_pct"]
    if splits.empty or "market" not in splits.columns:
        return pd.DataFrame(columns=cols)
    ml = splits[splits["market"] == "moneyline"].copy()
    if ml.empty:
        return pd.DataFrame(columns=cols)
    ml["date"] = pd.to_datetime(ml["start_time"], errors="coerce", utc=True).dt.date.astype(str)
    meta = ml.groupby("game_id").agg(home_abbr=("home_abbr", "first"),
                                      away_abbr=("away_abbr", "first"),
                                      date=("date", "first"))
    home = ml[ml["side"] == "home"].groupby("game_id")[["tickets_pct", "money_pct"]] \
        .mean().add_prefix("home_")
    away = ml[ml["side"] == "away"].groupby("game_id")[["tickets_pct", "money_pct"]] \
        .mean().add_prefix("away_")
    out = meta.join(home).join(away)
    out["home_tickets_pct"] = out["home_tickets_pct"].fillna(100.0 - out.get("away_tickets_pct"))
    out["home_money_pct"] = out["home_money_pct"].fillna(100.0 - out.get("away_money_pct"))
    out = out.dropna(subset=["home_tickets_pct", "home_money_pct"]).reset_index()
    return out[cols]

def _load_outcomes(box_path: Optional[Path] = None) -> pd.DataFrame:
    """FINAL, abbr-normalized, tie-free labels from the LOCAL ESPN boxscore parquet."""
    cols = ["date", "home_abbr", "away_abbr", "event_id", "y_home"]
    p = Path(box_path) if box_path is not None else _ESPN_BOX
    if not p.exists():
        return pd.DataFrame(columns=cols)
    b = pd.read_parquet(p)
    b = b[b["status"].astype(str).str.upper().str.contains("FINAL", na=False)].copy()
    if b.empty:
        return pd.DataFrame(columns=cols)
    b["date"] = pd.to_datetime(b["date"], errors="coerce").dt.date.astype(str)
    b["home_abbr"] = b["home_abbr"].map(_norm_abbr)
    b["away_abbr"] = b["away_abbr"].map(_norm_abbr)
    hs, aws = b["home_score"].astype(float), b["away_score"].astype(float)
    b = b[hs != aws].copy()
    b["y_home"] = (b["home_score"].astype(float) > b["away_score"].astype(float)).astype(float)
    return b[cols]

def resolve_outcomes(games: pd.DataFrame, box: pd.DataFrame) -> pd.DataFrame:
    """Left-join onto the FINAL outcome by (date, home_abbr, away_abbr); an
    unmatched game keeps event_id/y_home NaN (honest drop), never a guess."""
    if games.empty:
        return games
    g = games.copy()
    g["home_abbr"] = g["home_abbr"].map(_norm_abbr)
    g["away_abbr"] = g["away_abbr"].map(_norm_abbr)
    return g.merge(box, on=["date", "home_abbr", "away_abbr"], how="left")

def _candidate_close_files(dates: List[str]) -> List[str]:
    """date +/-1 day (a game can close the calendar day before its ET commence)."""
    out = set()
    for ds in dates:
        try:
            dt = datetime.strptime(str(ds), "%Y-%m-%d")
        except ValueError:
            continue
        out.update((dt + timedelta(days=delta)).strftime("%Y-%m-%d") for delta in (-1, 0, 1))
    return sorted(out)

def load_market_close(event_ids: List[Any], dates: List[str],
                      line_hist_dir: Optional[Path] = None) -> Dict[str, float]:
    """{event_id: devigged home moneyline close prob}, LATEST captured_at per
    event_id -- line_history's game_id IS the ESPN event_id (same feed family),
    a direct string join, no abbr resolution needed."""
    wanted = {str(e) for e in event_ids if pd.notna(e)}
    if not wanted:
        return {}
    d = Path(line_hist_dir) if line_hist_dir is not None else _LINE_HIST_DIR
    latest: Dict[str, Tuple[str, float]] = {}
    for fname in _candidate_close_files(dates):
        fp = d / f"{fname}.jsonl"
        if not fp.exists():
            continue
        for r in _iter_jsonl(fp):
            if (r.get("sport") != "mlb" or r.get("market_type") != "moneyline"
                    or r.get("side") != "home"):
                continue
            gid = str(r.get("game_id"))
            if gid not in wanted or r.get("devigged_prob") is None:
                continue
            ts = str(r.get("captured_at") or "")
            prev = latest.get(gid)
            if prev is None or ts > prev[0]:
                latest[gid] = (ts, float(r["devigged_prob"]))
    return {gid: p for gid, (_, p) in latest.items()}

def build_corpus(seed: int = 0, splits_dir: Optional[Path] = None,
                 box_path: Optional[Path] = None,
                 line_hist_dir: Optional[Path] = None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Full join pipeline -> (leak-free per-game frame, honest join diagnostics)."""
    splits = load_public_splits(splits_dir)
    agg = aggregate_sentiment(splits)
    box = _load_outcomes(box_path)
    resolved = resolve_outcomes(agg, box)
    n_games = len(agg)
    n_outcome = int(resolved["event_id"].notna().sum()) if not resolved.empty else 0
    close_map: Dict[str, float] = {}
    if n_outcome:
        close_map = load_market_close(resolved["event_id"].tolist(),
                                      sorted(resolved["date"].dropna().unique().tolist()),
                                      line_hist_dir)
    resolved["p_market"] = resolved["event_id"].map(
        lambda e: close_map.get(str(e)) if pd.notna(e) else None)
    n_price = int(resolved["p_market"].notna().sum()) if not resolved.empty else 0

    frame = resolved.dropna(subset=["y_home", "p_market"]).copy() if not resolved.empty \
        else pd.DataFrame()
    if not frame.empty:
        frame["sent_tickets_diff"] = frame["home_tickets_pct"] - 50.0
        frame["sent_money_diff"] = frame["home_money_pct"] - 50.0
        frame["p_poisson"] = frame["p_market"].astype(float)   # gate core's base column name
        frame["event_id"] = frame["event_id"].astype(str)
        frame = frame.sort_values("date", kind="mergesort").reset_index(drop=True)
        rng = np.random.default_rng(seed)
        frame[_NULL_COL] = rng.standard_normal(len(frame))

    diag = {
        "n_an_games": n_games, "n_outcome_joined": n_outcome, "n_price_joined": n_price,
        "n_gateable_rows": len(frame),
        "outcome_join_rate": round(n_outcome / n_games, 4) if n_games else 0.0,
        "price_join_rate": round(n_price / n_games, 4) if n_games else 0.0}
    return frame, diag

def _ledger(out: Dict[str, Any]) -> None:
    reject_ledger.record(
        "mlb", _SIGNAL, out["verdict"], str(out.get("vs_close", ""))[:200],
        source="funnel_gate",
        metrics={"n_corpora": out.get("n_corpora"), "null_rejects": out.get("null_rejects"),
                 "proposal_only": True, "n_gateable_rows": out.get("n_gateable_rows"),
                 "n_needed": out.get("n_needed")},
    )

def run(eps: float = 0.05, seed: int = 0, out_path: Optional[Path] = None,
        splits_dir: Optional[Path] = None, box_path: Optional[Path] = None,
        line_hist_dir: Optional[Path] = None) -> Dict[str, Any]:
    dest = Path(out_path) if out_path is not None else _VERDICT_OUT
    frame, diag = build_corpus(seed=seed, splits_dir=splits_dir, box_path=box_path,
                               line_hist_dir=line_hist_dir)
    n = len(frame)
    if n < _MIN_GATEABLE:
        per_day = diag["n_an_games"] or 1
        days_needed = -(-(_MIN_GATEABLE - n) // per_day)   # ceil div
        out: Dict[str, Any] = {
            "layer": _LAYER, "verdict": "UNDERPOWERED",
            "n_gateable_rows": n, "n_needed": _MIN_GATEABLE, "diagnostics": diag,
            "hypothesis": "public tickets%/money% split adds calibration over price alone",
            "protocol": "leak-free 2-corpus walk-forward logit(price)+feature vs "
                       "logit(price), DM by event_id, degenerate guard, planted-null "
                       "-- gate_one reused VERBATIM from gate_run_soccer_espn28",
            "frontier_expectation": "efficient markets already price public sentiment "
                                    "into the close -- honest NULL likely once gateable",
            "accrual_note": f"~{per_day} MLB games/day captured; ~{days_needed} more "
                            "day(s) needed at this rate -- re-run this module unchanged",
            "rerunnable": True, "proposal_only": True, "force_fed": False,
            "scouting_only": True,
            "vs_close": "UNPROVEN -- CALIBRATION only; not gateable yet (n)",
        }
        _write(out, dest)
        _ledger(out)
        return out

    mid = n // 2
    corp_a = frame.iloc[:mid].reset_index(drop=True)
    corp_b = frame.iloc[mid:].reset_index(drop=True)
    results = [gate_one(corp_a, corp_b, c, eps) for c in _FEATURE_COLS]
    null = gate_one(corp_a, corp_b, _NULL_COL, eps)
    null_rejects = null["verdict"] in ("REJECT", "INVALID_BASE", "PARTIAL")
    base_ok = not any(r["base_degenerate"] for r in results)
    any_ship = any(r["verdict"] == "SHIP" for r in results)
    verdict = ("NOT_TESTABLE" if not null_rejects else
               "INVALID_BASE" if not base_ok else
               "SHIP" if any_ship else "REJECT")
    out = {
        "layer": _LAYER, "verdict": verdict, "n_corpora": 2, "eps": eps,
        "n_gateable_rows": n, "diagnostics": diag,
        "base": "devigged close moneyline price (line_history, logit)",
        "base_skillful": base_ok, "results": results, "null": null, "null_rejects": null_rejects,
        "proposal_only": True, "force_fed": False, "scouting_only": verdict != "SHIP",
        "vs_close": "UNPROVEN -- CALIBRATION only (held-out home-win Brier), not edge"}
    _write(out, dest)
    _ledger(out)
    return out

def _write(out: Dict[str, Any], dest: Path = _VERDICT_OUT) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="ascii") as f:
        json.dump(out, f, indent=2, sort_keys=True, default=str)

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Gate the Action Network public-splits sentiment axis (MLB moneyline).")
    ap.add_argument("--eps", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    res = run(eps=a.eps, seed=a.seed)
    print(f"MLB AN-SENTIMENT GATE -> {res['verdict']}")
    for k in ("n_gateable_rows", "n_needed", "diagnostics", "n_corpora"):
        if k in res:
            print(f"  {k}: {res[k]}")
    print(f"wrote {_VERDICT_OUT}")
    return 0

__all__ = ["load_public_splits", "aggregate_sentiment", "resolve_outcomes",
           "load_market_close", "build_corpus", "run", "main",
           "_FEATURE_COLS", "_MIN_GATEABLE"]

if __name__ == "__main__":
    raise SystemExit(main())

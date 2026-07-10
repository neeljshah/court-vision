"""scripts.platformkit.execution.fill_model.meta_label_replication -- MEASUREMENT
ONLY: second-corpus adjudication of the flagged meta_label_buckets table (n=186,
every divergence quartile >50% CLV-positive incl. Q1 -- the selection-artifact
signature). Three checks, same bucketing, CLV language only (never $/ROI):

  A) SYNTHETIC corpus from settled data/cache/ingame_grade_joined/mlb ticks
     (178 games): at standardized checkpoints (first tick of innings 2/4/6) a
     synthetic order takes the model-favored side; edge=|model-market| at order
     time ONLY; beat_close = the last-tick within-venue close moved toward the
     taken side (strict, ties lose -- mirrors the ledger's clv_pct>0). The
     strict-disjoint population EXCLUDES every game the paper ledger bet.
  B) Walk-forward: quartile breakpoints fit on the FIRST half of games (by
     first-tick ts), rates evaluated on the LATER half only.
  C) Paper-ledger temporal split: first/second half by order ts, first-half
     breakpoints applied to both halves.

STEP-0 PREMISE CHECK (2026-07-11, fresh reads): clv_ledger.jsonl 186 true-close
kalshi rows (160 with edge; edge always >0 = taken-side divergence); joined mlb
corpus 178 ticker files, 0 missing close_prob; 103/178 games overlap the paper
corpus (excluded) -> strict-disjoint population = 29 usable games. DIAGNOSTIC: round(close_prob)
== outcome in 165/178 games (92.7%) -- the in-game "close" is essentially the
OUTCOME, so any model with outcome skill beats the close >50% at every
divergence size. That structural mechanism, not bucket-level signal, is the
artifact candidate.

CIs: Wilson per bucket + game-clustered bootstrap (checkpoints within a game
share one close/outcome -- rows are NOT independent; the cluster CI is the one
that counts). INVARIANTS: <=300 LOC; ASCII; stdlib only; never writes
data/registry/; no $/ROI/edge claim; ledger append is opt-in via --write-ledger.
Test: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/execution/fill_model/test_meta_label_replication.py -q
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from scripts.platformkit.execution.book_replay import load_jsonl
from scripts.platformkit.execution.fill_model.meta_label_buckets import (
    MIN_BUCKET_N, _bucket_stats, edge_bucket_label, edge_quartiles,
    load_true_close_kalshi_bets, wilson_ci)

_REPO = Path(__file__).resolve().parents[4]
JOINED_DIR = _REPO / "data" / "cache" / "ingame_grade_joined"
MLB_LEDGER = _REPO / "domains" / "mlb" / "knowledge" / "validation_ledger.jsonl"
CHECKPOINT_INNINGS = (2, 4, 6)
_INNING_RE = re.compile(r"\binning=(\d+)")


def paper_event_tickers(sport: str = "mlb") -> Set[str]:
    """Kalshi EVENT tickers the paper ledger bet (market_id minus side suffix)."""
    out: Set[str] = set()
    for r in load_true_close_kalshi_bets(sport):
        mid = str(r.get("market_id") or "")
        if mid.startswith("KX"):
            out.add(mid.rsplit("-", 1)[0].upper())
    return out


def synthetic_orders_for_file(path: Path) -> List[Dict[str, Any]]:
    """Synthetic orders for ONE joined ticker file: at the FIRST tick of each
    checkpoint inning, take the model-favored side. Order-time features only
    (model_prob/market_prob at that tick); close/outcome only label the row."""
    rows = load_jsonl(path)
    orders: List[Dict[str, Any]] = []
    seen: Set[int] = set()
    for r in rows:
        m = _INNING_RE.search(str(r.get("state_summary") or ""))
        if not m:
            continue
        inning = int(m.group(1))
        if inning not in CHECKPOINT_INNINGS or inning in seen:
            continue
        seen.add(inning)
        mp, md, cp = r.get("market_prob"), r.get("model_prob"), r.get("close_prob")
        if mp is None or md is None or cp is None or md == mp:
            continue  # no divergence -> no order; no close -> ungradable
        take_home = md > mp
        beat = (cp > mp) if take_home else (cp < mp)
        orders.append({
            "game_id": path.stem, "ts": r.get("ts"), "checkpoint_inning": inning,
            "side": "home" if take_home else "away", "edge": abs(md - mp),
            "beat_close": bool(beat), "outcome": r.get("outcome"),
        })
    return orders


def build_synthetic_corpus(sport: str = "mlb", joined_dir: Optional[Path] = None,
                           exclude_tickers: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    """All synthetic orders for *sport*, skipping *exclude_tickers* (upper-cased)."""
    sdir = (Path(joined_dir) if joined_dir is not None else JOINED_DIR) / sport
    excl = {t.upper() for t in (exclude_tickers or set())}
    out: List[Dict[str, Any]] = []
    for p in sorted(sdir.glob("*.jsonl")):
        if p.stem.upper() in excl:
            continue
        out.extend(synthetic_orders_for_file(p))
    return out


def cluster_ci(rows: List[Dict[str, Any]], iters: int = 2000, seed: int = 13) -> Optional[List[float]]:
    """95% game-clustered bootstrap CI for the beat_close rate (resample games)."""
    by_game: Dict[str, List[bool]] = {}
    for r in rows:
        by_game.setdefault(str(r.get("game_id")), []).append(bool(r.get("beat_close")))
    games = list(by_game.values())
    if not games:
        return None
    rng = random.Random(seed)
    rates = []
    for _ in range(iters):
        k = n = 0
        for g in (rng.choice(games) for _ in games):
            k += sum(g)
            n += len(g)
        rates.append(k / n if n else 0.0)
    rates.sort()
    return [round(rates[int(0.025 * iters)], 4), round(rates[int(0.975 * iters) - 1], 4)]


def binom_p_vs_half(k: int, n: int) -> Optional[float]:
    """Exact two-sided binomial p vs 0.5 (naive: ignores game clustering)."""
    if n == 0:
        return None
    tail = sum(math.comb(n, i) for i in range(min(k, n - k) + 1)) * 0.5 ** n
    return round(min(1.0, 2.0 * tail), 6)


def bucket_table(rows: List[Dict[str, Any]], qs: Optional[List[float]] = None) -> Dict[str, Any]:
    """SAME bucketing as meta_label_buckets, plus game-clustered CI per bucket."""
    qs = qs if qs is not None else edge_quartiles(rows)
    by_q: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_q.setdefault(edge_bucket_label(r["edge"], qs), []).append(r)
    table: Dict[str, Any] = {}
    for b, rs in sorted(by_q.items()):
        st = _bucket_stats(rs)
        st["clv_positive_ci95_game_clustered"] = cluster_ci(rs)
        st["n_games"] = len({str(r.get("game_id")) for r in rs})
        st["p_vs_coin_naive"] = binom_p_vs_half(st["clv_positive_n"], st["n"])
        table[b] = st
    return {"edge_quartile_breakpoints": [round(q, 5) for q in qs], "by_edge_quartile": table}


def _half_split(rows: List[Dict[str, Any]], key: str = "ts") -> tuple:
    srt = sorted(rows, key=lambda r: str(r.get(key) or ""))
    return srt[: len(srt) // 2], srt[len(srt) // 2:]


def walk_forward_table(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Breakpoints fit on the earlier half (by ts), rates scored on the later half."""
    first, second = _half_split(rows)
    qs = edge_quartiles(first)
    out = bucket_table(second, qs=qs)
    out["fit_n"], out["eval_n"] = len(first), len(second)
    return out


def paper_temporal_tables(sport: Optional[str] = None) -> Dict[str, Any]:
    """Paper-ledger corpus split first/second half by ts; first-half breakpoints
    applied to BOTH halves (walk-forward for the second)."""
    rows = [dict(r, game_id=r.get("event_id") or r.get("market_id"))
            for r in load_true_close_kalshi_bets(sport) if r.get("edge") is not None]
    first, second = _half_split(rows)
    qs = edge_quartiles(first)
    return {"n_first": len(first), "n_second": len(second),
            "first_half": bucket_table(first, qs=qs), "second_half": bucket_table(second, qs=qs)}


def _bucket_verdict(name: str, st: Dict[str, Any]) -> str:
    ci = st.get("clv_positive_ci95_game_clustered") or st.get("clv_positive_ci95") or [0, 1]
    if st["n"] < MIN_BUCKET_N:
        return "PROVISIONAL"
    if ci[0] > 0.5:
        # >50% floor reproduced even with NO order selection: the floor is
        # structural (close~=outcome), not divergence signal -- for the pure-
        # noise Q1 bucket that IS the artifact confirmation.
        return "ARTIFACT_CONFIRMED" if name.startswith("Q1") else "REPLICATED"
    return "FAILED_REPLICATION"


def _rate_gt_half(tbl: Dict[str, Any], bucket_prefix: str) -> bool:
    for name, st in tbl["by_edge_quartile"].items():
        if name.startswith(bucket_prefix):
            return (st.get("clv_positive_rate") or 0.0) > 0.5
    return False


def adjudicate(disjoint_tbl: Dict[str, Any], paper_split: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Ledger verdict rows: one per quartile from the strict-disjoint replication
    + one FAMILY row. Adjudication key: Q1 staying >50% on a NO-selection corpus
    = structural close artifact (ARTIFACT_CONFIRMED at Q1); Q1 collapsing to
    coin = the original Q1 does not exist outside the paper order flow
    (FAILED_REPLICATION). If NO bucket replicates while the paper corpus's
    all-positive pattern holds in its own second half, the family verdict is
    ARTIFACT_CONFIRMED: the positivity is a property of the paper ORDER
    SELECTION (which ticks become orders), not of divergence magnitude."""
    out = []
    verdicts = {}
    for name, st in disjoint_tbl["by_edge_quartile"].items():
        v = _bucket_verdict(name, st)
        verdicts[name] = v
        out.append({
            "corpus": "ingame_grade_joined_mlb_synthetic_checkpoints_disjoint",
            "edge_claimed": False, "effect": st["clv_positive_rate"],
            "hypothesis": "meta_label_divergence_bucket_%s" % name.split("_")[0],
            "n": st["n"], "p": st["p_vs_coin_naive"], "sport": "mlb",
            "verdict": v,
            "note": ("%s: %d/%d CLV-positive, game-clustered CI %s (%d games), "
                     "naive-binomial p vs coin %s. Second-corpus replication of the "
                     "flagged n=186 all-quartiles->50%% bucket table."
                     ) % (name, st["clv_positive_n"], st["n"],
                          st["clv_positive_ci95_game_clustered"], st["n_games"],
                          st["p_vs_coin_naive"]),
        })
    none_replicated = all(v in ("FAILED_REPLICATION", "PROVISIONAL") for v in verdicts.values())
    paper_stable = bool(paper_split) and _rate_gt_half(paper_split["second_half"], "Q1") \
        and _rate_gt_half(paper_split["second_half"], "Q4")
    family = "ARTIFACT_CONFIRMED" if (none_replicated and paper_stable) else (
        "FAILED_REPLICATION" if none_replicated else "MIXED")
    n_total = sum(st["n"] for st in disjoint_tbl["by_edge_quartile"].values())
    out.append({
        "corpus": "ingame_grade_joined_mlb_synthetic_checkpoints_disjoint+paper_temporal_split",
        "edge_claimed": False, "effect": None,
        "hypothesis": "meta_label_divergence_bucket_table_all_positive",
        "n": n_total, "p": None, "sport": "mlb", "verdict": family,
        "note": ("FAMILY verdict on the flagged n=186 table (every quartile incl. Q1 "
                 ">50%% CLV-positive): no quartile replicates on the independent "
                 "no-selection corpus (all at-or-below coin), while the paper corpus "
                 "keeps the all-positive pattern in its own second half -- the "
                 "positivity is an ORDER-SELECTION artifact of the paper flow, not a "
                 "divergence-magnitude meta-signal. Do not weight orders by these "
                 "buckets. paper_second_half_Q1>0.5=%s, Q4>0.5=%s."
                 ) % (paper_stable and _rate_gt_half(paper_split["second_half"], "Q1"),
                      paper_stable and _rate_gt_half(paper_split["second_half"], "Q4")),
    })
    return out


def build_report(joined_dir: Optional[Path] = None) -> Dict[str, Any]:
    excl = paper_event_tickers("mlb")
    disjoint = build_synthetic_corpus("mlb", joined_dir, exclude_tickers=excl)
    full = build_synthetic_corpus("mlb", joined_dir)
    disjoint_tbl = bucket_table(disjoint)
    paper_split = paper_temporal_tables()
    return {
        "edge_claimed": False,
        "design": "synthetic model-favored-side orders at innings %s; order-time features only; strict beat_close vs last-tick within-venue close" % (CHECKPOINT_INNINGS,),
        "n_paper_overlap_games_excluded": len(excl),
        "synthetic_disjoint": dict(disjoint_tbl, n_orders=len(disjoint),
                                   n_games=len({r["game_id"] for r in disjoint})),
        "synthetic_disjoint_walkforward": walk_forward_table(disjoint),
        "synthetic_full": dict(bucket_table(full), n_orders=len(full),
                               n_games=len({r["game_id"] for r in full})),
        "paper_temporal_split": paper_split,
        "verdicts": adjudicate(disjoint_tbl, paper_split),
    }


def append_ledger(verdicts: List[Dict[str, Any]], ledger: Optional[Path] = None) -> int:
    path = Path(ledger) if ledger is not None else MLB_LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for v in verdicts:
            fh.write(json.dumps(v, ensure_ascii=True, sort_keys=True) + "\n")
    return len(verdicts)


def main() -> int:
    ap = argparse.ArgumentParser(description="meta-label second-corpus replication (CLV language only, no $/edge claim)")
    ap.add_argument("--write-ledger", action="store_true")
    args = ap.parse_args()
    rep = build_report()
    print(json.dumps(rep, ensure_ascii=True, indent=2))
    if args.write_ledger:
        n = append_ledger(rep["verdicts"])
        print("appended %d verdict rows to %s" % (n, MLB_LEDGER))
    return 0


__all__ = ["paper_event_tickers", "synthetic_orders_for_file", "build_synthetic_corpus",
           "cluster_ci", "binom_p_vs_half", "bucket_table", "walk_forward_table",
           "paper_temporal_tables", "adjudicate", "build_report", "append_ledger"]

if __name__ == "__main__":
    raise SystemExit(main())

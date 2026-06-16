"""scripts.platformkit.knowledge.golden -- leak-aware golden set + recall@5 eval.

GOLDEN SET (tests/fixtures/intel_golden.jsonl, git-TRACKED -- fixtures, not data):
  schema per line: {"sport","query","expected_note_id"}
  >=120 rows, >=30 each for NBA/MLB/Soccer/Tennis, +>=15 MEMORY (5 corpora).

LEAK-AWARE AUTHORING:
  draft_candidates() generates DRAFT queries from each note's TITLE (and, for memory,
  the front-matter description) ONLY -- it NEVER reads the built index or scores. A
  human/Opus then rewrites those drafts into NATURAL paraphrases that do NOT copy the
  title verbatim (verbatim-title queries are query-leak and inflate recall). The
  committed jsonl is the reviewed, leak-checked version; the draft is throwaway.

EVAL (--eval): for each row retrieve(sport, query, top_k=5); hit if expected_note_id
  in returned note_ids. Reports recall@5 + MRR OVERALL and PER-SPORT, a bootstrap 95%
  CI, an ABLATION table (dense-only -> +bm25 -> +exact-boost), and a TAU calibration
  (50/50 split: sweep tau on tuning half maximizing F1 vs injected-irrelevant queries,
  validate on held-out half). Thresholds: overall recall@5 >= 0.90, every sport >= 0.85.

This module emits NO probability/odds/edge. ASCII only. Per-file eval test asserts
recall@5 >= 0.90. Run:
  python -m scripts.platformkit.knowledge.golden --eval
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import config
from .retrieve import retrieve

FIXTURE = Path(__file__).resolve().parent / "tests" / "fixtures" / "intel_golden.jsonl"
_STOP = {"the", "a", "an", "and", "of", "to", "in", "on", "for", "with", "as", "its",
         "is", "are", "vs", "against", "within", "into", "by", "at", "or"}


def load_golden(path: Path = FIXTURE) -> List[dict]:
    rows: List[dict] = []
    if not path.exists():
        return rows
    for ln in path.read_text(encoding="ascii").splitlines():
        ln = ln.strip()
        if ln:
            rows.append(json.loads(ln))
    return rows


# ---------------------------------------------------------------------------
# Leak-aware DRAFT candidate generation (title-only; NEVER reads the index)
# ---------------------------------------------------------------------------
def _content_words(title: str) -> List[str]:
    toks = re.findall(r"[a-z0-9][a-z0-9-]+", title.lower())
    return [t for t in toks if t not in _STOP]


def draft_candidates(per_sport: int = 32, mem: int = 16,
                     seed: int = 7) -> List[dict]:
    """Generate DRAFT (query, expected_note_id) rows from note TITLES only.

    These are NOT leak-checked; they are the raw material a human paraphrases. The
    draft query keeps content words but drops the title's word order so it is not a
    verbatim copy -- still, the committed fixture must be human-reviewed.
    """
    from .ingest import build_corpus
    rng = random.Random(seed)
    corpus = build_corpus()
    by_source: Dict[str, List] = {}
    for c in corpus:
        if len(c.title) < 6:
            continue
        by_source.setdefault(c.sport, []).append(c)
    out: List[dict] = []
    for sport in config.SPORTS:
        notes = by_source.get(sport, [])
        rng.shuffle(notes)
        for c in notes[:per_sport]:
            words = _content_words(c.title)
            if len(words) < 2:
                continue
            rng.shuffle(words)
            out.append({"sport": sport, "query": " ".join(words[:5]),
                        "expected_note_id": c.note_id})
    memnotes = by_source.get("MEMORY", [])
    rng.shuffle(memnotes)
    for c in memnotes[:mem]:
        words = _content_words(c.title)
        if len(words) < 2:
            continue
        rng.shuffle(words)
        out.append({"sport": "MEMORY", "query": " ".join(words[:5]),
                    "expected_note_id": c.note_id})
    return out


# ---------------------------------------------------------------------------
# Eval: recall@5, MRR, per-sport, bootstrap CI, ablation, tau calibration
# ---------------------------------------------------------------------------
def _eval_row(row: dict, top_k: int, **kw) -> Tuple[bool, float]:
    res = retrieve(row["query"], sport=row["sport"], top_k=top_k, **kw)
    ids = [h.note_id for h in res.hits]
    exp = row["expected_note_id"]
    if exp in ids:
        return True, 1.0 / (ids.index(exp) + 1)
    return False, 0.0


def evaluate(rows: List[dict], top_k: int = 5, **kw) -> Dict:
    per: Dict[str, List[Tuple[bool, float]]] = {}
    for r in rows:
        per.setdefault(r["sport"], []).append(_eval_row(r, top_k, **kw))
    out: Dict = {"per_sport": {}, "n": len(rows)}
    all_hits: List[bool] = []
    all_mrr: List[float] = []
    for sport, vals in per.items():
        hits = [h for h, _ in vals]
        mrr = [m for _, m in vals]
        all_hits += hits
        all_mrr += mrr
        out["per_sport"][sport] = {
            "n": len(vals),
            "recall@5": round(sum(hits) / len(hits), 4),
            "mrr": round(sum(mrr) / len(mrr), 4)}
    out["recall@5"] = round(sum(all_hits) / max(1, len(all_hits)), 4)
    out["mrr"] = round(sum(all_mrr) / max(1, len(all_mrr)), 4)
    out["_hits"] = all_hits
    return out


def bootstrap_ci(hits: List[bool], iters: int = 2000, seed: int = 13) -> Tuple[float, float]:
    rng = random.Random(seed)
    n = len(hits)
    if n == 0:
        return (0.0, 0.0)
    means = []
    for _ in range(iters):
        s = sum(hits[rng.randrange(n)] for _ in range(n)) / n
        means.append(s)
    means.sort()
    return (round(means[int(0.025 * iters)], 4), round(means[int(0.975 * iters)], 4))


def ablation(rows: List[dict]) -> List[Tuple[str, float]]:
    stages = [
        ("dense-only", dict(dense_w=1.0, sparse_w=0.0, use_boost=False)),
        ("+bm25(RRF)", dict(dense_w=config.DENSE_W, sparse_w=config.SPARSE_W,
                            use_boost=False)),
        ("+exact-boost", dict(dense_w=config.DENSE_W, sparse_w=config.SPARSE_W,
                              use_boost=True)),
    ]
    return [(name, evaluate(rows, **kw)["recall@5"]) for name, kw in stages]


def calibrate_tau(rows: List[dict], seed: int = 5) -> Dict:
    """50/50 split: sweep tau on the tuning half maximizing F1 (relevant vs injected
    irrelevant), validate recall + honest-reject rate on the held-out half."""
    rng = random.Random(seed)
    idx = list(range(len(rows)))
    rng.shuffle(idx)
    half = len(idx) // 2
    tune = [rows[i] for i in idx[:half]]
    held = [rows[i] for i in idx[half:]]
    irrel = ["xqzv telemetry ledger sprocket", "fiscal quarterly audit memorandum",
             "lunar regolith spectroscopy", "compiler register allocation pass"]
    best_tau, best_f1 = config.RELEVANCE_TAU, -1.0
    for tau in [round(t, 3) for t in [0.0, 0.02, 0.04, 0.06, 0.08, 0.1, 0.15, 0.2]]:
        tp = sum(1 for r in tune if not retrieve(
            r["query"], sport=r["sport"], top_k=5, tau=tau).reject)
        tn = sum(1 for q in irrel for s in config.SPORTS if retrieve(
            q, sport=s, top_k=5, tau=tau).reject)
        fn = len(tune) - tp
        fp = len(irrel) * len(config.SPORTS) - tn
        prec = tp / max(1, tp + fp)
        rec = tp / max(1, tp + fn)
        f1 = 2 * prec * rec / max(1e-9, prec + rec)
        if f1 > best_f1:
            best_f1, best_tau = f1, tau
    held_eval = evaluate(held, tau=best_tau)
    reject_irrel = sum(1 for q in irrel for s in config.SPORTS if retrieve(
        q, sport=s, top_k=5, tau=best_tau).reject) / (len(irrel) * len(config.SPORTS))
    return {"best_tau": best_tau, "tune_f1": round(best_f1, 3),
            "held_recall@5": held_eval["recall@5"],
            "held_irrelevant_reject_rate": round(reject_irrel, 3)}


def _print_report(rows: List[dict]) -> Dict:
    res = evaluate(rows, top_k=5)
    lo, hi = bootstrap_ci(res["_hits"])
    print(f"=== Golden recall@5 (n={res['n']}) ===")
    print(f"OVERALL recall@5={res['recall@5']} mrr={res['mrr']} 95%CI=[{lo},{hi}]")
    for sport, s in sorted(res["per_sport"].items()):
        print(f"  {sport:11s} n={s['n']:3d} recall@5={s['recall@5']} mrr={s['mrr']}")
    print("--- ablation (each stage should help) ---")
    for name, r in ablation(rows):
        print(f"  {name:14s} recall@5={r}")
    print("--- tau calibration (no tuning leak) ---")
    print("  " + json.dumps(calibrate_tau(rows)))
    return res


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", action="store_true",
                    help="Print leak-aware DRAFT candidates (for human review).")
    ap.add_argument("--eval", action="store_true", help="Run the recall@5 report.")
    args = ap.parse_args(argv)
    if args.draft:
        for r in draft_candidates():
            print(json.dumps(r))
        return 0
    rows = load_golden()
    if not rows:
        print("No golden fixture found at", FIXTURE)
        return 1
    res = _print_report(rows)
    ok = res["recall@5"] >= 0.90 and all(
        s["recall@5"] >= 0.85 for s in res["per_sport"].values())
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

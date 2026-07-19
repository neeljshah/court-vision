"""scripts.platformkit.ingame.mlb_label_audit -- adjudicate label/state integrity of the
MLB in-game joined corpus (data/cache/ingame_grade_joined/mlb/*.jsonl) that gates the
margin-blind blend fix (mlb_blend_fit.py).

Two prior investigations suspected the LATE-INNING (inn>=7) down-side rows carry STALE or
WRONG labels/markets -- e.g. "home down >=4 in inning 7+" showing mean_y=0.214 with market
~0.29 (real comeback rate ~5%). If those ticks are corrupt, the blend gate's PASS (which
holds only WITH inn>=7 ticks, FAIL without) is an artifact of corrupt data. This module
adjudicates that with an INDEPENDENT outcome source.

CHECKS (per game file):
  (a) OUTCOME CROSS-CHECK: re-derive home_win from data/domains/mlb/games_current.parquet
      (final runs), matched via the Kalshi ticker's date + away/home blob. A joined label
      that disagrees with the independent final is a LABEL BUG -> game dropped.
  (b) MONOTONE SANITY: the last captured tick's run-diff sign vs the settled outcome. A
      last tick showing home LOSING while outcome=home_win is either a real comeback
      (independent final confirms it -> capture-truncation, NOT a bug) or, if the
      independent final ALSO contradicts, a label bug (already caught by (a)).
  (c) STALE-MARKET: spans where market_prob is frozen (identical) for >30 min of game time
      while the score moves materially (|run_diff| change >=2). Quality diagnostic.
  (d) TIME-ALIGNMENT: ticks whose inning regresses or ts goes backwards within a game.
      Quality diagnostic.

DROP semantics (--write-clean): a WHOLE GAME is dropped iff its label is a confirmed bug
(check (a) mismatch). Never row-surgery; the judge corpus is never modified in place --
mlb_clean/ is a COPY. Monotone/stale/time flags are reported but do NOT drop a game whose
label the independent source confirms (dropping real comebacks would bias the corpus).

The decisive number: fraction of inn>=7 ticks in dropped games vs earlier-inning ticks. If
late innings are disproportionately corrupt, the FAIL-excluding-inn7 gate arm was fighting
bad data; if clean, the blend's late-inning-only improvement is real signal (and must be
judged on its own fragility, not excused as a data artifact).

INVARIANTS: build only under scripts/platformkit/; ASCII; <=300 LOC; no edge claims;
edge_claimed always False. Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/ingame/test_mlb_label_audit.py -q
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scripts.platformkit.ingame.ingame_id_resolver_mlb import parse_kalshi_mlb_ticker

EDGE_CLAIMED = False
_SR = re.compile(r"home_score=([\-\d.]+) away_score=([\-\d.]+) inning=(\d+) half=(\w+)")
_MON = {"JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
        "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"}
# games_current.parquet team dialect -> Kalshi KXMLBGAME ticker-blob dialect. Only the
# spots where they differ; every other code is identical 3 letters.
_P2K = {"ARI": "AZ", "CUB": "CHC", "KAN": "KC", "OAK": "ATH", "SDG": "SD", "SFO": "SF",
        "TAM": "TB", "WAS": "WSH"}
_STALE_MIN = 30.0        # frozen-market window (minutes of game time)
_STALE_RD = 2.0          # material score move while frozen
_LATE_INN = 7


def _k(abbr: str) -> str:
    return _P2K.get(abbr, abbr)


def build_outcome_index(games_parquet: str) -> Dict[Tuple[str, str], List[int]]:
    """(date, away+home Kalshi blob) -> [independent home_win, ...] from final runs."""
    import pandas as pd
    df = pd.read_parquet(games_parquet)
    df = df.assign(_d=pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d"))
    idx: Dict[Tuple[str, str], List[int]] = {}
    for _, r in df.iterrows():
        blob = _k(str(r["away_team"])) + _k(str(r["home_team"]))
        idx.setdefault((r["_d"], blob), []).append(int(r["target_home_win"]))
    return idx


def _ts(s: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _ticker_date(stem: str) -> Optional[str]:
    p = parse_kalshi_mlb_ticker(stem)
    if not p or p["mon"] not in _MON:
        return None
    return "20%s-%s-%s" % (p["yy"], _MON[p["mon"]], p["dd"])


def _load_ticks(path: str) -> List[Dict[str, Any]]:
    """Parse each jsonl tick into {ts, rd, inning, outcome, market_prob}; skip unparseable."""
    ticks: List[Dict[str, Any]] = []
    for line in open(path, "r"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        m = _SR.search(d.get("state_summary", "") or "")
        if not m or d.get("outcome") is None:
            continue
        ticks.append({
            "ts": _ts(d.get("ts", "")),
            "rd": float(m.group(1)) - float(m.group(2)),
            "inning": int(m.group(3)),
            "outcome": float(d["outcome"]),
            "market_prob": d.get("market_prob"),
        })
    ticks.sort(key=lambda t: t["ts"] or datetime.min)
    return ticks


def _split_late(ticks: List[Dict[str, Any]], pred) -> Tuple[int, int]:
    """(late_flagged, early_flagged) tick counts under a per-tick boolean pred(i)."""
    late = early = 0
    for i, t in enumerate(ticks):
        if pred(i):
            if t["inning"] >= _LATE_INN:
                late += 1
            else:
                early += 1
    return late, early


def audit_game(path: str, idx: Dict[Tuple[str, str], List[int]]) -> Dict[str, Any]:
    """Run all four checks on one game file; return a per-game verdict dict."""
    stem = os.path.basename(path).replace(".jsonl", "")
    ticks = _load_ticks(path)
    res: Dict[str, Any] = {"game_id": stem, "n_ticks": len(ticks),
                           "n_late": sum(1 for t in ticks if t["inning"] >= _LATE_INN),
                           "resolved": False, "label_bug": False, "unverifiable": True,
                           "last_tick_contradicts": False, "stale_market": False,
                           "time_regression": False, "stale_late": 0, "stale_early": 0,
                           "reg_late": 0, "reg_early": 0}
    if not ticks:
        return res
    label = int(ticks[0]["outcome"])
    # (a) outcome cross-check
    date = _ticker_date(stem)
    hits = idx.get((date, parse_kalshi_mlb_ticker(stem)["blob"])) if date else None
    if hits and len(hits) == 1:
        res["resolved"], res["unverifiable"] = True, False
        res["independent_home_win"] = hits[0]
        res["label_bug"] = label != hits[0]
    # (b) monotone sanity: last-tick direction vs settled outcome
    last_rd = ticks[-1]["rd"]
    if (last_rd < 0 and label == 1) or (last_rd > 0 and label == 0):
        res["last_tick_contradicts"] = True
    # (c) stale market
    def _stale_at(i: int) -> bool:
        j = i
        while j > 0 and ticks[j - 1]["market_prob"] == ticks[i]["market_prob"]:
            j -= 1
        a, b = ticks[j]["ts"], ticks[i]["ts"]
        if a and b and (b - a).total_seconds() / 60.0 > _STALE_MIN:
            return abs(ticks[i]["rd"] - ticks[j]["rd"]) >= _STALE_RD
        return False
    sl, se = _split_late(ticks, _stale_at)
    res["stale_market"] = (sl + se) > 0
    res["stale_late"], res["stale_early"] = sl, se
    # (d) time alignment: inning regresses (ts already sorted, so back-in-time -> inning dip)
    def _reg_at(i: int) -> bool:
        return i > 0 and ticks[i]["inning"] < ticks[i - 1]["inning"]
    rl, re_ = _split_late(ticks, _reg_at)
    res["time_regression"] = (rl + re_) > 0
    res["reg_late"], res["reg_early"] = rl, re_
    return res


def run_audit(corpus_dir: str, games_parquet: str) -> Dict[str, Any]:
    """Audit every game file; aggregate counts, flagged lists, and late-vs-early fractions."""
    idx = build_outcome_index(games_parquet)
    games = [audit_game(p, idx) for p in sorted(glob.glob(os.path.join(corpus_dir, "*.jsonl")))]
    n_late = sum(g["n_late"] for g in games)
    n_early = sum(g["n_ticks"] - g["n_late"] for g in games)
    dropped = [g for g in games if g["label_bug"]]
    drop_late = sum(g["n_late"] for g in dropped)
    drop_early = sum(g["n_ticks"] - g["n_late"] for g in dropped)

    def _lists(key):
        return sorted(g["game_id"] for g in games if g[key])

    def _frac(n, d):
        return round(n / d, 4) if d else 0.0
    return {
        "corpus_dir": corpus_dir,
        "n_games": len(games), "n_ticks": n_late + n_early,
        "n_ticks_late": n_late, "n_ticks_early": n_early,
        "checks": {
            "outcome_cross_check": {
                "resolved": sum(g["resolved"] for g in games),
                "unverifiable": sum(g["unverifiable"] for g in games),
                "label_bugs": len(dropped), "bug_game_ids": _lists("label_bug"),
            },
            "monotone_sanity": {
                "last_tick_contradicts_outcome": sum(g["last_tick_contradicts"] for g in games),
                "game_ids": _lists("last_tick_contradicts"),
                "note": ("contradiction confirmed by independent final = capture-truncation "
                         "(real comeback), NOT a label bug; only cross-check mismatches drop."),
            },
            "stale_market": {
                "games": sum(g["stale_market"] for g in games), "game_ids": _lists("stale_market"),
                "late_ticks": sum(g["stale_late"] for g in games),
                "early_ticks": sum(g["stale_early"] for g in games),
            },
            "time_alignment": {
                "games": sum(g["time_regression"] for g in games),
                "game_ids": _lists("time_regression"),
                "late_ticks": sum(g["reg_late"] for g in games),
                "early_ticks": sum(g["reg_early"] for g in games),
            },
        },
        "dropped_games": len(dropped),
        "dropped_tick_frac_late": _frac(drop_late, n_late),
        "dropped_tick_frac_early": _frac(drop_early, n_early),
        "honest_note": ("Whole-game drop only on a confirmed label bug (independent final "
                        "disagrees). If dropped_tick_frac_late ~ dropped_tick_frac_early ~ 0 "
                        "the corpus is not corrupt and the blend gate split is real signal "
                        "concentration, not a data artifact -- re-gate on the clean copy to "
                        "confirm the verdict is unchanged."),
        "edge_claimed": EDGE_CLAIMED,
    }


def write_clean(corpus_dir: str, report: Dict[str, Any], out_dir: str) -> int:
    """COPY every non-dropped game file into out_dir (never touch the source). Returns count."""
    drop = set(report["checks"]["outcome_cross_check"]["bug_game_ids"])
    dst = Path(out_dir)
    dst.mkdir(parents=True, exist_ok=True)
    kept = 0
    for p in sorted(glob.glob(os.path.join(corpus_dir, "*.jsonl"))):
        if os.path.basename(p).replace(".jsonl", "") in drop:
            continue
        shutil.copy2(p, dst / os.path.basename(p))
        kept += 1
    return kept


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus-dir", default="data/cache/ingame_grade_joined/mlb")
    ap.add_argument("--games-parquet", default="data/domains/mlb/games_current.parquet")
    ap.add_argument("--out", default="data/cache/benchmarks/mlb_label_audit.json")
    ap.add_argument("--write-clean", action="store_true",
                    help="copy non-dropped games to data/cache/ingame_grade_joined/mlb_clean/")
    ap.add_argument("--clean-dir", default="data/cache/ingame_grade_joined/mlb_clean")
    args = ap.parse_args()
    report = run_audit(args.corpus_dir, args.games_parquet)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print("games=%d ticks=%d label_bugs=%d dropped_frac(late=%.4f early=%.4f) -> %s" % (
        report["n_games"], report["n_ticks"], report["dropped_games"],
        report["dropped_tick_frac_late"], report["dropped_tick_frac_early"], out))
    if args.write_clean:
        kept = write_clean(args.corpus_dir, report, args.clean_dir)
        print("wrote clean corpus: %d games -> %s" % (kept, args.clean_dir))


if __name__ == "__main__":
    main()

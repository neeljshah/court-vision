"""scripts.platformkit.check_ingame_join_integrity -- fail-closed integrity checker for
the in-game JOINED tick corpus (data/cache/ingame_grade_joined/<sport>/<TICKER>.jsonl).

WHY: ticker_settlement_join.join_ticker_file stamps ONE settlement label onto EVERY row
of a ticker's file (ticker_settlement_join.py:176,185,196). If that file holds ticks from
more than one real game -- the pre-guard team-pair bridge in
inplay_capture_loop._scan_live_by_legs (inplay_capture_loop.py:453,468-485) bound a
series' NEXT game to the PREVIOUS day's ticker -- then the label is correct for at most
one of them and wrong for the rest. Every calibration bin those rows land in is distorted.

CHECKS (per game file, all read-only):
  label_disagree  last tick's leader vs the settlement label (a leader at a TRUE final
                  tick wins by definition, so any disagreement is a join defect)
  frozen_market   market_prob has <=1 distinct value across the whole tick path
  ts_outside      a tick whose UTC date is outside [ticker_date, ticker_date+1] (an ET
                  game never spans more than two UTC dates)
  short_path      fewer than MIN_TICKS ticks
  multi_game      monotonicity resets (score or clock going backwards) -- more than one
                  segment means the file holds more than one real game

Exits 1 when any label disagreement exists, else 0.

INVARIANTS: read-only on data/; platformkit-only; ASCII; no edge/ROI language.
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/test_check_ingame_join_integrity.py -q
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = _REPO / "data" / "cache" / "ingame_grade_joined"

MIN_TICKS = 10
MARGINS: Tuple[int, ...] = (1, 3, 5)
MAX_IDS_IN_TABLE = 40

_KV = re.compile(r"([a-z_]+)=(-?[\d.]+)")
_TICKER_DATE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})")
_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}


def parse_state(summary: str) -> Dict[str, float]:
    """Numeric fields of a state_summary blob. Non-numeric tokens are dropped."""
    out: Dict[str, float] = {}
    for key, val in _KV.findall(str(summary or "")):
        try:
            out[key] = float(val)
        except ValueError:  # pragma: no cover -- the regex already constrains the shape
            continue
    return out


def ticker_date(stem: str) -> Optional[date]:
    """Scheduled date encoded in a Kalshi ticker (KXMLBGAME-26JUL021235PITPHI)."""
    m = _TICKER_DATE.search(str(stem or ""))
    if not m:
        return None
    yy, mon, dd = m.group(1), m.group(2), m.group(3)
    if mon not in _MONTHS:
        return None
    try:
        return date(2000 + int(yy), _MONTHS[mon], int(dd))
    except ValueError:
        return None


def _tick_date(ts: Any) -> Optional[date]:
    try:
        return datetime.strptime(str(ts)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _clock(st: Dict[str, float]) -> Optional[float]:
    """The sport's monotone within-game clock: MLB inning, soccer minute."""
    if "inning" in st:
        return st["inning"]
    return st.get("minute")


def _count_segments(states: List[Dict[str, float]]) -> int:
    """Segments separated by a backwards jump in score or clock.

    STATELESS ticks (state_summary "live", ~1/3 of the MLB corpus) carry no ordering
    information and are skipped -- treating their absent fields as zero would invent a
    reset at every one of them. Only fields present in BOTH neighbours are compared.

    ponytail: a monotonicity reset is the cheapest multi-game tell and needs no external
    schedule; upgrade to a schedule join if a sport ever resets these legitimately.
    """
    segments = 1
    prev: Optional[Dict[str, float]] = None
    for st in states:
        if "home_score" not in st:
            continue
        if prev is not None:
            back = (st.get("home_score", 0.0) < prev.get("home_score", 0.0)
                    or st.get("away_score", 0.0) < prev.get("away_score", 0.0))
            now, before = _clock(st), _clock(prev)
            if now is not None and before is not None and now < before:
                back = True
            if back:
                segments += 1
        prev = st
    return segments


def scan_game(path: Path) -> Dict[str, Any]:
    """Per-game integrity record. A malformed file is reported, never raised."""
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    rec: Dict[str, Any] = {"game_id": path.stem, "n_ticks": len(rows),
                           "short_path": len(rows) < MIN_TICKS}
    if not rows:
        rec.update({"empty": True, "label_disagree": False, "frozen_market": False,
                    "ts_outside": False, "multi_game": False, "segments": 0,
                    "leader": None, "stateless_only": True})
        return rec

    states = [parse_state(r.get("state_summary", "")) for r in rows]
    stated = [st for st in states if "home_score" in st]
    rec["n_stateless_ticks"] = len(states) - len(stated)
    rec["stateless_only"] = not stated

    # The LAST STATED tick is the corpus's best view of the final score; a trailing
    # stateless "live" tick would otherwise read as 0-0 and hide a real disagreement.
    final = stated[-1] if stated else {}
    home, away = final.get("home_score", 0.0), final.get("away_score", 0.0)
    outcome = rows[-1].get("outcome")
    leader = "home" if home > away else ("away" if away > home else None)
    expected = {"home": 1.0, "away": 0.0}.get(leader)
    rec["final_home"], rec["final_away"] = home, away
    rec["last_state_clock"] = _clock(final) if final else None
    rec["outcome"] = outcome
    rec["leader"] = leader
    rec["margin"] = abs(home - away)
    rec["label_disagree"] = bool(leader is not None and outcome != expected)

    probs = {r.get("market_prob") for r in rows if r.get("market_prob") is not None}
    rec["n_distinct_market"] = len(probs)
    rec["frozen_market"] = len(probs) <= 1

    gdate = ticker_date(path.stem)
    outside = 0
    if gdate is not None:
        window = {gdate, gdate + timedelta(days=1)}
        outside = sum(1 for r in rows if _tick_date(r.get("ts")) not in window)
    rec["ticker_date"] = gdate.isoformat() if gdate else None
    rec["n_ticks_outside_window"] = outside
    rec["ts_outside"] = outside > 0

    rec["segments"] = _count_segments(states)
    rec["multi_game"] = rec["segments"] > 1
    return rec


FLAGS: Tuple[str, ...] = ("label_disagree", "frozen_market", "ts_outside",
                          "short_path", "multi_game", "stateless_only")


def scan_sport(sport_dir: Path) -> Dict[str, Any]:
    """Aggregate every game file of one sport plus its leader-at-last-tick table."""
    games = [scan_game(p) for p in sorted(sport_dir.glob("*.jsonl"))]
    totals = {flag: sum(1 for g in games if g.get(flag)) for flag in FLAGS}
    leader_freq: Dict[str, Dict[str, Any]] = {}
    for m in MARGINS:
        pool = [g for g in games if g.get("leader") and g.get("margin", 0.0) >= m]
        agree = sum(1 for g in pool if not g["label_disagree"])
        leader_freq["margin_ge_%d" % m] = {
            "n_games": len(pool), "n_label_agrees": agree,
            "observed_freq": round(agree / len(pool), 4) if pool else None,
            "expected_freq": 1.0,
        }
    return {
        "sport": sport_dir.name,
        "n_games": len(games),
        "n_ticks": sum(g["n_ticks"] for g in games),
        "n_stateless_ticks": sum(g.get("n_stateless_ticks", 0) for g in games),
        "n_tied_final": sum(1 for g in games if g.get("leader") is None),
        "totals": totals,
        "leader_at_last_tick": leader_freq,
        "offenders": {flag: sorted(g["game_id"] for g in games if g.get(flag))
                      for flag in FLAGS},
        "games": games,
    }


def scan_root(root: Path) -> Dict[str, Any]:
    """Scan every sport subdirectory (names starting with '_' are skipped)."""
    sports = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_"))
    report: Dict[str, Any] = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": str(root),
        "min_ticks": MIN_TICKS,
        "sports": {p.name: scan_sport(p) for p in sports},
    }
    report["n_label_disagree_total"] = sum(
        s["totals"]["label_disagree"] for s in report["sports"].values())
    return report


def _row(cells: List[str], widths: List[int]) -> str:
    return "| " + " | ".join(c.ljust(w) for c, w in zip(cells, widths)) + " |"


def _table(head: List[str], body: List[List[str]]) -> List[str]:
    widths = [max([len(head[i])] + [len(r[i]) for r in body]) for i in range(len(head))]
    sep = "|" + "|".join("-" * (w + 2) for w in widths) + "|"
    return [_row(head, widths), sep] + [_row(r, widths) for r in body]


def summary_table(report: Dict[str, Any]) -> str:
    """ASCII summary. Calibration vocabulary only -- no edge/ROI framing."""
    body = []
    for name, s in sorted(report["sports"].items()):
        t = s["totals"]
        body.append([name, str(s["n_games"]), str(s["n_ticks"]),
                     str(s["n_stateless_ticks"]),
                     str(t["label_disagree"]), str(t["frozen_market"]),
                     str(t["ts_outside"]), str(t["short_path"]), str(t["multi_game"])])
    lines = ["INGAME JOIN INTEGRITY -- %s" % report["root"], ""]
    lines += _table(["sport", "games", "ticks", "stateless", "label_dis", "frozen_mkt",
                     "ts_outside", "short(<%d)" % report["min_ticks"], "multi_game"],
                    body)

    lbody = []
    for name, s in sorted(report["sports"].items()):
        for key, v in s["leader_at_last_tick"].items():
            obs = "n/a" if v["observed_freq"] is None else "%.4f" % v["observed_freq"]
            lbody.append([name, key.replace("margin_ge_", ">="), str(v["n_games"]),
                          obs, "1.0000"])
    lines += ["", "LEADER AT LAST TICK -- label agreement (expected 1.0000)", ""]
    lines += _table(["sport", "margin", "games", "observed", "expected"], lbody)

    for name, s in sorted(report["sports"].items()):
        ids = s["offenders"]["label_disagree"]
        if ids:
            shown = ids[:MAX_IDS_IN_TABLE]
            lines += ["", "%s label_disagree ids (%d of %d shown):"
                      % (name, len(shown), len(ids))] + ["  " + i for i in shown]
            if len(ids) > len(shown):
                lines.append("  ... full list in the JSON report")
    lines += ["", "TOTAL label disagreements: %d" % report["n_label_disagree_total"]]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--out", default=None, help="write the full JSON report here")
    args = ap.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print("NO_DATA: %s is not a directory" % root)
        return 2
    report = scan_root(root)
    print(summary_table(report))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=1, ensure_ascii=True), encoding="utf-8")
        print("\nwrote %s" % out)
    return 1 if report["n_label_disagree_total"] else 0


if __name__ == "__main__":
    sys.exit(main())

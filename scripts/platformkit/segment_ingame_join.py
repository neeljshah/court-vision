"""scripts.platformkit.segment_ingame_join -- rebuild the in-game JOINED tick corpus
so that one file holds exactly one real game.

WHY: the pre-guard capture bridge matched a Kalshi ticker to a live game by TEAM PAIR
only (inplay_capture_loop._scan_live_by_legs), so consecutive games of an MLB series
were appended to one ticker file, and ticker_settlement_join stamped that ticker's ONE
(correct) settlement label onto EVERY row. 126 of 227 MLB files hold more than one game
and 27,076 ticks carry another game's label --
docs/research/ingame_join_integrity_2026-09-16.md.

WHAT THIS DOES (read-only on the existing corpus; writes a NEW sibling directory):
  1. SPLIT each tick path at a monotonicity break (_is_break). STATELESS ticks
     (state_summary == "live", ~1/3 of MLB) carry no ordering information, so they
     never break a segment; they attach by time to the segment open when they arrive.
  2. KEEP the one segment the settlement label belongs to (select_segment), or
     QUARANTINE the file. An unattributable tick path is an honest drop, never a guess.
  3. WRITE it to <root>/<sport><SUFFIX>/<TICKER>.jsonl, same row schema, with a
     `segment_audit` object on the FIRST row only (a header field; the file stays a
     rows-only jsonl every existing reader can consume unchanged).

The original corpus is never modified in place and never deleted. Calibration
vocabulary only: this changes WHICH ticks a calibration bin sees, makes no claim about
profit, and a corrected corpus may move the numbers either way.

From /c/Users/neelj/nba-ai-system:
  python scripts/platformkit/segment_ingame_join.py --out-json <report.json>
  python -m pytest scripts/platformkit/test_segment_ingame_join.py -q
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:  # bare-script invocation
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.check_ingame_join_integrity import parse_state  # noqa: E402

DEFAULT_ROOT = _REPO / "data" / "cache" / "ingame_grade_joined"
DEFAULT_SPORTS: Tuple[str, ...] = ("mlb", "soccer_intl")
SUFFIX = "_segmented"
# GAP_HOURS: a game is ~3h and the observed contaminating gaps are 15-28h (a day boundary),
# so 6h splits those and still clears a rain delay. BACKWARD_HOURS: capture jitter runs to
# -243s on 107 live files and a strict >0 rule split real games there; score/clock
# monotonicity catches a genuine new game, so this only clears the jitter.
GAP_HOURS, BACKWARD_HOURS = 6.0, 0.25
LABEL_SIDE = {1.0: "home", 0.0: "away", 0.5: "tie"}  # label -> side the final score shows


def _ts(value: Any) -> Optional[datetime]:
    try:
        return datetime.strptime(str(value)[:19], "%Y-%m-%dT%H:%M:%S")
    except (ValueError, TypeError):
        return None


def read_rows(path: Path) -> List[Dict[str, Any]]:
    """Every parseable jsonl row. A malformed line is skipped, never raised."""
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _clock(state: Dict[str, float]) -> Optional[float]:
    """The sport's monotone within-game clock: MLB inning, soccer minute."""
    return state["inning"] if "inning" in state else state.get("minute")


def _is_break(state: Dict[str, float], prev: Optional[Dict[str, float]],
              now: Optional[datetime], prev_ts: Optional[datetime],
              gap_hours: float) -> bool:
    """True when this tick cannot belong to the same game as the previous one."""
    if prev_ts is not None and now is not None:
        hours = (now - prev_ts).total_seconds() / 3600.0
        if hours < -BACKWARD_HOURS or hours > gap_hours:
            return True
    if "home_score" not in state or prev is None:
        return False
    home, away = state.get("home_score", 0.0), state.get("away_score", 0.0)
    if home < prev.get("home_score", 0.0) or away < prev.get("away_score", 0.0):
        return True
    clock_now, clock_prev = _clock(state), _clock(prev)
    if clock_now is not None and clock_prev is not None and clock_now < clock_prev:
        return True
    return home == 0.0 and away == 0.0 and bool(prev.get("home_score", 0.0)
                                                or prev.get("away_score", 0.0))


def split_segments(rows: Sequence[Dict[str, Any]],
                   gap_hours: float = GAP_HOURS) -> List[List[Dict[str, Any]]]:
    """Split a tick path into per-game segments. Stateless rows never break a
    segment; they join whichever segment is open when they arrive."""
    segments: List[List[Dict[str, Any]]] = [[]]
    prev_state: Optional[Dict[str, float]] = None
    prev_ts: Optional[datetime] = None
    for row in rows:
        state = parse_state(row.get("state_summary", ""))
        now = _ts(row.get("ts"))
        if _is_break(state, prev_state, now, prev_ts, gap_hours):
            segments.append([])
        segments[-1].append(row)
        if "home_score" in state:
            prev_state = state
        if now is not None:
            prev_ts = now
    return [s for s in segments if s]


def segment_end(segment: Sequence[Dict[str, Any]]) -> Optional[Tuple[str, Optional[datetime]]]:
    """(side leading at the last STATED tick, that tick's timestamp), or None when
    the segment holds no stated tick at all."""
    last: Optional[Tuple[Dict[str, float], Optional[datetime]]] = None
    for row in segment:
        state = parse_state(row.get("state_summary", ""))
        if "home_score" in state:
            last = (state, _ts(row.get("ts")))
    if last is None:
        return None
    state, when = last
    home, away = state.get("home_score", 0.0), state.get("away_score", 0.0)
    return ("home" if home > away else "away" if away > home else "tie"), when


def select_segment(segments: Sequence[Sequence[Dict[str, Any]]], outcome: Any,
                   close_ts: Optional[datetime]) -> Tuple[Optional[int], str]:
    """Index of the segment the settlement label belongs to, plus a reason string.

    ANCHOR then VERIFY. The anchor is `close_ts`, the settlement timestamp the label
    itself carries: the segment whose last stated tick is nearest it is the game that
    settled (measured on the live corpus, that distance is 0 seconds for every
    resolvable file). The label side is then a VERIFICATION gate, not the selector,
    because ranking by label agreement first lets an earlier contaminated segment
    outrank a truncated true one. A segment with no stated tick is never selected.
    """
    label_side = LABEL_SIDE.get(outcome)
    if label_side is None:
        return None, "no_settlement_label"
    ranked: List[Tuple[float, int]] = []
    ends: Dict[int, str] = {}
    for index, segment in enumerate(segments):
        end = segment_end(segment)
        if end is None:
            continue
        side, when = end
        ends[index] = side
        if close_ts is None or when is None:
            distance = float(len(segments) - index)  # no anchor: last stated wins
        else:
            distance = abs((when - close_ts).total_seconds())
        ranked.append((distance, index))
    if not ranked:
        return None, "no_stated_tick"
    ranked.sort()
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None, "ambiguous_two_segments_equidistant"
    index = ranked[0][1]
    side = ends[index]
    if side == label_side:
        return index, "label_agrees"
    if side == "tie":
        # Capture truncated before the end, so the last stated score is not the final
        # one. The label still belongs to this game -- the separate truncation defect,
        # not contamination. Kept and flagged so a consumer can exclude it.
        return index, "label_indeterminate_truncated"
    return None, "label_disagrees"


def _stateless(rows: Sequence[Dict[str, Any]]) -> int:
    return sum(1 for r in rows if "home_score" not in parse_state(r.get("state_summary", "")))


def segment_file(path: Path, sport: str = "", gap_hours: float = GAP_HOURS) -> Dict[str, Any]:
    """{"rows": kept rows (empty when quarantined), "audit": the segment_audit dict}."""
    rows = read_rows(path)
    audit: Dict[str, Any] = {
        "game_id": path.stem, "segments_found": 0, "segment_kept": None,
        "ticks_in": len(rows), "ticks_kept": 0, "ticks_dropped": len(rows),
        "stateless_in": _stateless(rows), "stateless_kept": 0, "reason": "empty_file",
        "source": "%s/%s" % (sport, path.name) if sport else path.name,
        "tool": "scripts/platformkit/segment_ingame_join.py",
    }
    if not rows:
        return {"rows": [], "audit": audit}
    segments = split_segments(rows, gap_hours)
    index, reason = select_segment(segments, rows[-1].get("outcome"),
                                   _ts(rows[-1].get("close_ts")))
    audit.update(segments_found=len(segments), reason=reason)
    if index is None:
        return {"rows": [], "audit": audit}
    kept = list(segments[index])
    audit.update(segment_kept=index, ticks_kept=len(kept),
                 ticks_dropped=len(rows) - len(kept), stateless_kept=_stateless(kept))
    return {"rows": kept, "audit": audit}


def write_segment(out_path: Path, result: Dict[str, Any]) -> None:
    """Write the kept rows, stamping `segment_audit` onto the FIRST row only."""
    rows = [dict(r) for r in result["rows"]]
    rows[0]["segment_audit"] = result["audit"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(json.dumps(r, ensure_ascii=True) + "\n" for r in rows),
                        encoding="utf-8")


def run_sport(root: Path, sport: str, suffix: str = SUFFIX,
              gap_hours: float = GAP_HOURS, write: bool = True) -> Dict[str, Any]:
    """Segment one sport directory into <sport><suffix>/."""
    src, dst = root / sport, root / (sport + suffix)
    files = sorted(src.glob("*.jsonl"))
    s: Dict[str, Any] = {
        "sport": sport, "src": str(src), "dst": str(dst), "files_in": len(files),
        "files_kept": 0, "files_quarantined": 0, "ticks_in": 0, "ticks_kept": 0,
        "stateless_in": 0, "stateless_kept": 0, "quarantined": [], "kept": [],
    }
    for path in files:
        result = segment_file(path, sport, gap_hours)
        audit = result["audit"]
        s["ticks_in"] += audit["ticks_in"]
        s["stateless_in"] += audit["stateless_in"]
        if not result["rows"]:
            s["files_quarantined"] += 1
            s["quarantined"].append(audit)
            continue
        s["files_kept"] += 1
        s["ticks_kept"] += audit["ticks_kept"]
        s["stateless_kept"] += audit["stateless_kept"]
        s["kept"].append(audit)
        if write:
            write_segment(dst / path.name, result)
    return s


def summary_table(report: Dict[str, Any]) -> str:
    """ASCII per-sport table. Calibration vocabulary only."""
    head = ["sport", "files_in", "files_kept", "files_quar", "ticks_in", "ticks_kept",
            "stateless_in", "stateless_dropped"]
    body = [[s["sport"], str(s["files_in"]), str(s["files_kept"]),
             str(s["files_quarantined"]), str(s["ticks_in"]), str(s["ticks_kept"]),
             str(s["stateless_in"]), str(s["stateless_in"] - s["stateless_kept"])]
            for s in report["sports"]]
    widths = [max([len(head[i])] + [len(r[i]) for r in body]) for i in range(len(head))]
    rows = ["| " + " | ".join(c.ljust(w) for c, w in zip(head, widths)) + " |",
            "|" + "|".join("-" * (w + 2) for w in widths) + "|"]
    rows += ["| " + " | ".join(c.ljust(w) for c, w in zip(r, widths)) + " |" for r in body]
    lines = ["INGAME SEGMENTATION -- %s" % report["root"], ""] + rows
    for s in report["sports"]:
        lines.append("")
        for bucket in ("kept", "quarantined"):
            tally: Dict[str, int] = {}
            for entry in s[bucket]:
                tally[entry["reason"]] = tally.get(entry["reason"], 0) + 1
            lines.append("%s %s by reason: %s" % (s["sport"], bucket, tally or "{}"))
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--sport", action="append", dest="sports", default=None)
    ap.add_argument("--suffix", default=SUFFIX)
    ap.add_argument("--gap-hours", type=float, default=GAP_HOURS)
    ap.add_argument("--dry-run", action="store_true", help="measure, write nothing")
    ap.add_argument("--out-json", default=None, help="full JSON report incl. quarantine")
    args = ap.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print("NO_DATA: %s is not a directory" % root)
        return 2
    sports = args.sports or list(DEFAULT_SPORTS)
    report = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": str(root), "suffix": args.suffix, "gap_hours": args.gap_hours,
        "sports": [run_sport(root, s, args.suffix, args.gap_hours, not args.dry_run)
                   for s in sports if (root / s).is_dir()],
    }
    print(summary_table(report))
    if args.out_json:
        out = Path(args.out_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=1, ensure_ascii=True), encoding="utf-8")
        print("\nwrote %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""compute_clv.py — closing-line value tracker for the cycle-68 bet log.

CLV (closing-line value) is the single most-trusted indicator of long-term
betting skill: did the line at your bet placement reflect a better price
than where the sharps moved it by tip-off? Positive CLV across many bets
guarantees positive long-term ROI even when short-term variance hides it.

This script joins two artifacts:
  data/bets/<date>.csv          (cycle 68 — placement-time line + odds)
  data/lines/<date>_close.csv   (cycle 59 — re-fetched ~5min before tip)

The closing snapshot uses the SAME schema as fetch_dk_props (player, opp,
venue, stat, line, over_odds, under_odds). To produce it, run
fetch_dk_props.py with `--out data/lines/<date>_close.csv` near tip-off.

Output: bet_log enriched with closing_line, closing_odds, clv_pts (signed
movement in the bettor's favor), clv_cents (probability shift in cents).

  python scripts/compute_clv.py data/bets/2026-05-24.csv \\
      data/lines/2026-05-24_close.csv \\
      --out data/bets/2026-05-24_clv.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _name_key(s: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def _american_to_implied_prob(odds: int) -> float:
    """Vig-included implied probability for American odds."""
    if odds >= 100:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def load_closing_lines(path: str) -> Dict[Tuple[str, str], dict]:
    """Return {(name_key, stat_key): {line, over_odds, under_odds}}.

    Closing snapshots are keyed by (player, stat) — the line value itself
    can have moved, which is the whole point.
    """
    out: Dict[Tuple[str, str], dict] = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            key = (_name_key(r.get("player", "")),
                   (r.get("stat", "") or "").lower().strip())
            try:
                line = float(r.get("line", "nan"))
                over_odds = int(r.get("over_odds", -110))
                under_odds = int(r.get("under_odds", -110))
            except ValueError:
                continue
            if not key[0] or not key[1]:
                continue
            out[key] = {"line": line, "over_odds": over_odds,
                        "under_odds": under_odds}
    return out


def compute_one(bet: dict, closing: dict) -> dict:
    """Score one bet vs the closing snapshot. Returns {closing_line,
    closing_odds, clv_pts, clv_cents, beat_close}.

    clv_pts:  positive when the line moved AGAINST the closing-side
              (i.e. the bettor got the better number).
    clv_cents: same idea in implied-probability cents. A +5 cents CLV
               means the bettor got a price worth 5% more probability than
               the close.
    beat_close: True if CLV > 0 (most important field for tracking sharp%).
    """
    side = (bet.get("side", "") or "").upper()
    try:
        placed_line = float(bet.get("line", "nan"))
        placed_odds = int(bet.get("odds", -110) or -110)
    except ValueError:
        return {"closing_line": "", "closing_odds": "",
                "clv_pts": "", "clv_cents": "", "beat_close": ""}
    close_line = closing["line"]
    close_odds = (closing["over_odds"] if side == "OVER"
                  else closing["under_odds"])

    # Line movement (in stat units). CORRECT (CV_CLV_LINE_SIGN_FIX=1): CLV is
    # positive when you got a BETTER NUMBER than the close. OVER -> better is a
    # LOWER number, so you beat the close when it closes HIGHER:
    #   OVER  -> closing - placed ; UNDER -> placed - closing.
    # LEGACY default (flag OFF) inverted both signs (GRADING_SETTLE_CLV_AUDIT.md
    # B-1). Gated default-OFF = byte-identical legacy reports until flipped.
    _clv_sign_fix = (os.environ.get("CV_CLV_LINE_SIGN_FIX", "").strip().lower()
                     not in ("", "0", "false", "no", "off"))
    if side == "OVER":
        clv_pts = round((close_line - placed_line) if _clv_sign_fix
                        else (placed_line - close_line), 2)
    else:
        clv_pts = round((placed_line - close_line) if _clv_sign_fix
                        else (close_line - placed_line), 2)

    # Implied-prob movement. Compare vig-included implied probs at placed
    # vs closing odds for THE SAME SIDE. clv_cents = (placed_implied -
    # closing_implied) * 100. NEGATIVE delta means you got a better price.
    # We flip the sign so positive = good (the bettor's edge).
    placed_prob = _american_to_implied_prob(placed_odds)
    close_prob = _american_to_implied_prob(close_odds)
    clv_cents = round((close_prob - placed_prob) * 100.0, 2)

    return {
        "closing_line":  f"{close_line:g}",
        "closing_odds":  close_odds,
        "clv_pts":       clv_pts,
        "clv_cents":     clv_cents,
        "beat_close":    "Y" if (clv_pts > 0 or clv_cents > 0) else "N",
    }


def compute_clv(bets: List[dict],
                  closing: Dict[Tuple[str, str], dict]) -> Tuple[List[dict], dict]:
    """Enrich each bet with closing info; return (rows, summary)."""
    out: List[dict] = []
    matched = 0; beat = 0
    total_clv_pts = 0.0; total_clv_cents = 0.0
    for b in bets:
        key = (_name_key(b.get("player", "")),
               (b.get("stat", "") or "").lower().strip())
        c = closing.get(key)
        if c is None:
            row = dict(b)
            row.update({"closing_line": "", "closing_odds": "",
                        "clv_pts": "", "clv_cents": "",
                        "beat_close": "NA"})
            out.append(row); continue
        scored = compute_one(b, c)
        matched += 1
        if scored["beat_close"] == "Y":
            beat += 1
            try:
                total_clv_pts += float(scored["clv_pts"]) if scored["clv_pts"] != "" else 0.0
            except (TypeError, ValueError):
                pass
            try:
                total_clv_cents += float(scored["clv_cents"]) if scored["clv_cents"] != "" else 0.0
            except (TypeError, ValueError):
                pass
        row = dict(b); row.update(scored)
        out.append(row)
    summary = {
        "total":         len(bets),
        "matched":       matched,
        "unmatched":     len(bets) - matched,
        "beat_close":    beat,
        "beat_pct":      (100.0 * beat / matched) if matched else 0.0,
        "mean_clv_pts":  (total_clv_pts / beat) if beat else 0.0,
        "mean_clv_cents": (total_clv_cents / beat) if beat else 0.0,
    }
    return out, summary


def write_csv(out_path: str, rows: List[dict]) -> int:
    if not rows:
        return 0
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fieldnames = list(rows[0].keys())
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bet_log", help="bet log CSV from compare_to_lines --bet-log")
    ap.add_argument("closing_lines", help="closing-line snapshot CSV (canonical schema)")
    ap.add_argument("--out", default=None,
                    help="Output path (default: <bet_log>_clv.csv)")
    args = ap.parse_args()

    if not os.path.exists(args.bet_log):
        print(f"[fail] bet log not found: {args.bet_log}")
        return 1
    bets = []
    with open(args.bet_log, encoding="utf-8") as fh:
        bets = list(csv.DictReader(fh))
    if not bets:
        print("[done] bet log is empty"); return 0

    closing = load_closing_lines(args.closing_lines)
    if not closing:
        print(f"[warn] closing-line snapshot empty or missing: {args.closing_lines}")

    rows, summary = compute_clv(bets, closing)
    out = args.out or args.bet_log.replace(".csv", "_clv.csv")
    n = write_csv(out, rows)
    print(f"  Wrote {n} CLV-enriched rows -> {out}")
    print("\n== CLV summary ==")
    print(f"Bets: {summary['matched']} matched / {summary['unmatched']} unmatched "
          f"({summary['total']} total)")
    if summary['matched']:
        print(f"Beat the close: {summary['beat_close']}/{summary['matched']} "
              f"= {summary['beat_pct']:.1f}%")
        if summary['beat_close']:
            print(f"Mean CLV when beating: {summary['mean_clv_pts']:+.2f} stat units, "
                  f"{summary['mean_clv_cents']:+.2f} cents")
    return 0


if __name__ == "__main__":
    # CV_CLV_LINE_SIGN_FIX (owner-flipped 2026-06-05): use the CORRECT CLV-line sign
    # by default for the operator CLI (the legacy default was inverted, B-1). Set here
    # (CLI entry only, NOT in main()/compute_one) so the gated default-OFF unit-test
    # baseline stays byte-identical; setdefault preserves the CV_CLV_LINE_SIGN_FIX=0
    # escape hatch. Reporting-only; training-label clv_label uses the price-based path.
    os.environ.setdefault("CV_CLV_LINE_SIGN_FIX", "1")
    sys.exit(main())

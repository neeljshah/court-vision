"""scripts.platformkit.grade_paper -- auto-settle/grade PAPER bets once games end.

Takes the OPEN paper bets in the CLV ledger, fetches each game's FINAL result from
the keyless ESPN scoreboard (reusing live_board), and -- ONLY for genuinely final
games -- appends a SETTLED twin carrying the actual win/loss, paper P&L, and CLV.
grade_summary() is the honest scoreboard (hit-rate, paper ROI, mean CLV,
%-beat-close, by sport + market) of whether the paper strategy actually works.

HONESTY CONTRACT (binding): NEVER fabricates an outcome or close -- a game is settled
ONLY when feed state is in {"post","final"} AND both scores are present; else SKIPPED
as pending. Append-only + a settle_key guard => IDEMPOTENT (no double-settle). Paper
only (every twin executed=False; no money/book API). CLV reuses
clv_ledger.settle_closing_line/devig -- never re-derived; a true close is rarely
stored, so we use the LAST-OBSERVED price as a LABELLED proxy (clv_is_proxy=True), and
with no price grade win/loss only (clv_pct=None). No $-edge claim; paper ROI is a
small-N hypothesis, CLV is the honest yardstick.

Build only under scripts/platformkit/; <=300 LOC; no secrets; no $-edge claim.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.platformkit import clv_ledger as _clv
from scripts.platformkit.frontend import live_board as _lb

# Sports we know how to fetch finals for (ESPN keyless scoreboard via live_board).
_KNOWN_SPORTS = ("mlb", "nba", "soccer_intl", "soccer")
_FINAL_STATES = ("post", "final")


def _settle_key(bet: Dict[str, Any]) -> str:
    """Stable identity for one open bet, used to dedupe settlements (idempotency)."""
    return "|".join(str(bet.get(k, "")) for k in
                    ("sport", "matchup", "side", "taken_book", "taken_decimal", "ts"))


def _norm_tokens(text: str) -> List[str]:
    """Lowercased alpha tokens of a team name / abbreviation, for fuzzy matchup match."""
    return [t for t in re.split(r"[^a-z0-9]+", str(text).lower()) if t]


def _matchup_sides(matchup: str) -> Tuple[Optional[str], Optional[str]]:
    """Split a 'A @ B' / 'A vs B' matchup string into (left, right) raw labels.

    We do NOT infer home/away from string order -- only use the two labels to identify
    WHICH game this is. Win/loss uses the ledger 'side' vs the feed's home/away scores.
    """
    s = str(matchup)
    for sep in (" @ ", "@", " vs ", " vs. ", " v ", " - ", " at "):
        if sep in s:
            a, _, b = s.partition(sep)
            return a.strip(), b.strip()
    return (s.strip() or None), None


def _team_match(label: Optional[str], game_display: str, game_abbr: Optional[str]) -> bool:
    """True if a matchup label refers to the game's team (by abbr or name tokens)."""
    if not label:
        return False
    lab = _norm_tokens(label)
    if not lab:
        return False
    if game_abbr and "".join(lab) == game_abbr.lower():
        return True
    disp = set(_norm_tokens(game_display))
    abbr = set(_norm_tokens(game_abbr)) if game_abbr else set()
    # Every label token must appear in the game's name/abbr token set (handles
    # "CIN" -> "Cincinnati Reds", "NYK"/"Knicks", etc.).
    return all(t in disp or t in abbr for t in lab)


def _find_final_game(bet: Dict[str, Any], games: List[Dict[str, Any]]
                     ) -> Optional[Dict[str, Any]]:
    """The FINAL game whose two teams match this bet's matchup. None if not found/final."""
    left, right = _matchup_sides(bet.get("matchup", ""))
    for g in games:
        if g.get("state") not in _FINAL_STATES:
            continue
        hd, ha = g.get("home"), g.get("home_abbr")
        ad, aa = g.get("away"), g.get("away_abbr")
        # both labels must map onto the two teams (either orientation)
        m1 = (_team_match(left, hd, ha) and _team_match(right, ad, aa))
        m2 = (_team_match(left, ad, aa) and _team_match(right, hd, ha))
        if (m1 or m2) and g.get("home_score") is not None and g.get("away_score") is not None:
            return g
    return None


def _outcome(side: str, home_score: int, away_score: int) -> Optional[str]:
    """Moneyline win/loss for the backed two-way *side*. None on a draw (push)."""
    if home_score == away_score:
        return None  # draw -> push (refund); soccer 90-min can draw
    home_won = home_score > away_score
    if side == "home":
        return "win" if home_won else "loss"
    return "win" if not home_won else "loss"


def _paper_pnl(outcome: Optional[str], taken_decimal: float, stake: float) -> float:
    """Paper P&L for a settled moneyline bet. Push -> 0.0 (stake returned)."""
    if outcome == "win":
        return round((float(taken_decimal) - 1.0) * float(stake), 6)
    if outcome == "loss":
        return round(-float(stake), 6)
    return 0.0  # push


def grade_one(bet: Dict[str, Any], game: Dict[str, Any]) -> Dict[str, Any]:
    """Build a SETTLED twin of *bet* from a FINAL *game*. Pure (no I/O).

    Win/loss is the actual final score vs the bet's home/away side. CLV reuses
    clv_ledger.settle_closing_line against a (proxy) close when a price is available;
    otherwise clv_pct is left None (win/loss only).
    """
    hs, as_ = int(game["home_score"]), int(game["away_score"])
    side = str(bet.get("side", "")).strip().lower()
    outcome = _outcome(side, hs, as_)
    stake = float(bet.get("stake", 0.0) or 0.0)
    taken_decimal = float(bet["taken_decimal"])

    settled = dict(bet)
    # CLV: use a stored closing line if present, else the last-observed market price
    # as a labelled proxy. clv_ledger fills fair_close / clv_pct / beat_close.
    ch = bet.get("closing_decimal_home")
    ca = bet.get("closing_decimal_away")
    is_proxy = False
    if ch is None or ca is None:
        ch = bet.get("last_decimal_home") or bet.get("close_proxy_home")
        ca = bet.get("last_decimal_away") or bet.get("close_proxy_away")
        is_proxy = ch is not None and ca is not None
    if ch is not None and ca is not None:
        settled = _clv.settle_closing_line(settled, float(ch), float(ca))
        settled["clv_is_proxy"] = bool(is_proxy)
    else:
        settled["status"] = "settled"
        settled["settled_at"] = _clv._now_iso()
        settled["clv_pct"] = None
        settled["beat_close"] = None
        settled["clv_note"] = "no closing line or last-observed price; win/loss only"

    settled["graded"] = True
    settled["outcome"] = outcome if outcome is not None else "push"
    settled["home_score"] = hs
    settled["away_score"] = as_
    settled["pnl"] = _paper_pnl(outcome, taken_decimal, stake)
    settled["executed"] = False  # paper invariant preserved
    settled["settle_key"] = _settle_key(bet)
    return settled


def _load_predictions(predictions_path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    """Optional predictions store -> {matchup: row}. Tolerant: missing file -> {}."""
    if predictions_path is None:
        predictions_path = (_clv.DEFAULT_LEDGER.parent / "paper_predictions.jsonl")
    p = Path(predictions_path)
    if not p.exists():
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            mk = str(row.get("matchup", ""))
            if mk:
                out[mk] = row
    return out


def grade_open_bets(
    ledger_path: Optional[Path] = None,
    predictions_path: Optional[Path] = None,
    *,
    fetch_finals: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Settle every OPEN paper bet whose game is FINAL; append settled twins.

    Idempotent: a bet already settled (matching settle_key in the ledger) is skipped.
    Games that are not final are SKIPPED and counted as pending -- never fabricated.
    *fetch_finals* is injectable for tests: sport -> live_board-shaped payload (with
    a 'games' list). Default fetches the keyless ESPN scoreboard via live_board.
    """
    ledger_path = Path(ledger_path) if ledger_path else _clv.DEFAULT_LEDGER
    rows = _clv.load_ledger(ledger_path)
    open_bets = [r for r in rows if r.get("status") == "open"]
    already = {r.get("settle_key") for r in rows if r.get("settle_key")}
    # Optional enrichment: pull a stored closing-line proxy from the predictions store.
    preds = _load_predictions(predictions_path)

    fetch = fetch_finals if fetch_finals is not None else _lb.todays_live_games
    # Fetch each needed sport's scoreboard once.
    sports = sorted({str(b.get("sport", "")).lower() for b in open_bets})
    boards: Dict[str, List[Dict[str, Any]]] = {}
    feed_status: Dict[str, str] = {}
    for sp in sports:
        if not sp:
            continue
        try:
            payload = fetch(sp)
        except Exception:  # noqa: BLE001 - one bad feed never sinks the pass
            payload = {"status": "unavailable", "games": []}
        feed_status[sp] = str(payload.get("status", "unknown"))
        boards[sp] = list(payload.get("games") or [])

    settled_now: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []
    for bet in open_bets:
        key = _settle_key(bet)
        if key in already:
            continue  # idempotent: do not double-settle
        sp = str(bet.get("sport", "")).lower()
        # carry any stored proxy close from the predictions store into the bet
        pr = preds.get(str(bet.get("matchup", "")))
        if pr:
            for k in ("closing_decimal_home", "closing_decimal_away",
                      "last_decimal_home", "last_decimal_away"):
                if bet.get(k) is None and pr.get(k) is not None:
                    bet = {**bet, k: pr[k]}
        game = _find_final_game(bet, boards.get(sp, []))
        if game is None:
            pending.append({"matchup": bet.get("matchup"), "sport": sp,
                            "reason": "no final game matched"})
            continue
        settled = grade_one(bet, game)
        _clv.append_settlement(settled, path=ledger_path)
        already.add(key)
        settled_now.append({"matchup": settled.get("matchup"), "sport": sp,
                            "side": settled.get("side"), "outcome": settled["outcome"],
                            "pnl": settled["pnl"], "clv_pct": settled.get("clv_pct"),
                            "clv_is_proxy": settled.get("clv_is_proxy", False)})

    return {
        "n_open": len(open_bets),
        "n_settled_now": len(settled_now),
        "n_pending": len(pending),
        "feed_status": feed_status,
        "settled": settled_now,
        "pending": pending,
        "honest_note": ("Only genuinely FINAL games are settled; no outcome or close "
                        "is fabricated. Paper only (executed=False); CLV may be a "
                        "labelled last-price proxy. No $-edge is claimed."),
    }


def _grade_bucket(rows_in: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Hit-rate / paper-ROI / CLV stats over a set of graded rows. Pure."""
    dec = [r for r in rows_in if r.get("outcome") in ("win", "loss")]
    w = sum(1 for r in dec if r.get("outcome") == "win")
    st = sum(float(r.get("stake", 0.0) or 0.0) for r in rows_in)
    pl = sum(float(r.get("pnl", 0.0) or 0.0) for r in rows_in)
    cv = [float(r["clv_pct"]) for r in rows_in if r.get("clv_pct") is not None]
    return {
        "n": len(rows_in),
        "n_decided": len(dec),
        "hit_rate": round(100.0 * w / len(dec), 4) if dec else None,
        "paper_roi": round(100.0 * pl / st, 4) if st > 0 else None,
        "total_stake": round(st, 6),
        "total_pnl": round(pl, 6),
        "n_with_clv": len(cv),
        "mean_clv_pct": round(sum(cv) / len(cv), 6) if cv else None,
        "pct_beat_close": (round(100.0 * sum(1 for c in cv if c > 0) / len(cv), 4)
                           if cv else None),
    }


def grade_summary(ledger_path: Optional[Path] = None) -> Dict[str, Any]:
    """Honest scoreboard over GRADED rows (graded=True): hit-rate, paper ROI, CLV,
    %-beat-close, by sport + market. ROI = total pnl / total stake (paper)."""
    ledger_path = Path(ledger_path) if ledger_path else _clv.DEFAULT_LEDGER
    rows = [r for r in _clv.load_ledger(ledger_path) if r.get("graded")]
    if not rows:
        return {"n": 0, "hit_rate": None, "paper_roi": None, "mean_clv_pct": None,
                "pct_beat_close": None, "by_sport": {}, "by_market": {}}
    out = dict(_grade_bucket(rows))
    out["by_sport"] = {sp: _grade_bucket([r for r in rows if str(r.get("sport")) == sp])
                       for sp in sorted({str(r.get("sport", "unknown")) for r in rows})}
    out["by_market"] = {mk: _grade_bucket([r for r in rows
                                           if str(r.get("market", "moneyline")) == mk])
                        for mk in sorted({str(r.get("market", "moneyline")) for r in rows})}
    out["honest_note"] = ("Paper track record. ROI is small-N + paper, a hypothesis to "
                          "forward-test -- NOT a proven edge. CLV is the honest yardstick.")
    return out


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Settle/grade open paper bets on FINAL games.")
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--predictions", default=None)
    a = ap.parse_args(argv)
    ledger = Path(a.ledger) if a.ledger else None
    graded = grade_open_bets(ledger, Path(a.predictions) if a.predictions else None)
    print("GRADE PASS (paper, executed_any=False):")
    print("  open=%d settled_now=%d pending=%d"
          % (graded["n_open"], graded["n_settled_now"], graded["n_pending"]))
    print("  feed_status=%s" % json.dumps(graded["feed_status"]))
    for s in graded["settled"]:
        print("  SETTLED %s [%s] %s pnl=%s clv=%s%s"
              % (s["matchup"], s["side"], s["outcome"], s["pnl"], s["clv_pct"],
                 " (proxy)" if s.get("clv_is_proxy") else ""))
    print("SUMMARY:", json.dumps(grade_summary(ledger), indent=2, default=str))
    return 0


__all__ = [
    "grade_open_bets",
    "grade_summary",
    "grade_one",
]


if __name__ == "__main__":
    raise SystemExit(_main())

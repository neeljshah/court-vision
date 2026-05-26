"""place_bet.py - record intent to bet (probe R16_E7).

Manual placement workflow:
    operator runs this CLI -> a row gets appended to data/pnl_ledger.csv,
    then a copy-pasteable summary prints for the operator to mirror on the
    actual sportsbook UI (FanDuel / Bovada / Pinnacle / etc, which don't
    have public placement APIs).

Closes the "bet recommended -> bet ledger record" loop so CLV math can
track real entries.

Usage (R16_E7 design):
    python scripts/place_bet.py --player "Keldon Johnson" --stat reb \\
        --side OVER --line 3.5 --book pinnacle --odds +157 --stake 50

Optional:
    --bankroll 1000        # for the 5% per-bet stake cap (default 1000)
    --max-pct 5.0          # override the 5% cap
    --dry-run              # validate + preview summary, DO NOT touch ledger
    --slate <path>         # default: data/cache/probe_R15_tonight_slate_bets.json
    --game <game_id>       # bypass slate lookup
    --player-id <id>       # bypass slate lookup
    --team <abbrev>        # bypass slate lookup
    --model-pred <float>   # bypass slate lookup
    --model-prob <float>   # bypass slate lookup
    --kelly-pct <float>    # bypass slate lookup
    --no-slate-validate    # skip the slate cross-check (manual bets)

Back-compat: the legacy --odds takes an int (-115 or +157 both fine).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.betting.pnl_ledger import (   # noqa: E402
    place_bet as _ledger_place_bet,
    current_bankroll,
    american_to_payout,
    LEDGER_CSV,
    VALID_SIDES,
    VALID_STATS,
)
from src.betting.line_validator import (   # noqa: E402
    validate_bet_line,
    DEFAULT_MAX_STALENESS_SEC,
)

DEFAULT_SLATE = os.path.join(
    PROJECT_DIR, "data", "cache", "probe_R15_tonight_slate_bets.json",
)
DEFAULT_PLAYERINFO_DIR = os.path.join(PROJECT_DIR, "data", "cache", "playerinfo")


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def _name_key(s: str) -> str:
    """Strip accents + lower + collapse whitespace (matches injuries.name_key)."""
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.lower().strip())


_BOOK_ALIASES = {
    "pin": "pin", "pinnacle": "pin",
    "fd": "fd", "fanduel": "fd",
    "bov": "bov", "bovada": "bov",
    "dk": "dk", "draftkings": "dk",
    "mgm": "mgm", "betmgm": "mgm",
    "pp": "pp", "prizepicks": "pp",
}


def _book_canon(b: str) -> str:
    return _BOOK_ALIASES.get(str(b or "").lower().strip(), str(b or "").lower().strip())


_BOOK_PRETTY = {
    "pin": "PINNACLE", "fd": "FANDUEL", "bov": "BOVADA",
    "dk": "DRAFTKINGS", "mgm": "BETMGM", "pp": "PRIZEPICKS",
}


def load_slate(path: str) -> Optional[Dict]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def find_slate_match(
    slate: Dict,
    player: str,
    stat: str,
    side: str,
    book: str,
    line: float,
) -> Optional[Dict]:
    """Return the slate entry (preferring all_positive_bets_unfiltered, then ranked_bets)
    that matches (player, stat, side, book, line), or None.

    Match tolerance:
        - player: name_key equality
        - stat: lowercase equality
        - side: OVER/UNDER case-insensitive equality
        - book: canonical-alias equality
        - line: within 0.01 (handles 3.50 vs 3.5)
    """
    pkey = _name_key(player)
    stat_l = stat.lower()
    side_u = side.upper()
    book_c = _book_canon(book)
    candidates: List[Dict] = []
    for bucket in ("all_positive_bets_unfiltered", "ranked_bets"):
        for row in slate.get(bucket, []) or []:
            if _name_key(row.get("player", "")) != pkey: continue
            if str(row.get("stat", "")).lower() != stat_l: continue
            if str(row.get("side", "")).upper() != side_u: continue
            if _book_canon(row.get("book", "")) != book_c: continue
            if abs(float(row.get("line", -999)) - float(line)) > 0.01: continue
            candidates.append(row)
        if candidates:
            return candidates[0]
    return None


def resolve_player_id(player: str) -> Optional[str]:
    """Scan data/cache/playerinfo/*.json for a name match."""
    pkey = _name_key(player)
    if not os.path.isdir(DEFAULT_PLAYERINFO_DIR):
        return None
    for fn in os.listdir(DEFAULT_PLAYERINFO_DIR):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(DEFAULT_PLAYERINFO_DIR, fn), encoding="utf-8") as fh:
                d = json.load(fh)
            for info in d.get("common_player_info", []) or []:
                if _name_key(info.get("DISPLAY_FIRST_LAST", "")) == pkey:
                    return str(d.get("player_id") or info.get("PERSON_ID") or "")
        except (json.JSONDecodeError, OSError, KeyError):
            continue
    return None


def resolve_game_id_from_schedule(team: str, date_iso: Optional[str] = None) -> Optional[str]:
    """Best-effort lookup of game_id from any cached schedule file.

    Returns "" (empty string) when unresolved -- the ledger accepts blank
    game_id and CLV will fall back to (book, player, stat) matching.
    """
    # No reliable cached schedule on disk for the slate-day under all setups;
    # leave to caller. The placement still works with empty game_id.
    return None


# --------------------------------------------------------------------------- #
# Payout helpers                                                              #
# --------------------------------------------------------------------------- #
def potential_payout(stake: float, odds: int) -> Tuple[float, float]:
    """Return (total_return, net_profit)."""
    profit = stake * american_to_payout(int(odds))
    return round(stake + profit, 2), round(profit, 2)


def format_copy_paste(
    book: str, player: str, stat: str, side: str, line: float, odds: int,
    stake: float, bet_id: str, model_pred: Optional[float] = None,
    model_prob: Optional[float] = None, kelly_pct: Optional[float] = None,
    dry_run: bool = False,
) -> str:
    total, profit = potential_payout(stake, odds)
    pretty = _BOOK_PRETTY.get(_book_canon(book), book.upper())
    odds_s = f"{odds:+d}"
    lines = [
        ("[DRY-RUN] " if dry_run else "") +
        f"{pretty} - {player} {stat.upper()} {side.upper()} {line:g} @ {odds_s}",
        f"Stake: ${stake:.2f}",
        f"Potential payout: ${total:.2f} (profit ${profit:+.2f})",
    ]
    if model_pred is not None:
        m = f"Model pred: {model_pred:.2f}"
        if model_prob is not None:
            m += f"  |  P(win)={model_prob:.3f}"
        if kelly_pct is not None:
            m += f"  |  Kelly={kelly_pct:.2f}%"
        lines.append(m)
    lines.append(f"Bet ID: {bet_id}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Idempotency check                                                           #
# --------------------------------------------------------------------------- #
def find_duplicate_open(
    player: str, stat: str, side: str, book: str, line: float,
    ledger_path: str = LEDGER_CSV,
) -> Optional[str]:
    """Return bet_id of any existing OPEN row that matches the new placement.

    Prevents accidental double-recording when the operator re-runs the same
    command. Returns None if no duplicate.
    """
    if not os.path.exists(ledger_path):
        return None
    pkey = _name_key(player)
    stat_l = stat.lower()
    side_u = side.upper()
    book_c = _book_canon(book)
    import csv as _csv
    try:
        with open(ledger_path, encoding="utf-8") as fh:
            for r in _csv.DictReader(fh):
                if r.get("status") != "open":
                    continue
                if _name_key(r.get("player", "")) != pkey: continue
                if str(r.get("stat", "")).lower() != stat_l: continue
                if str(r.get("side", "")).upper() != side_u: continue
                if _book_canon(r.get("book", "")) != book_c: continue
                try:
                    if abs(float(r.get("line", -999)) - float(line)) > 0.01: continue
                except ValueError:
                    continue
                return r.get("bet_id")
    except OSError:
        return None
    return None


# --------------------------------------------------------------------------- #
# Main CLI                                                                    #
# --------------------------------------------------------------------------- #
def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Record intent to bet -> data/pnl_ledger.csv + copy-paste summary"
    )
    ap.add_argument("--player", required=True, help="player full name")
    ap.add_argument("--stat",   required=True, help="pts|reb|ast|fg3m|stl|blk|tov")
    ap.add_argument("--side",   required=True, choices=["OVER", "UNDER", "over", "under"])
    ap.add_argument("--line",   required=True, type=float)
    ap.add_argument("--book",   required=True, help="pinnacle|fanduel|bovada|...")
    ap.add_argument("--odds",   required=True, type=int, help="American odds, e.g. +157 or -115")
    ap.add_argument("--stake",  required=True, type=float, help="$ wagered")
    ap.add_argument("--bankroll", type=float, default=1000.0,
                    help="Bankroll for the 5%% per-bet cap (default 1000)")
    ap.add_argument("--max-pct", type=float, default=5.0,
                    help="Max stake as %% of bankroll (default 5.0)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Validate + preview the summary, do NOT touch the ledger")
    ap.add_argument("--slate", default=DEFAULT_SLATE,
                    help="Slate JSON path (default: probe_R15_tonight_slate_bets.json)")
    ap.add_argument("--no-slate-validate", action="store_true",
                    help="Skip the slate (player, stat, book) cross-check")
    ap.add_argument("--allow-duplicate", action="store_true",
                    help="Allow placing even if an OPEN duplicate row already exists")
    ap.add_argument("--force-stale", action="store_true",
                    help="Bypass the line-freshness validator (emergency / manual override)")
    ap.add_argument("--max-staleness-sec", type=int, default=DEFAULT_MAX_STALENESS_SEC,
                    help=f"Max snapshot age to accept (default {DEFAULT_MAX_STALENESS_SEC}s)")
    ap.add_argument("--lines-dir", default=None,
                    help="Override line-snapshot directory (for tests / probes)")
    # Optional overrides / fallbacks when not in slate
    ap.add_argument("--game",       default=None, help="NBA game_id (overrides slate)")
    ap.add_argument("--player-id",  default=None)
    ap.add_argument("--team",       default=None)
    ap.add_argument("--model-pred", type=float, default=None)
    ap.add_argument("--model-prob", type=float, default=None)
    ap.add_argument("--kelly-pct",  type=float, default=None)
    ap.add_argument("--strategy",   default=None,
                    help="Optional A/B strategy tag (legacy compatibility)")
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    ap = _build_parser()
    args = ap.parse_args(argv)

    side_u = args.side.upper()
    stat_l = args.stat.lower()
    if side_u not in VALID_SIDES:
        print(f"[fail] side must be OVER|UNDER, got {args.side!r}")
        return 2
    if stat_l not in VALID_STATS:
        print(f"[fail] stat must be one of {sorted(VALID_STATS)}, got {args.stat!r}")
        return 2
    if args.stake <= 0:
        print(f"[fail] stake must be > 0, got {args.stake}")
        return 2

    # ---- Stake cap (default 5% of bankroll) ----
    cap = float(args.bankroll) * (float(args.max_pct) / 100.0)
    if args.stake > cap + 1e-9:
        print(f"[fail] stake ${args.stake:.2f} exceeds {args.max_pct}% cap "
              f"of bankroll ${args.bankroll:.2f} (cap=${cap:.2f})")
        return 3

    # ---- Slate validation ----
    slate_row: Optional[Dict] = None
    if not args.no_slate_validate:
        slate = load_slate(args.slate)
        if slate is None:
            print(f"[warn] slate not found at {args.slate} -- proceeding without slate context")
        else:
            slate_row = find_slate_match(
                slate, args.player, stat_l, side_u, args.book, args.line,
            )
            if slate_row is None:
                print(f"[fail] no slate match for "
                      f"{args.player} {stat_l.upper()} {side_u} {args.line} @ "
                      f"{_book_canon(args.book)} in {os.path.basename(args.slate)}")
                print(f"       use --no-slate-validate to bypass, or check the slate "
                      f"with: python -c \"import json; "
                      f"d=json.load(open('{args.slate}')); "
                      f"print([(r['player'],r['stat'],r['side'],r['book'],r['line']) "
                      f"for r in d['all_positive_bets_unfiltered'][:20]])\"")
                return 4

    # ---- Idempotency ----
    if not args.allow_duplicate:
        # Read LEDGER_CSV at call time (not import time) so monkeypatched test
        # paths are honoured.
        dup = find_duplicate_open(
            args.player, stat_l, side_u, args.book, args.line,
            ledger_path=globals().get("LEDGER_CSV", LEDGER_CSV),
        )
        if dup:
            print(f"[fail] open duplicate already in ledger: bet_id={dup}")
            print( "       use --allow-duplicate to force a second placement")
            return 5

    # ---- Resolve player_id / team / game_id / model context from slate ----
    model_pred = args.model_pred
    model_prob = args.model_prob
    kelly_pct  = args.kelly_pct
    team       = args.team
    game_id    = args.game
    player_id  = args.player_id

    if slate_row is not None:
        if model_pred is None: model_pred = slate_row.get("model_q50")
        if model_prob is None: model_prob = slate_row.get("model_prob")
        if kelly_pct is None:
            k = slate_row.get("kelly_pct_used") or slate_row.get("kelly_pct_full")
            if k is not None: kelly_pct = float(k)
        if team is None: team = slate_row.get("team")
    if player_id is None:
        player_id = resolve_player_id(args.player)

    # ---- Line-freshness validator (probe R17_J2) ----
    # Confirms the (book, player, stat, line, odds) tuple still exists in a
    # snapshot newer than `max_staleness_sec`. Aborts before the ledger row is
    # written if the line / odds moved. `--force-stale` bypasses the check.
    validator_snapshot: Optional[Dict] = None
    validator_reason = "skipped (--force-stale)"
    validator_ok = True
    if not args.force_stale:
        validator_kwargs = {"max_staleness_sec": int(args.max_staleness_sec)}
        if args.lines_dir:
            validator_kwargs["lines_dir"] = args.lines_dir
        validator_ok, validator_reason, validator_snapshot = validate_bet_line(
            book=args.book,
            player_name=args.player,
            stat=stat_l,
            line=float(args.line),
            side=side_u,
            odds=int(args.odds),
            **validator_kwargs,
        )
        if not validator_ok:
            print(f"[fail] line-validator: {validator_reason}")
            if validator_snapshot:
                live_line = validator_snapshot.get("line")
                live_odds = validator_snapshot.get("odds_current")
                live_age  = validator_snapshot.get("age_sec")
                bits = []
                if live_line is not None:
                    bits.append(f"line={live_line:g}")
                if live_odds is not None:
                    bits.append(f"odds={live_odds:+d}")
                if live_age is not None:
                    bits.append(f"age={live_age:.0f}s")
                if bits:
                    print(f"       live snapshot: {' '.join(bits)} "
                          f"(captured_at={validator_snapshot.get('captured_at')})")
            print( "       use --force-stale to override (emergency only)")
            return 6
        print(f"[ok] line-validator: {validator_reason}")

    # ---- Dry-run preview ----
    if args.dry_run:
        preview_bet_id = "DRY-RUN-PREVIEW"
        msg = format_copy_paste(
            book=args.book, player=args.player, stat=stat_l, side=side_u,
            line=args.line, odds=args.odds, stake=args.stake,
            bet_id=preview_bet_id, model_pred=model_pred, model_prob=model_prob,
            kelly_pct=kelly_pct, dry_run=True,
        )
        print(msg)
        print(f"[ok] dry-run: ledger NOT modified, stake within {args.max_pct}% cap")
        if slate_row is not None:
            print(f"[ok] slate match: edge_pct={slate_row.get('edge_pct')}, "
                  f"ev_per_dollar={slate_row.get('ev_per_dollar')}")
        return 0

    # ---- Persist to ledger ----
    bet_id = _ledger_place_bet(
        game_id=game_id or "",
        player=args.player,
        stat=stat_l,
        line=float(args.line),
        side=side_u,
        book=_book_canon(args.book),
        odds=int(args.odds),
        stake=float(args.stake),
        model_pred=model_pred,
        model_prob=model_prob,
        kelly_pct=kelly_pct,
        player_id=player_id,
        team=team,
        bankroll_before=float(args.bankroll),
        strategy=args.strategy or "default",
    )

    msg = format_copy_paste(
        book=args.book, player=args.player, stat=stat_l, side=side_u,
        line=args.line, odds=args.odds, stake=args.stake, bet_id=bet_id,
        model_pred=model_pred, model_prob=model_prob, kelly_pct=kelly_pct,
        dry_run=False,
    )
    print(msg)
    print(f"[ok] appended to {LEDGER_CSV}")
    print(f"[ok] bankroll_after = ${current_bankroll():.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""clv.py - tier2-7 (loop 5).

Closing Line Value calculator that ties the P&L ledger (cycle 8762cd94)
to the live prop-line history (cycle 8d40558a).

CLV is the most honest signal of bet quality because it removes outcome
variance: did the line move IN YOUR FAVOR between placement and tip-off?
Positive CLV across a sample size predicts long-run ROI even when realised
W/L wobbles around expectation.

Two data dependencies (additive, no schema changes):
    data/pnl_ledger.csv             - placement-time bets (cycle 8762cd94)
    data/lines/<date>_<book>.csv    - per-minute line snapshots (cycle 8d40558a)

Output (additive enrichment, separate file):
    data/pnl_ledger_clv.csv  - original ledger columns + closing_line, closing_odds,
                               clv_line, clv_odds, clv_percent, beat_close, notes

Public API
----------
find_closing_line(book, game_id, player_id, stat, side, asof) -> (line, odds) | None
compute_clv(bet_row, closing_line, closing_odds)               -> dict
enrich_pnl_with_clv(pnl_path, lines_dir)                       -> pd.DataFrame

Key design choices
------------------
- "Closing" = snapshot whose captured_at is closest to (asof - 30 min) but
  STRICTLY BEFORE `asof`. If the most recent snapshot inside that window
  is older than 24 h, treat as missing.
- Lookup is best-effort: prefer (book, game_id, player_id, stat) but fall
  back to (book, player_name, stat) when ids are blank (the scraper schema
  tolerates blank ids - see cycle 8d40558a notes).
- clv_percent = placement_implied_prob - closing_implied_prob. POSITIVE means
  the bettor beat the close (placed at a longer price than where the market
  closed). Vig-included probs on both sides for like-for-like comparison.
"""
from __future__ import annotations

import csv
import glob
import os
import unicodedata
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_PNL_PATH  = os.path.join(PROJECT_DIR, "data", "pnl_ledger.csv")
DEFAULT_LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")
DEFAULT_OUT_PATH  = os.path.join(PROJECT_DIR, "data", "pnl_ledger_clv.csv")

# How far before tip we treat a snapshot as "closing".
CLOSING_OFFSET_MIN = 30
# Outside this window we don't trust the snapshot to represent the close.
MAX_SNAPSHOT_AGE_HOURS = 24

# Map full book names (used in the lines snapshot files) back to ledger short codes
# and vice versa, so we can match e.g. ledger 'DK' to snapshot 'draftkings'.
_BOOK_ALIASES = {
    "dk":          "draftkings",
    "draftkings":  "draftkings",
    "fd":          "fanduel",
    "fanduel":     "fanduel",
    "mgm":         "betmgm",
    "betmgm":      "betmgm",
    "odds-api":    "odds-api",
    "oddsapi":     "odds-api",
    "pp":          "prizepicks",
    "prizepicks":  "prizepicks",
    "bov":         "bovada",
    "bovada":      "bovada",
    "pin":         "pinnacle",
    "pinnacle":    "pinnacle",
}


def _book_canon(b: str) -> str:
    return _BOOK_ALIASES.get((b or "").lower().strip(), (b or "").lower().strip())


def _name_key(s: str) -> str:
    """Strip accents + lowercase; matches the convention used in compute_clv.py."""
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def _american_to_implied_prob(odds) -> Optional[float]:
    """Vig-included implied probability (0-1). Returns None on bad input."""
    try:
        odds = int(odds)
    except (TypeError, ValueError):
        return None
    if odds == 0:
        return None
    if odds >= 100:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def _parse_iso(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Snapshot loading.                                                           #
# --------------------------------------------------------------------------- #
def _load_snapshots(lines_dir: str) -> List[Dict]:
    """Read every data/lines/*.csv (NOT recursive sub-folders).

    The scraper writes one file per (date, book) - we union them all and
    let `find_closing_line` filter by (book, captured_at) per query.
    Returns rows as-loaded; callers must coerce types.
    """
    if not os.path.isdir(lines_dir):
        return []
    rows: List[Dict] = []
    # Files look like 2026-05-24_dk.csv or 2026-05-24_draftkings.csv.
    for path in sorted(glob.glob(os.path.join(lines_dir, "*.csv"))):
        try:
            with open(path, encoding="utf-8") as fh:
                rows.extend(list(csv.DictReader(fh)))
        except (OSError, csv.Error):
            continue
    return rows


def find_closing_line(
    book: str,
    game_id: str,
    player_id: str,
    stat: str,
    side: str,
    asof: datetime,
    lines_dir: str = DEFAULT_LINES_DIR,
    snapshots: Optional[List[Dict]] = None,
    player_name: str = "",
) -> Optional[Tuple[float, int]]:
    """Return (closing_line, closing_odds_for_side) or None.

    "Closing" = snapshot captured_at closest to (asof - CLOSING_OFFSET_MIN min)
    but strictly < asof. If best candidate is older than MAX_SNAPSHOT_AGE_HOURS,
    return None (stale snapshot, not a real close).

    Match keys (in priority order):
      1) (book, game_id, player_id, stat)  - hard match on ids
      2) (book, player_name, stat)          - fallback when ids are blank

    Side controls which odds column to return (OVER -> over_price, UNDER -> under_price).
    """
    snaps = snapshots if snapshots is not None else _load_snapshots(lines_dir)
    if not snaps:
        return None

    book_c = _book_canon(book)
    stat_l = (stat or "").lower().strip()
    side_u = (side or "").upper().strip()
    pid_s  = str(player_id or "").strip()
    gid_s  = str(game_id or "").strip()
    pname_k = _name_key(player_name)

    target = asof - timedelta(minutes=CLOSING_OFFSET_MIN)
    # Strictly before asof (we never want a snapshot taken AFTER placement-time
    # logic finished; tip-off is the real upper bound when called from enrichment).
    deadline = asof
    max_age = timedelta(hours=MAX_SNAPSHOT_AGE_HOURS)

    best: Optional[Tuple[float, Dict]] = None  # (abs-distance-to-target-seconds, row)
    best_tier = 99
    for r in snaps:
        # Book match.
        if _book_canon(r.get("book", "")) != book_c:
            continue
        # Stat match.
        if (r.get("stat", "") or "").lower().strip() != stat_l:
            continue

        # Tier 1: id-based; Tier 2: name-based fallback.
        tier = 99
        rgid = str(r.get("game_id", "") or "").strip()
        rpid = str(r.get("player_id", "") or "").strip()
        if pid_s and rpid and rpid == pid_s and (not gid_s or not rgid or rgid == gid_s):
            tier = 1
        elif pname_k and _name_key(r.get("player_name", "")) == pname_k:
            tier = 2
        else:
            continue

        ts = _parse_iso(r.get("captured_at", ""))
        if ts is None or ts >= deadline:
            continue
        # Reject snapshots that are absurdly old vs the bet.
        if (deadline - ts) > max_age:
            continue

        dist = abs((ts - target).total_seconds())
        # Prefer the higher-confidence tier even at slightly worse time distance.
        if tier < best_tier or (tier == best_tier and (best is None or dist < best[0])):
            best = (dist, r)
            best_tier = tier

    if best is None:
        return None

    row = best[1]
    try:
        cline = float(row.get("line", "nan"))
    except (TypeError, ValueError):
        return None

    odds_field = "over_price" if side_u == "OVER" else "under_price"
    raw_odds = row.get(odds_field, "")
    try:
        codds = int(raw_odds)
    except (TypeError, ValueError):
        return None
    return (cline, codds)


# --------------------------------------------------------------------------- #
# CLV math.                                                                   #
# --------------------------------------------------------------------------- #
def compute_clv(
    bet_row: Dict,
    closing_line: Optional[float],
    closing_odds: Optional[int],
) -> Dict:
    """Score one bet vs its closing snapshot.

    Returns
    -------
    dict with keys:
        clv_line     - signed line movement in stat units (positive = beat close)
        clv_odds     - signed odds movement in American units (positive = beat close)
        clv_percent  - placement_implied_prob - closing_implied_prob  (positive = beat close)
        beat_close   - bool
        notes        - human-readable explanation of any partial / null reasons
    """
    notes_parts: List[str] = []
    side = (bet_row.get("side", "") or "").upper()
    out = {
        "clv_line":    None,
        "clv_odds":    None,
        "clv_percent": None,
        "beat_close":  None,
        "notes":       "",
    }

    try:
        placed_line = float(bet_row.get("line", "nan"))
    except (TypeError, ValueError):
        placed_line = None
    try:
        placed_odds = int(bet_row.get("american_odds", 0) or 0)
    except (TypeError, ValueError):
        placed_odds = None

    if closing_line is None or closing_odds is None:
        out["notes"] = "no closing snapshot"
        return out
    if placed_line is None or placed_odds is None:
        out["notes"] = "bad bet placement fields"
        return out
    if side not in ("OVER", "UNDER"):
        out["notes"] = f"unknown side {side!r}"
        return out

    # Line movement / CLV sign.
    # CORRECT semantics (CV_CLV_LINE_SIGN_FIX=1): CLV is positive when you got a
    # BETTER NUMBER than the close. For an OVER bet a LOWER number is better, so
    # you beat the close when the line CLOSED HIGHER than you placed:
    #   OVER  -> clv_line = closing_line - placed_line   (close 24.5 vs placed 22.5 = +2.0)
    # For an UNDER bet a HIGHER number is better, so you beat the close when it
    # CLOSED LOWER than you placed:
    #   UNDER -> clv_line = placed_line - closing_line   (placed 22.5 vs close 20.5 = +2.0)
    # This matches the verified reference betting_portfolio.record_clv and the
    # nightly price-based clv_tracker. The LEGACY default (flag OFF) had BOTH
    # signs inverted (a confirmed reporting bug, GRADING_SETTLE_CLV_AUDIT.md B-1:
    # it reported beat_close for BOTH favorable AND unfavorable line moves). Gated
    # default-OFF = byte-identical to the legacy reports until the owner flips it
    # (the price-based clv_percent below was always correct, so daily CLV bps are
    # unaffected; only clv_line/beat_close in the manual/weekly reports change).
    _clv_sign_fix = (os.environ.get("CV_CLV_LINE_SIGN_FIX", "").strip().lower()
                     not in ("", "0", "false", "no", "off"))
    if side == "OVER":
        clv_line = round((closing_line - placed_line) if _clv_sign_fix
                         else (placed_line - closing_line), 4)
    else:
        clv_line = round((placed_line - closing_line) if _clv_sign_fix
                         else (closing_line - placed_line), 4)

    # Odds movement. Positive American-odds CLV means closing odds are SHORTER
    # than what you placed at (you got the longer price).
    placed_prob  = _american_to_implied_prob(placed_odds)
    closing_prob = _american_to_implied_prob(closing_odds)
    if placed_prob is None or closing_prob is None:
        notes_parts.append("bad odds for implied-prob")
        clv_pct = None
    else:
        # closing - placed: positive when close implies MORE probability than
        # placement, i.e. shorter price now, i.e. you locked in the longer price.
        clv_pct = round(closing_prob - placed_prob, 6)

    # Cosmetic American-odds delta (always reported even if implied-prob math failed).
    clv_odds = closing_odds - placed_odds

    beat = (clv_line > 0) or (clv_pct is not None and clv_pct > 0)
    out.update({
        "clv_line":    clv_line,
        "clv_odds":    clv_odds,
        "clv_percent": clv_pct,
        "beat_close":  bool(beat),
        "notes":       ";".join(notes_parts),
    })
    return out


# --------------------------------------------------------------------------- #
# Ledger enrichment.                                                          #
# --------------------------------------------------------------------------- #
def _load_ledger(pnl_path: str) -> List[Dict]:
    if not os.path.exists(pnl_path):
        return []
    with open(pnl_path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _placed_at(bet_row: Dict) -> Optional[datetime]:
    return _parse_iso(bet_row.get("placed_at", ""))


def _asof_for_bet(bet_row: Dict) -> datetime:
    """Approximate tip-off as `placed_at + 30 min` for the lookup window.

    We don't have a true tip timestamp on the ledger row. The scraper writes
    snapshots all day, so anchoring to placed_at means "find the snapshot
    captured between placement and ~placement-time" - which is the right
    semantic for a bet placed shortly before tip. If a bettor places hours
    early, the lookup naturally returns None (no snapshot in window).
    """
    p = _placed_at(bet_row)
    if p is None:
        return datetime.now()
    return p + timedelta(minutes=30)


def enrich_pnl_with_clv(
    pnl_path: str = DEFAULT_PNL_PATH,
    lines_dir: str = DEFAULT_LINES_DIR,
    out_path: Optional[str] = None,
) -> List[Dict]:
    """Join ledger with closing-line snapshots; write enriched CSV.

    Returns enriched rows (list of dicts) so callers can post-process without
    re-reading. Gracefully empty when either file is missing.
    """
    out_path = out_path or DEFAULT_OUT_PATH
    bets = _load_ledger(pnl_path)
    if not bets:
        # Still write a header-only file so downstream callers don't crash.
        _write_enriched(out_path, [])
        return []

    snaps = _load_snapshots(lines_dir)
    enriched: List[Dict] = []
    for b in bets:
        asof = _asof_for_bet(b)
        clos = find_closing_line(
            book=b.get("book", ""),
            game_id=b.get("game_id", ""),
            player_id=b.get("player_id", ""),
            stat=b.get("stat", ""),
            side=b.get("side", ""),
            asof=asof,
            snapshots=snaps,
            player_name=b.get("player", ""),
        )
        if clos is None:
            scored = compute_clv(b, None, None)
            cline_field, codds_field = "", ""
        else:
            cline, codds = clos
            scored = compute_clv(b, cline, codds)
            cline_field, codds_field = f"{cline:g}", str(codds)

        row = dict(b)
        row["closing_line"] = cline_field
        row["closing_odds"] = codds_field
        for k in ("clv_line", "clv_odds", "clv_percent", "beat_close", "notes"):
            v = scored.get(k)
            row[k] = "" if v is None else (
                f"{v:.6f}" if isinstance(v, float) else str(v)
            )
        enriched.append(row)

    _write_enriched(out_path, enriched)
    return enriched


def _write_enriched(path: str, rows: List[Dict]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    base_cols = [
        "bet_id", "placed_at", "game_id", "player_id", "player", "team",
        "stat", "line", "side", "book", "american_odds", "stake",
        "model_pred", "model_prob", "model_edge", "kelly_pct",
        "status", "settled_at", "actual_stat", "profit_loss", "bankroll_after",
    ]
    clv_cols = ["closing_line", "closing_odds", "clv_line", "clv_odds",
                "clv_percent", "beat_close", "notes"]
    fields = base_cols + clv_cols
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


# --------------------------------------------------------------------------- #
# Aggregation helpers used by scripts/clv_report.py.                          #
# --------------------------------------------------------------------------- #
def _safe_float(s) -> Optional[float]:
    try:
        v = float(s)
        return v
    except (TypeError, ValueError):
        return None


def aggregate_clv(rows: List[Dict], by: str = "combined") -> Dict:
    """Compute summary stats over enriched rows.

    by:
        "combined" - one overall dict
        "stat" | "book" | "side" - dict of {group_key: subdict}
    """
    def _summarise(grp: List[Dict]) -> Dict:
        n = len(grp)
        with_close = [r for r in grp if r.get("closing_line", "") != ""]
        n_w = len(with_close)
        pcts = [
            _safe_float(r.get("clv_percent"))
            for r in with_close
            if _safe_float(r.get("clv_percent")) is not None
        ]
        beats = sum(1 for r in with_close if str(r.get("beat_close", "")).lower() == "true")
        mean_pct = (sum(pcts) / len(pcts)) if pcts else 0.0

        # Pearson correlation: clv_percent vs realised roi (per-bet).
        pairs = []
        for r in with_close:
            p = _safe_float(r.get("clv_percent"))
            stake = _safe_float(r.get("stake")) or 0.0
            pnl = _safe_float(r.get("profit_loss"))
            if p is None or pnl is None or stake <= 0:
                continue
            pairs.append((p, pnl / stake))
        corr = _pearson(pairs) if len(pairs) >= 2 else None

        return {
            "n":               n,
            "n_with_close":    n_w,
            "missing_close":   n - n_w,
            "mean_clv_percent": mean_pct,
            "beat_close_rate": (beats / n_w) if n_w else 0.0,
            "clv_vs_roi_corr": corr,
        }

    if by == "combined":
        return _summarise(rows)

    field_map = {"stat": "stat", "book": "book", "side": "side"}
    if by not in field_map:
        raise ValueError(f"by must be combined|stat|book|side, got {by!r}")
    field = field_map[by]
    groups: Dict[str, List[Dict]] = {}
    for r in rows:
        k = (r.get(field, "") or "").lower() or "(none)"
        groups.setdefault(k, []).append(r)
    return {k: _summarise(g) for k, g in sorted(groups.items())}


def _pearson(pairs: List[Tuple[float, float]]) -> Optional[float]:
    n = len(pairs)
    if n < 2:
        return None
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    num = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    dx2 = sum((p[0] - mx) ** 2 for p in pairs)
    dy2 = sum((p[1] - my) ** 2 for p in pairs)
    if dx2 <= 0 or dy2 <= 0:
        return None
    return round(num / ((dx2 * dy2) ** 0.5), 4)

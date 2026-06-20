"""scripts.platformkit.improve.settled_ingest -- honest settled-game DATA-IN for the
self-improve loop (SI-P0-02 + A2). Reconstructs the newly-SETTLED games to fold, driven by a
per-(sport, corpus) id/date HIGH-WATER MARK that NEVER skips and NEVER double-counts, and --
the honesty crux -- distinguishes a DEAD feed from a genuinely-empty offseason.

`settled_finals.settled_since` returns `[]` for BOTH a dead/blocked feed AND an honestly-idle
offseason -- the two read identically, and a dead feed that reads green is the central honesty
violation. So this module fetches each date board itself (network injected via http_get) and
CLASSIFIES the fetch:
  * STALE     -- board FAILED to fetch/parse (exception, non-dict, no `events` list). Feed is
                 DEAD: FREEZE the watermark clock + status=DEGRADED. Never reads green.
  * IDLE      -- boards parsed OK but yielded zero NEW unseen finals (offseason / all-folded),
                 OR new finals with no wired states yet. Clock MAY advance; NOT degraded;
                 NOT a fabricated game.
  * FRESH_NEW -- a board parsed OK and surfaced >=1 clean foldable unseen final.

NEVER-SKIP / NEVER-DOUBLE-COUNT: dedup by game_id against the UNION of the caller's seen_ids
and the loop checkpoint's seen_ids (PRIMARY guard, never a key filter -- an out-of-order late
final is surfaced). A season-aware MULTI-DAY window means a late/next-day final never rolls off
a single-day board; overlapping windows dedup by id for free. The high-water key advances
forward-only (display/order only). Must call settle_audit on what it returns (MF3 anti-0-fill);
an audit-degraded batch downgrades to DEGRADED rather than 0-fill a missing outcome.

Returns a structured IngestSummary (counts + status + clean games + advanced cursor). No
$/pnl/roi/edge anywhere -- feeds a CALIBRATION gate; vs_close UNPROVEN. Never edits MEMORY.md,
never writes data/registry/, never flips a flag, never creates the PIPELINE_ENABLED sentinel.
NEVER raises. Stdlib + repo-internal; ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from scripts.platformkit.improve.cursor_util import SEEN_CAP, game_id as _gid, key as _key
from scripts.platformkit.improve.settle_audit import audit_settled, AuditSummary

logger = logging.getLogger("settled_ingest")

# Status strings (stable; consumed by the daemon/status sidecar).
STALE = "STALE"            # feed dead -> clock FROZEN, DEGRADED
IDLE = "IDLE"             # parsed OK, nothing new -> clock may advance, honest-idle
FRESH_NEW = "FRESH_NEW"   # >=1 unseen final surfaced
DEGRADED = "DEGRADED"     # STALE feed OR audit-degraded batch -> never green

# Multi-day backfill window (yesterday+today) so a late/next-day final never rolls off the
# single-day board. Per-sport in-season MONTHS decide ONLY whether an empty IDLE is EXPECTED
# (offseason) -- never to drop or fabricate a game; out-of-season finals are honored anyway.
DEFAULT_WINDOW_DAYS = 2
_IN_SEASON_MONTHS: Dict[str, frozenset] = {
    "nba": frozenset({10, 11, 12, 1, 2, 3, 4, 5, 6}),
    "mlb": frozenset({3, 4, 5, 6, 7, 8, 9, 10, 11}),
    "soccer": frozenset({8, 9, 10, 11, 12, 1, 2, 3, 4, 5}),
    "soccer_intl": frozenset(range(1, 13)),
    "tennis": frozenset(range(1, 13)),
}


@dataclass
class IngestSummary:
    """Structured result of one settled-ingest pass (counts only -- NO $/ROI)."""

    sport: str = ""
    corpus: str = "settled_finals"
    status: str = IDLE
    degraded: bool = False
    in_season: bool = True
    clean_games: List[Dict[str, Any]] = field(default_factory=list)
    n_fetched_final: int = 0      # finals seen across parsed boards (pre-dedup)
    n_new_unseen: int = 0         # finals not in the seen-id union
    n_clean: int = 0             # passed the MF3 audit
    n_quarantined: int = 0
    quarantine_reasons: List[str] = field(default_factory=list)
    n_boards: int = 0
    n_boards_ok: int = 0          # boards that fetched+parsed cleanly
    high_water: str = ""         # advanced display/order key (forward-only)
    folded_ids: List[str] = field(default_factory=list)  # ids to record as seen
    clock_advances: bool = False  # may caller advance last_fetch_ok_ts?
    note: str = "calibration, not edge; vs_close UNPROVEN; idle != degraded"

    def to_dict(self) -> Dict[str, Any]:
        """Counts/status only -- the foldable games are deliberately NOT serialized here."""
        d = {k: v for k, v in asdict(self).items() if k != "clean_games"}
        d["quarantine_reasons"] = list(self.quarantine_reasons)
        return d


def _in_season(sport: str, when: datetime) -> bool:
    months = _IN_SEASON_MONTHS.get(str(sport).lower())
    if not months:
        return True  # unknown sport: assume in-season so we never wrongly excuse a gap
    return when.month in months


def date_window(*, days: int = DEFAULT_WINDOW_DAYS,
                now: Optional[datetime] = None) -> List[str]:
    """Season-aware MULTI-DAY ESPN `dates=` window (YYYYMMDD), oldest first.

    Returns `days` consecutive calendar days ending today (UTC) so a late/next-day final
    never rolls off a single-day board. Overlapping windows across cycles dedup by game_id
    for free, so the window is safe to widen. Never raises.
    """
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    n = max(1, int(days))
    out = [(ref - timedelta(days=d)).strftime("%Y%m%d") for d in range(n)]
    out.reverse()  # oldest first (display/order friendliness)
    return out


def _parse_board_finals(board: Any, sport: str) -> Optional[List[Dict[str, Any]]]:
    """Parse ONE board into its final-game dicts, or None when the board is UNPARSEABLE.

    None signals a STALE fetch (exception upstream, non-dict body, or no `events` list) --
    the caller FREEZES the clock for it. An empty list signals a parsed-OK board with zero
    finals (contributes to IDLE, clock may advance). Never raises.
    """
    if not isinstance(board, dict):
        return None
    if not isinstance(board.get("events"), list):
        return None  # malformed/empty body -- treat as dead, not idle
    try:
        from scripts.platformkit.ingame import settled_finals as _sf
        return list(_sf._final_games_from_board(board, str(sport).lower()))
    except Exception as exc:  # noqa: BLE001 -- a parse blow-up is STALE, never a crash
        logger.debug("_parse_board_finals(%s) failed: %s", sport, exc)
        return None


def ingest_settled(sport: str, *,
                   seen_ids: Optional[Sequence[str]] = None,
                   checkpoint_seen_ids: Optional[Sequence[str]] = None,
                   high_water: str = "",
                   http_get: Optional[Callable[[str], Any]] = None,
                   states_for_game: Optional[Callable[..., Sequence[Dict[str, Any]]]] = None,
                   dates: Optional[Sequence[str]] = None,
                   window_days: int = DEFAULT_WINDOW_DAYS,
                   now: Optional[datetime] = None,
                   degrade_fraction: float = 0.5) -> IngestSummary:
    """Reconstruct the newly-SETTLED games to fold for `sport`. NEVER raises.

    Per-(sport,corpus) id/date HIGH-WATER MARK: dedup by game_id against the UNION of
    `seen_ids` and `checkpoint_seen_ids` (PRIMARY guard, monotonic -- two runs never
    double-count); season-aware multi-day window so nothing rolls off unseen; CLASSIFIES the
    fetch STALE/IDLE/FRESH_NEW so a dead feed surfaces DEGRADED not green; runs settle_audit
    (MF3 anti-0-fill) and returns ONLY clean games for folding."""
    sp = str(sport).lower()
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    in_season = _in_season(sp, ref)
    summary = IngestSummary(sport=sp, in_season=in_season, high_water=str(high_water or ""))

    # Resolve the network getter (injected for tests; real keyless ESPN otherwise).
    if http_get is None:
        try:
            from scripts.platformkit.ingame.settled_finals import _default_http_get
            http_get = _default_http_get
        except Exception:  # noqa: BLE001 -- provider gone -> dead feed
            http_get = None

    win = list(dates) if dates else date_window(days=window_days, now=ref)
    seen = set(str(s) for s in (seen_ids or ()))
    seen |= set(str(s) for s in (checkpoint_seen_ids or ()))  # UNION -- gap-2 fix

    # --- fetch + classify each board; STALE (unparseable) freezes the clock -----------
    finals: Dict[str, Dict[str, Any]] = {}
    n_boards = 0
    n_boards_ok = 0
    try:
        from scripts.platformkit.ingame.settled_finals import _LEAGUE_PATH
        path = _LEAGUE_PATH.get(sp)
    except Exception:  # noqa: BLE001
        path = None
    if path and http_get is not None:
        site = "https://site.api.espn.com/apis/site/v2/sports"
        for d in win:
            n_boards += 1
            url = "%s/%s/scoreboard?dates=%s" % (site, path, d)
            try:
                board = http_get(url)
            except Exception as exc:  # noqa: BLE001 -- one dead board: STALE for it
                logger.debug("ingest_settled(%s) board %s fetch failed: %s", sp, d, exc)
                board = None
            parsed = _parse_board_finals(board, sp) if board is not None else None
            if parsed is None:
                continue  # STALE board -- does NOT count toward an OK observation
            n_boards_ok += 1
            for g in parsed:
                finals[g["game_id"]] = g  # dedup within the window by id

    summary.n_boards = n_boards
    summary.n_boards_ok = n_boards_ok
    summary.n_fetched_final = len(finals)

    # A board count > 0 with ZERO boards parsing OK == a DEAD feed. Freeze the clock.
    feed_dead = n_boards > 0 and n_boards_ok == 0
    if feed_dead:
        summary.status = STALE
        summary.degraded = True
        summary.clock_advances = False  # FREEZE: never let a dead feed read green
        return summary

    # --- never-skip / never-double-count dedup against the seen-id UNION --------------
    fresh = [g for g in finals.values() if str(g["game_id"]) not in seen]
    fresh.sort(key=lambda g: _key(g))
    summary.n_new_unseen = len(fresh)

    # advance the display/order high-water forward-only across EVERY parsed final (so the
    # cursor reflects what we observed), but folding is decided by id dedup, never this key.
    batch_keys = [_key(g) for g in finals.values()]
    summary.high_water = max([summary.high_water] + batch_keys) if batch_keys else summary.high_water

    if not fresh:
        # Parsed OK, nothing new: honest IDLE (offseason or all-already-folded). The clock
        # MAY advance -- we successfully verified there is nothing new. NOT degraded.
        summary.status = IDLE
        summary.clock_advances = True
        return summary

    # --- enrich each new final into frozen-schema state rows (reconstruct for folding) --
    # A raw ESPN final carries NO states/outcome; the sport's ingest adapter reconstructs
    # them. If NO adapter is wired yet, enrichment yields zero states for every game -- that
    # is a WIRING gap (honest IDLE), NOT a dead feed (STALE) and NOT a fabricated row.
    enriched = _enrich(sp, fresh, states_for_game)
    any_states = any(g.get("states") for g in enriched)
    if not any_states:
        summary.status = IDLE  # feed alive + new finals, but no states to fold yet (wiring)
        summary.clock_advances = True
        return summary

    # --- MF3 settle_audit: NEVER 0-fill a missing outcome into a neutral observation ---
    audit: AuditSummary = audit_settled(enriched, degrade_fraction=degrade_fraction,
                                        raise_on_degraded=False)
    summary.n_quarantined = audit.n_quarantined
    summary.quarantine_reasons = [r for _, r in audit.quarantined]

    if audit.degraded:
        # A batch that HAD states but is mostly unfoldable (the ingest attached no real
        # labels) -- 0-fill territory. DEGRADED: surface zero clean games, FREEZE the clock.
        summary.status = DEGRADED
        summary.degraded = True
        summary.clock_advances = False
        return summary

    clean = list(audit.clean_games)
    summary.clean_games = clean
    summary.n_clean = len(clean)
    summary.folded_ids = [_gid(g) for g in clean][-SEEN_CAP:]
    summary.status = FRESH_NEW if clean else IDLE
    summary.clock_advances = True
    return summary


def _enrich(sport: str, games: Sequence[Dict[str, Any]],
            states_for_game: Optional[Callable[..., Sequence[Dict[str, Any]]]]
            ) -> List[Dict[str, Any]]:
    """Attach reconstructed in-game state rows to each final via the sport's adapter (injected
    `states_for_game` else settled_finals.states_for_game; absent -> []). A game whose
    enrichment yields no states keeps `states=[]`, later audited as empty-states -- NEVER
    fabricated. NEVER raises."""
    getter = states_for_game
    if getter is None:
        try:
            from scripts.platformkit.ingame.settled_finals import states_for_game as getter
        except Exception:  # noqa: BLE001 -- no adapter -> zero states everywhere
            getter = None
    out: List[Dict[str, Any]] = []
    for g in games:
        rows: List[Dict[str, Any]] = []
        if getter is not None:
            try:
                rows = [r for r in getter(sport, g) if isinstance(r, dict)]
            except Exception as exc:  # noqa: BLE001 -- bad adapter: skip states, never crash
                logger.debug("_enrich(%s) states failed for %s: %s", sport, g.get("game_id"), exc)
                rows = []
        ng = dict(g)
        ng["states"] = rows
        out.append(ng)
    return out


def settled_games_fn(name: str, *, since: str = "",
                     seen_ids: Optional[Sequence[str]] = None,
                     **kw: Any) -> List[Dict[str, Any]]:
    """Daemon-shaped adapter matching selfimprove_daemon's settled_games_fn(name, since=,
    seen_ids=): returns ONLY the clean foldable games (the richer status/degraded verdict is
    on ingest_settled()'s IngestSummary). Dead feed / degraded batch / offseason -> []. NEVER
    raises."""
    try:
        s = ingest_settled(name, seen_ids=seen_ids, high_water=str(since or ""), **kw)
        return list(s.clean_games)
    except Exception as exc:  # noqa: BLE001 -- purity: any failure -> empty (NO_CANDIDATE)
        logger.debug("settled_games_fn(%s) failed: %s", name, exc)
        return []

__all__ = ["IngestSummary", "ingest_settled", "settled_games_fn", "date_window",
           "STALE", "IDLE", "FRESH_NEW", "DEGRADED", "DEFAULT_WINDOW_DAYS"]

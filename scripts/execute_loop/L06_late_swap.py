"""L06_late_swap.py — Late-Swap Watcher (BUILD L6).

Polls L20 injury feed for new OUT/DOUBTFUL updates within the slate lock window,
finds affected lineups, estimates EV swing, and recommends replacement candidates.

Public API
----------
    SwapAction              frozen dataclass
    SwapSignal              frozen dataclass
    watch_for_swaps(slate, current_lineups, current_bets, poll_seconds) -> Iterator[SwapSignal]
    compute_swap_impact(slate, lineup, news, fpts_data)                 -> SwapSignal | None
    recommend_swap_actions(signal)                                       -> list[SwapAction]

CLI
---
    python L06_late_swap.py --help
"""
from __future__ import annotations

import logging
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set

# ── paths ─────────────────────────────────────────────────────────────────────
_SCRIPT_DIR  = Path(__file__).resolve().parent
_PROJECT_DIR = _SCRIPT_DIR.parents[1]
sys.path.insert(0, str(_PROJECT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR))

log = logging.getLogger(__name__)

# ── soft imports ─────────────────────────────────────────────────────────────
try:
    from scripts.execute_loop.L01_slate_ingester import SlateContest
except ImportError:
    try:
        from L01_slate_ingester import SlateContest  # type: ignore[no-redef]
    except ImportError:
        SlateContest = None  # type: ignore[assignment,misc]

try:
    from scripts.execute_loop.L02_fpts_distribution import FPTSDistribution
except ImportError:
    try:
        from L02_fpts_distribution import FPTSDistribution  # type: ignore[no-redef]
    except ImportError:
        FPTSDistribution = None  # type: ignore[assignment,misc]

try:
    from scripts.execute_loop.L20_injury_feed import (
        InjuryUpdate,
        diff_against_seen,
        run_all_sources,
    )
except ImportError:
    from L20_injury_feed import (  # type: ignore[no-redef]
        InjuryUpdate,
        diff_against_seen,
        run_all_sources,
    )

try:
    from scripts.execute_loop.L22_alerting import send_alert as _send_alert
except ImportError:
    try:
        from L22_alerting import send_alert as _send_alert  # type: ignore[no-redef]
    except ImportError:
        log.warning("[L06] L22_alerting not found — alerts disabled")
        _send_alert = None  # type: ignore[assignment]

# ── constants ─────────────────────────────────────────────────────────────────
_TRIGGER_STATUSES: Set[str] = {"OUT", "DOUBTFUL"}
_WINDOW_MINUTES   = 30          # minutes past lock_time still considered relevant
_EV_SWING_THRESH  = 5.0         # pp  — minimum swing to emit a signal
_OUT_WIN_PROB     = 0.05        # assumed P(OVER) for an OUT player (zero minutes)
_DOUBTFUL_WIN_PROB = 0.15       # assumed P(OVER) for a DOUBTFUL player


# ── dataclasses ───────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SwapAction:
    lineup_id: str
    drop_player: str
    add_player: str
    salary_delta: int          # positive = cheaper replacement (saves cap)
    projected_fpts_delta: float  # expected FPTS gain (add - drop)


@dataclass(frozen=True)
class SwapSignal:
    trigger_player: str
    trigger_status: str                  # "OUT" | "DOUBTFUL"
    affected_lineups: List[str]
    affected_props: List[str]
    recommended_actions: List[SwapAction]
    ev_swing_pp: float                   # absolute pp swing on best affected bet
    timestamp: datetime


# ── name normalisation (mirrors L20) ─────────────────────────────────────────
def _normalize_name(s: str) -> str:
    return (
        unicodedata.normalize("NFKD", s)
        .encode("ascii", "ignore")
        .decode()
        .lower()
        .strip()
    )


def _names_match(a: str, b: str) -> bool:
    return _normalize_name(a) == _normalize_name(b)


# ── slate lock helpers ────────────────────────────────────────────────────────
def _parse_iso(ts: str) -> Optional[datetime]:
    """Parse an ISO-8601 string to an aware datetime. Returns None on failure."""
    import re
    if not ts:
        return None
    s = re.sub(r"(\.\d{6})\d+([\+\-Z])", r"\1\2", ts.replace("Z", "+00:00"))
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _within_window(slate, now: Optional[datetime] = None) -> bool:
    """Return True if *now* is before lock_time + WINDOW_MINUTES.

    Returns False (with a WARN log) when we are past the window.
    """
    now = now or _now_utc()
    lock_str = getattr(slate, "lock_time", "") or ""
    lock_dt  = _parse_iso(lock_str)
    if lock_dt is None:
        log.warning("[L06] Cannot parse lock_time %r — treating as within window", lock_str)
        return True
    deadline = lock_dt + timedelta(minutes=_WINDOW_MINUTES)
    if now > deadline:
        log.warning(
            "[L06] now=%s is past lock_time + %dmin window (%s) — skipping news",
            now.isoformat(timespec="seconds"),
            _WINDOW_MINUTES,
            deadline.isoformat(timespec="seconds"),
        )
        return False
    return True


# ── lineup / bet helpers ──────────────────────────────────────────────────────
def _lineups_containing(player_name: str, lineups: List[dict]) -> List[dict]:
    """Return all lineup dicts whose 'players' list contains player_name."""
    norm = _normalize_name(player_name)
    return [
        lu for lu in lineups
        if any(_normalize_name(p) == norm for p in lu.get("players", []))
    ]


def _bets_for_player(player_name: str, bets: List[dict]) -> List[dict]:
    """Return all bet dicts for the given player."""
    norm = _normalize_name(player_name)
    return [b for b in bets if _normalize_name(b.get("player", "")) == norm]


def _compute_ev_swing(news: InjuryUpdate, bets: List[dict]) -> float:
    """Compute ev_swing_pp = max(|p_new - p_old|) * 100 across affected bets.

    For an OUT player p_new ≈ 0.05 (nearly zero minutes).
    For a DOUBTFUL player p_new ≈ 0.15.
    Falls back to 0.0 when bets is empty.
    """
    if not bets:
        return 0.0
    p_new = _OUT_WIN_PROB if news.status == "OUT" else _DOUBTFUL_WIN_PROB
    swings = [abs(p_new - float(b.get("model_p_side", 0.5))) * 100 for b in bets]
    return max(swings) if swings else 0.0


# ── replacement candidate finder ─────────────────────────────────────────────
def _player_position(player_name: str, slate) -> Optional[str]:
    """Look up player's position in slate.players list."""
    norm = _normalize_name(player_name)
    for p in getattr(slate, "players", []):
        if _normalize_name(p.get("name", "")) == norm:
            return p.get("position")
    return None


def _player_salary(player_name: str, slate) -> int:
    """Look up player's salary in slate.players list. Returns 0 if not found."""
    norm = _normalize_name(player_name)
    for p in getattr(slate, "players", []):
        if _normalize_name(p.get("name", "")) == norm:
            return int(p.get("salary", 0))
    return 0


def _find_replacements(
    slate,
    lineup: dict,
    drop_player: str,
    fpts_data: Dict[str, float],
    max_candidates: int = 5,
) -> List[dict]:
    """Return top replacement candidates: same position, salary fits, rank by proj_fpts/salary.

    Each candidate: {"name": str, "salary": int, "proj_fpts": float, "position": str}
    """
    drop_salary  = _player_salary(drop_player, slate)
    drop_pos     = _player_position(drop_player, slate)
    total_salary = int(lineup.get("total_salary", 0))
    salary_cap   = int(lineup.get("salary_cap", getattr(slate, "salary_cap", 50_000)))
    cap_remaining = salary_cap - total_salary + drop_salary  # budget after removing drop

    rostered_norms = {_normalize_name(p) for p in lineup.get("players", [])}
    drop_norm      = _normalize_name(drop_player)

    candidates = []
    for p in getattr(slate, "players", []):
        p_norm = _normalize_name(p.get("name", ""))
        if p_norm == drop_norm:
            continue  # skip the player being dropped
        if p_norm in rostered_norms:
            continue  # already in lineup
        if drop_pos and p.get("position") != drop_pos:
            continue  # position mismatch
        p_salary = int(p.get("salary", 0))
        if p_salary > cap_remaining:
            continue  # too expensive
        proj_fpts = fpts_data.get(p.get("name", ""), fpts_data.get(p_norm, 0.0))
        efficiency = proj_fpts / p_salary if p_salary > 0 else 0.0
        candidates.append({
            "name":       p.get("name", ""),
            "salary":     p_salary,
            "proj_fpts":  proj_fpts,
            "position":   p.get("position", ""),
            "efficiency": efficiency,
        })

    candidates.sort(key=lambda x: x["efficiency"], reverse=True)
    return candidates[:max_candidates]


# ── core unit-testable function ───────────────────────────────────────────────
def compute_swap_impact(
    slate,
    lineup: dict,
    news: InjuryUpdate,
    fpts_data: Dict[str, float],
    current_bets: Optional[List[dict]] = None,
) -> Optional[SwapSignal]:
    """Compute swap signal for a single (lineup, injury-news) pair.

    Returns SwapSignal if ev_swing_pp > EV_SWING_THRESH or FPTS delta > 5pp equiv,
    otherwise None.

    Parameters
    ----------
    slate        : SlateContest-like with .players, .salary_cap, .lock_time
    lineup       : {"lineup_id": str, "players": list[str], "total_salary": int,
                    "salary_cap": int}
    news         : InjuryUpdate (status in {OUT, DOUBTFUL})
    fpts_data    : {player_name: projected_fpts}
    current_bets : all active bets (used for EV swing calc; may be empty)
    """
    if current_bets is None:
        current_bets = []

    drop_player  = news.player
    affected_bets = _bets_for_player(drop_player, current_bets)
    ev_swing_pp   = _compute_ev_swing(news, affected_bets)

    # Compute FPTS-based swing as a fallback gate when bets is empty
    drop_proj_fpts = fpts_data.get(drop_player, fpts_data.get(_normalize_name(drop_player), 0.0))
    p_new          = _OUT_WIN_PROB if news.status == "OUT" else _DOUBTFUL_WIN_PROB
    fpts_swing_equiv = drop_proj_fpts * (1.0 - p_new)  # expected FPTS lost

    # Emit signal if bet EV swing is significant OR FPTS impact is large enough
    if ev_swing_pp <= _EV_SWING_THRESH and fpts_swing_equiv <= _EV_SWING_THRESH:
        return None

    # Use the larger of the two metrics as the canonical ev_swing_pp
    effective_swing = max(ev_swing_pp, fpts_swing_equiv)

    lineup_id    = lineup.get("lineup_id", "unknown")
    affected_prop_ids = [b.get("bet_id", "") for b in affected_bets]

    replacements  = _find_replacements(slate, lineup, drop_player, fpts_data)
    drop_salary   = _player_salary(drop_player, slate)
    drop_proj     = drop_proj_fpts

    actions: List[SwapAction] = []
    for cand in replacements:
        actions.append(SwapAction(
            lineup_id=lineup_id,
            drop_player=drop_player,
            add_player=cand["name"],
            salary_delta=drop_salary - cand["salary"],   # positive = cheaper add
            projected_fpts_delta=cand["proj_fpts"] - drop_proj,
        ))

    return SwapSignal(
        trigger_player=drop_player,
        trigger_status=news.status,
        affected_lineups=[lineup_id],
        affected_props=affected_prop_ids,
        recommended_actions=actions,
        ev_swing_pp=round(effective_swing, 2),
        timestamp=_now_utc(),
    )


# ── recommend_swap_actions ────────────────────────────────────────────────────
def recommend_swap_actions(signal: SwapSignal) -> List[SwapAction]:
    """Return the recommended SwapActions from a signal, sorted by FPTS delta desc.

    This is a thin convenience wrapper — the actions are already computed inside
    compute_swap_impact; this re-sorts and validates them.
    """
    valid = [
        a for a in signal.recommended_actions
        if a.add_player and a.drop_player and a.add_player != a.drop_player
    ]
    return sorted(valid, key=lambda a: a.projected_fpts_delta, reverse=True)


# ── main generator ────────────────────────────────────────────────────────────
def watch_for_swaps(
    slate,
    current_lineups: List[dict],
    current_bets: List[dict],
    poll_seconds: int = 60,
    fpts_data: Optional[Dict[str, float]] = None,
    _now_fn=None,          # injectable for testing
) -> Iterator[SwapSignal]:
    """Poll L20 every poll_seconds; yield SwapSignal for each actionable injury.

    SAFETY: Never mutates current_lineups or current_bets.

    Parameters
    ----------
    slate            : SlateContest-like object
    current_lineups  : list of lineup dicts (read-only)
    current_bets     : list of bet dicts (read-only)
    poll_seconds     : seconds between L20 polls (default 60)
    fpts_data        : {player_name: float} projected FPTS (optional; 0.0 fallback)
    _now_fn          : callable() -> datetime, used for test injection
    """
    if fpts_data is None:
        fpts_data = {}
    now_fn = _now_fn or _now_utc
    seen_signals: Set[str] = set()   # "player|status" dedupe key

    log.info(
        "[L06] Starting late-swap watcher — poll=%ds, %d lineups, %d bets",
        poll_seconds, len(current_lineups), len(current_bets),
    )

    while True:
        now = now_fn()

        # Guard: skip if we are past the lock window
        if not _within_window(slate, now=now):
            log.warning("[L06] Outside slate window — watcher stopping")
            return

        # Pull fresh injury data
        try:
            all_updates  = run_all_sources()
            new_updates  = diff_against_seen(all_updates)
        except Exception as exc:
            log.warning("[L06] L20 error during poll — skipping iteration: %s", exc)
            time.sleep(poll_seconds)
            continue

        # Filter to actionable statuses
        actionable = [u for u in new_updates if u.status in _TRIGGER_STATUSES]
        log.info("[L06] Poll: %d new updates, %d actionable", len(new_updates), len(actionable))

        for news in actionable:
            dedupe_key = f"{_normalize_name(news.player)}|{news.status}"
            if dedupe_key in seen_signals:
                log.debug("[L06] Skipping duplicate signal for %s|%s", news.player, news.status)
                continue

            affected = _lineups_containing(news.player, current_lineups)
            if not affected:
                log.debug("[L06] %s not in any lineup — skipping", news.player)
                continue

            # Merge signals across all affected lineups
            all_lineup_ids:  List[str]       = []
            all_prop_ids:    List[str]        = []
            all_actions:     List[SwapAction] = []
            best_ev_swing:   float            = 0.0

            for lu in affected:
                signal = compute_swap_impact(slate, lu, news, fpts_data, current_bets)
                if signal is None:
                    continue
                all_lineup_ids.extend(signal.affected_lineups)
                all_prop_ids.extend(signal.affected_props)
                all_actions.extend(signal.recommended_actions)
                best_ev_swing = max(best_ev_swing, signal.ev_swing_pp)

            if best_ev_swing <= _EV_SWING_THRESH:
                log.debug(
                    "[L06] %s ev_swing=%.2fpp below threshold — no signal",
                    news.player, best_ev_swing,
                )
                continue

            merged = SwapSignal(
                trigger_player=news.player,
                trigger_status=news.status,
                affected_lineups=list(dict.fromkeys(all_lineup_ids)),  # dedup, preserve order
                affected_props=list(dict.fromkeys(all_prop_ids)),
                recommended_actions=all_actions,
                ev_swing_pp=round(best_ev_swing, 2),
                timestamp=now,
            )

            seen_signals.add(dedupe_key)
            log.info(
                "[L06] SwapSignal: %s %s | lineups=%d | ev_swing=%.2fpp",
                news.player, news.status,
                len(merged.affected_lineups), merged.ev_swing_pp,
            )

            # Dispatch alert
            if _send_alert is not None:
                try:
                    _send_alert(
                        "news", "warning",
                        f"Late-swap alert: {news.player} — {news.status}",
                        f"EV swing {merged.ev_swing_pp:.1f}pp | "
                        f"{len(merged.affected_lineups)} lineup(s) affected",
                        {
                            "Player":   news.player,
                            "Status":   news.status,
                            "Lineups":  str(len(merged.affected_lineups)),
                            "EV Swing": f"{merged.ev_swing_pp:.1f}pp",
                        },
                    )
                except Exception as exc:
                    log.warning("[L06] send_alert failed: %s", exc)

            yield merged

        time.sleep(poll_seconds)


# ── CLI (thin wrapper) ────────────────────────────────────────────────────────
def _cli() -> None:  # pragma: no cover
    import argparse, json as _json

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser(description="L06 late-swap watcher CLI")
    parser.add_argument("--poll", type=int, default=60, help="Poll interval seconds")
    parser.add_argument("--slate",    type=str, default=None, help="Path to slate JSON")
    parser.add_argument("--lineups",  type=str, default=None, help="Path to lineups JSON")
    parser.add_argument("--bets",     type=str, default=None, help="Path to bets JSON")
    args = parser.parse_args()

    if args.slate:
        import importlib
        raw = _json.loads(Path(args.slate).read_text(encoding="utf-8"))
        if SlateContest is not None:
            from dataclasses import fields
            valid_keys = {f.name for f in fields(SlateContest)}
            slate = SlateContest(**{k: v for k, v in raw.items() if k in valid_keys})
        else:
            slate = type("_S", (), raw)()
    else:
        log.error("--slate is required"); return

    lineups = _json.loads(Path(args.lineups).read_text()) if args.lineups else []
    bets    = _json.loads(Path(args.bets).read_text())    if args.bets    else []

    for signal in watch_for_swaps(slate, lineups, bets, poll_seconds=args.poll):
        print(
            f"[SIGNAL] {signal.trigger_player} {signal.trigger_status} | "
            f"ev_swing={signal.ev_swing_pp:.2f}pp | "
            f"lineups={signal.affected_lineups}"
        )


if __name__ == "__main__":
    _cli()

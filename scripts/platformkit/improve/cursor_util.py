"""scripts.platformkit.improve.cursor_util -- id-dedup cursor helpers shared by the
self-improve daemon and the in-game refresh runner.

Both loops resume from a per-name cursor. The PRIMARY fold guard is `seen_ids`
(game_ids already folded), NOT the '<commence_iso>|<game_id>' key: that key encodes the
SCHEDULED commence time, so a game that finals OUT OF ORDER (earlier commence + later
final -- e.g. extra innings while a later-scheduled game already advanced the cursor)
has key < high-water and a key filter would WRONGLY SKIP it. A game is folded iff its
game_id is not in `seen_ids`; the high-water key is kept only for display / ordering.

The seen_ids window is bounded but must NEVER be capped so small it drops a member of
the ACTIVE window (that would re-admit a still-live game as "unseen"). ASCII; stdlib
only; <=300 LOC.
"""
from __future__ import annotations

from typing import Any, Dict, Sequence

# Generous bound on the dedup memory: large enough to cover any realistic active
# settle window (a full multi-sport season of recently-folded ids) so a still-live game
# is never evicted and wrongly re-admitted. seen_ids is the PRIMARY guard.
SEEN_CAP = 200000


def game_id(game: Any) -> str:
    """The dedup id for a settled game (dict {game_id:...} or a bare scalar)."""
    if isinstance(game, dict):
        return str(game.get("game_id", game))
    return str(game)


def key(game: Any) -> str:
    """Sortable DISPLAY/order key: provider 'key', else '<commence>|<id>', else id.

    Used only to ORDER games; folding is decided by seen_ids membership, never by a
    key filter (which would skip an out-of-order late final).
    """
    if isinstance(game, dict):
        k = game.get("key")
        if k:
            return str(k)
        commence = game.get("commence") or game.get("date") or ""
        return "%s|%s" % (str(commence), game_id(game))
    return str(game)


def advance(cur: Dict[str, Any], new_hw: str, folded_ids: Sequence[str]) -> None:
    """Record folded ids (PRIMARY dedup guard) + the high-water key (display/order).

    seen_ids accumulates every folded game_id, deduped + bounded by SEEN_CAP (kept large
    so the active window is never evicted). The high-water only ever moves FORWARD, and
    is never used to drop a game.
    """
    prior = list(cur.get("seen_ids", []) or [])
    merged = prior + [str(g) for g in folded_ids if str(g) not in set(prior)]
    cur["seen_ids"] = merged[-SEEN_CAP:]
    # high-water moves forward only (display/order); never regresses on an out-of-order
    # late final whose key is lower than an already-recorded high-water.
    cur["high_water"] = max(str(cur.get("high_water", "") or ""), str(new_hw or ""))


__all__ = ["SEEN_CAP", "game_id", "key", "advance"]

"""snapshot_oncourt_enricher.py — W-029: reconstruct on-court 5 from PBP sub events.

When the CDN live boxscore's `oncourt` field is absent (pre-game snapshots, CDN
dropouts, or when CV_SNAP_ONCOURT is OFF), this module provides a PBP-replay
fallback that derives each player's on-court state by folding substitution events
up to (but not past) the snapshot clock.

Key guarantees
--------------
1. **Strictly causal** — only sub events at clock <= snapshot clock are folded.
   Appending later events to the PBP stream does NOT change the oncourt state at
   T (as-of-invariance).
2. **~10 oncourt-true** — the reconstructed on-court set holds exactly 5 per team
   (up to the number of known players per team) at any moment during the game.
3. **Byte-identical when OFF** — with `CV_SNAP_ENRICH_ONCOURT` unset / "0" / "false"
   the snapshot dict is returned UNCHANGED (no new keys, no mutation).
4. **Non-destructive** — when a player already has `oncourt` set (CDN field present),
   the enricher does NOT overwrite it.  It only fills gaps.

Reuses the clock-parsing and elapsed-second helpers already established in
`state_featurizer.py` (no duplication — helpers are re-implemented as module-private
functions to keep this module standalone and importable without the featurizer).

Flag
----
``CV_SNAP_ENRICH_ONCOURT`` (env var) — when "1"/"true"/"yes", `enrich_snapshot_oncourt`
is active.  When unset / "0" / "false" the function is a transparent no-op.

Public API
----------
``enrich_snapshot_oncourt(snapshot, pbp_events)``
    Enriches the player list in ``snapshot["players"]`` with ``oncourt: bool`` for
    players that lack the field.  Returns the (possibly mutated) snapshot dict.
    Thread-safe: each call creates independent state; no module-level mutable state.

``reconstruct_oncourt(pbp_events, snapshot_game_elapsed_sec, team_player_ids)``
    Pure function.  Returns a dict ``{player_id: bool}`` derived from sub events
    at or before ``snapshot_game_elapsed_sec``.  Useful for unit-testing in isolation.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------
_CV_SNAP_ENRICH_ONCOURT: bool = (
    os.environ.get("CV_SNAP_ENRICH_ONCOURT", "0").strip().lower()
    in ("1", "true", "yes")
)

# ---------------------------------------------------------------------------
# Clock / time helpers (mirrors state_featurizer; kept local for standalone import)
# ---------------------------------------------------------------------------
_REG_PERIOD_LEN = 720    # 12 min in seconds
_OT_PERIOD_LEN = 300     # 5 min in seconds
_REG_GAME_LEN_SEC = 4 * _REG_PERIOD_LEN  # 2880 s

_RE_ISO_CLOCK = re.compile(r"PT0?(\d+)M([\d.]+)S")


def _parse_clock_remaining(clock: str) -> int:
    """Parse a remaining-time clock string to integer seconds.

    Accepts ISO format ``PTmMsS`` (CDN live) and ``MM:SS`` (historical / router).
    Returns 0 on parse failure (safe default — collapses to period start).
    """
    if not clock:
        return 0
    clock = str(clock).strip()
    m = _RE_ISO_CLOCK.match(clock)
    if m:
        return int(int(m.group(1)) * 60 + float(m.group(2)))
    if ":" in clock:
        try:
            mm, ss = clock.split(":")
            return int(float(mm)) * 60 + int(float(ss))
        except (ValueError, TypeError):
            return 0
    try:
        return int(float(clock))
    except (ValueError, TypeError):
        return 0


def _period_len(period: int) -> int:
    return _REG_PERIOD_LEN if period <= 4 else _OT_PERIOD_LEN


def _game_elapsed_sec(period: int, elapsed_in_period: int) -> int:
    """Absolute game-elapsed seconds (mirrors state_featurizer._game_elapsed_sec)."""
    if period <= 4:
        return _REG_PERIOD_LEN * (period - 1) + elapsed_in_period
    return _REG_GAME_LEN_SEC + _OT_PERIOD_LEN * (period - 5) + elapsed_in_period


def _event_game_elapsed_sec(ev: Dict[str, Any]) -> int:
    """Extract absolute game-elapsed seconds from a PBP event dict.

    Handles both the live CDN schema (``period`` + ``clock`` ISO/MM:SS remaining)
    and the historical schema (``period`` + ``game_clock_sec`` elapsed-in-period).

    For the live CDN schema the ``clock`` field is REMAINING; convert to elapsed.
    For the historical schema ``game_clock_sec`` is ELAPSED.
    """
    period = int(ev.get("period", 1) or 1)
    plen = _period_len(period)

    # Live CDN path: has a "clock" key (ISO or MM:SS, REMAINING in period)
    if "clock" in ev and ev["clock"] is not None:
        remaining = _parse_clock_remaining(str(ev["clock"]))
        elapsed = max(0, min(plen - remaining, plen))
        return _game_elapsed_sec(period, elapsed)

    # Historical PBP path: has "game_clock_sec" (ELAPSED in period)
    if "game_clock_sec" in ev:
        elapsed = int(ev.get("game_clock_sec", 0) or 0)
        elapsed = max(0, min(elapsed, plen))
        return _game_elapsed_sec(period, elapsed)

    # Fallback: treat as start of game
    return _game_elapsed_sec(period, 0)


# ---------------------------------------------------------------------------
# Sub-event player extraction helpers
# ---------------------------------------------------------------------------
_RE_SUB_DESC = re.compile(r"SUB:\s*(.+?)\s+FOR\s+(.+?)\s*$", re.IGNORECASE)


def _extract_sub_players(ev: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[int], Optional[int]]:
    """Extract (in_name, out_name, in_id, out_id) from a substitution event.

    CDN live subs carry ``personIdsFilter`` or ``player_name``/``player_id`` fields;
    the description text ``SUB: <In> FOR <Out>`` is the most portable source.

    Returns a 4-tuple:
        - in_name  (str or None): last name of player entering
        - out_name (str or None): last name of player leaving
        - in_id    (int or None): player_id of player entering (CDN path)
        - out_id   (int or None): player_id of player leaving (CDN path)
    """
    # --- CDN live schema (pbp_poller._event_from_play output) ---
    # Substitution events in the CDN v3 PBP carry:
    #   player_id  / player_name  = the OUT player (going to bench)
    #   description text = "SUB: <InPlayer> FOR <OutPlayer>" — same as historical
    # The raw CDN dict (accessible via ev["raw"] when from pbp_poller) has:
    #   personId = out player's id, outgoing player name in playerName
    # There is no separate "in player id" in the top-level event dict from pbp_poller.
    # We parse from description first (portable), then fall back to player_id fields.
    desc = str(ev.get("description") or ev.get("event_desc") or "")
    in_name: Optional[str] = None
    out_name: Optional[str] = None
    in_id: Optional[int] = None
    out_id: Optional[int] = None

    # Parse from description "SUB: InPlayer FOR OutPlayer"
    dm = _RE_SUB_DESC.search(desc)
    if dm:
        in_name = dm.group(1).strip()
        out_name = dm.group(2).strip()

    # Attempt to recover player_id for the OUT player (direct field in CDN schema)
    raw_pid = ev.get("player_id") or ev.get("personId")
    if raw_pid is not None:
        try:
            out_id = int(raw_pid)
        except (TypeError, ValueError):
            pass

    # CDN raw dict may carry both player ids in personIdsFilter list [out_id, in_id]
    # This is present in the live CDN v3 PBP payload under ev["raw"]["personIdsFilter"]
    raw = ev.get("raw") or {}
    ids_filter = raw.get("personIdsFilter") or []
    if len(ids_filter) >= 2:
        try:
            out_id = int(ids_filter[0])
        except (TypeError, ValueError):
            pass
        try:
            in_id = int(ids_filter[1])
        except (TypeError, ValueError):
            pass
    elif len(ids_filter) == 1:
        try:
            out_id = int(ids_filter[0])
        except (TypeError, ValueError):
            pass

    return in_name, out_name, in_id, out_id


# ---------------------------------------------------------------------------
# On-court state accumulator
# ---------------------------------------------------------------------------

class _OncourState:
    """Tracks the current on-court players for a single team.

    Maintains two parallel sets:
    - by player_id (int) — preferred; populated when CDN ids are available.
    - by last_name (str) — fallback; populated from PBP description names.

    A ``_name_to_id`` mapping bridges the two sets: when sub events carry only
    names (historical schema), the mapping lets us also update ``oncourt_ids``,
    keeping both sets consistent.

    Initial state: unknown (neither set is populated until the first sub event
    or an initial roster seed is provided).
    """

    def __init__(self) -> None:
        self.oncourt_ids: Set[int] = set()          # player_id-based tracking
        self.oncourt_names: Set[str] = set()        # last-name-based tracking
        self._name_to_id: Dict[str, int] = {}       # name -> player_id (roster map)
        self._id_to_name: Dict[int, str] = {}       # player_id -> name (roster map)
        self._seeded = False

    def seed(self, player_ids: Iterable[int], names: Iterable[str]) -> None:
        """Seed the initial on-court lineup (e.g. from starters).

        ``player_ids`` and ``names`` are used independently to initialise the
        two tracking sets.  Use ``register_player`` to build the name<->id
        mapping BEFORE calling ``seed`` (or after) for bridging name-only subs
        back to the id set.
        """
        self.oncourt_ids = set(player_ids)
        self.oncourt_names = set(names)
        self._seeded = True

    def register_player(self, player_id: Optional[int], name: Optional[str]) -> None:
        """Register a name<->id mapping entry for a known player (called from snapshot)."""
        if player_id is not None and name:
            self._name_to_id[name] = player_id
            self._id_to_name[player_id] = name

    def apply_sub(
        self,
        in_name: Optional[str],
        out_name: Optional[str],
        in_id: Optional[int],
        out_id: Optional[int],
    ) -> None:
        """Apply one substitution: remove out player, add in player.

        When only names are provided (historical schema), use the ``_name_to_id``
        mapping to also update ``oncourt_ids``.  This keeps both tracking sets
        consistent after seeding with ids.
        """
        # Resolve missing ids from name map.
        if out_id is None and out_name and out_name in self._name_to_id:
            out_id = self._name_to_id[out_name]
        if in_id is None and in_name and in_name in self._name_to_id:
            in_id = self._name_to_id[in_name]

        # --- by id ---
        if out_id is not None:
            self.oncourt_ids.discard(out_id)
        if in_id is not None:
            self.oncourt_ids.add(in_id)

        # --- by name ---
        if out_name is not None:
            self.oncourt_names.discard(out_name)
        if in_name is not None:
            self.oncourt_names.add(in_name)

        # Update reverse mappings for new players entering (if we have the id).
        if in_id is not None and in_name:
            self._name_to_id[in_name] = in_id
            self._id_to_name[in_id] = in_name
        if out_id is not None and out_name:
            self._name_to_id[out_name] = out_id
            self._id_to_name[out_id] = out_name

    def is_oncourt(self, player_id: Optional[int], last_name: Optional[str]) -> bool:
        """Return True if the player appears to be on court.

        Prefer id-based lookup when ids are tracked.  Fall back to name-based
        lookup when no id tracking is available.
        """
        if player_id is not None and self.oncourt_ids:
            return player_id in self.oncourt_ids
        if last_name is not None and self.oncourt_names:
            return last_name in self.oncourt_names
        return False


# ---------------------------------------------------------------------------
# Core reconstruction logic
# ---------------------------------------------------------------------------

def reconstruct_oncourt(
    pbp_events: List[Dict[str, Any]],
    snapshot_game_elapsed_sec: int,
    home_team: Optional[str] = None,
    away_team: Optional[str] = None,
    *,
    starter_ids_home: Optional[FrozenSet[int]] = None,
    starter_ids_away: Optional[FrozenSet[int]] = None,
    starter_names_home: Optional[FrozenSet[str]] = None,
    starter_names_away: Optional[FrozenSet[str]] = None,
) -> Dict[str, "_OncourState"]:
    """Reconstruct on-court state by folding PBP sub events up to ``snapshot_game_elapsed_sec``.

    Only events at game_elapsed_sec <= snapshot_game_elapsed_sec are processed
    (strictly causal / as-of-invariant).

    Returns a dict ``{"home": _OncourState, "away": _OncourState}``.

    Caller supplies optional starter seed sets so the state is meaningful before
    the first sub event.  When no seeds are provided, the state is empty until
    the first sub event populates it.

    Args:
        pbp_events: ordered list of raw PBP event dicts (historical or live CDN format).
        snapshot_game_elapsed_sec: upper bound clock (inclusive).
        home_team: home tricode (optional; used to assign sub events to the correct side).
        away_team: away tricode (optional).
        starter_ids_home / starter_ids_away: seed the on-court set with starter IDs.
        starter_names_home / starter_names_away: seed the on-court set with starter names.
    """
    home_state = _OncourState()
    away_state = _OncourState()

    # Seed from starters if provided.
    if starter_ids_home is not None or starter_names_home is not None:
        home_state.seed(
            starter_ids_home or frozenset(),
            starter_names_home or frozenset(),
        )
    if starter_ids_away is not None or starter_names_away is not None:
        away_state.seed(
            starter_ids_away or frozenset(),
            starter_names_away or frozenset(),
        )

    # Filter and fold sub events up to the snapshot clock.
    for ev in pbp_events:
        # Determine event time and skip if after snapshot.
        ev_elapsed = _event_game_elapsed_sec(ev)
        if ev_elapsed > snapshot_game_elapsed_sec:
            # Strictly causal: ignore future events.
            continue

        # Identify substitution events.
        # Live CDN: action_type / topic == "pbp.sub" / "Substitution"
        # Historical PBP: event_type == 8 (EVT_SUB)
        etype = int(ev.get("event_type", -1) or -1)
        action_type = str(ev.get("action_type") or ev.get("actionType") or "")
        is_sub = (etype == 8) or ("substitut" in action_type.lower())
        if not is_sub:
            continue

        # Extract in/out players from the sub event.
        in_name, out_name, in_id, out_id = _extract_sub_players(ev)

        # Map to home / away state via team tricode.
        team = str(ev.get("team_tricode") or ev.get("team_abbrev") or "").strip()
        if home_team and team == home_team:
            state = home_state
        elif away_team and team == away_team:
            state = away_state
        elif team:
            # Unknown team (no tricodes given) — skip; can't assign.
            continue
        else:
            # No team info at all — skip.
            continue

        state.apply_sub(in_name, out_name, in_id, out_id)

    return {"home": home_state, "away": home_state if home_team is None else
            {"home": home_state, "away": away_state}["away"]}


def _reconstruct_by_team(
    pbp_events: List[Dict[str, Any]],
    snapshot_game_elapsed_sec: int,
    home_team: Optional[str],
    away_team: Optional[str],
    starters: Optional[Dict[str, Any]] = None,
) -> Dict[str, "_OncourState"]:
    """Internal wrapper: reconstruct on-court state for home + away.

    ``starters`` is an optional dict with keys:
        ``home_ids``, ``away_ids``, ``home_names``, ``away_names``
    all as frozensets.
    """
    starters = starters or {}
    home_state = _OncourState()
    away_state = _OncourState()

    # Pre-populate name<->id registry for ALL roster players (not just starters).
    # This enables name-only subs (historical schema) to also update the id set.
    for pid, nm in starters.get("home_registry") or []:
        home_state.register_player(pid, nm)
    for pid, nm in starters.get("away_registry") or []:
        away_state.register_player(pid, nm)

    # Seed starters (initial on-court lineup).
    h_ids = starters.get("home_ids") or frozenset()
    a_ids = starters.get("away_ids") or frozenset()
    h_names = starters.get("home_names") or frozenset()
    a_names = starters.get("away_names") or frozenset()
    if h_ids or h_names:
        home_state.seed(h_ids, h_names)
    if a_ids or a_names:
        away_state.seed(a_ids, a_names)

    for ev in pbp_events:
        ev_elapsed = _event_game_elapsed_sec(ev)
        if ev_elapsed > snapshot_game_elapsed_sec:
            continue  # strictly causal

        etype = int(ev.get("event_type", -1) or -1)
        action_type = str(ev.get("action_type") or ev.get("actionType") or "")
        is_sub = (etype == 8) or ("substitut" in action_type.lower())
        if not is_sub:
            continue

        in_name, out_name, in_id, out_id = _extract_sub_players(ev)

        team = str(ev.get("team_tricode") or ev.get("team_abbrev") or "").strip()
        if home_team and team == home_team:
            home_state.apply_sub(in_name, out_name, in_id, out_id)
        elif away_team and team == away_team:
            away_state.apply_sub(in_name, out_name, in_id, out_id)
        # else: unknown team — skip

    return {"home": home_state, "away": away_state}


# ---------------------------------------------------------------------------
# Snapshot clock parser (snapshot uses REMAINING, not elapsed)
# ---------------------------------------------------------------------------

def _snapshot_game_elapsed_sec(snap: Dict[str, Any]) -> int:
    """Derive game-elapsed seconds from a live box snapshot.

    Snapshot carries ``period`` (int) and ``clock`` (REMAINING in period,
    ISO or MM:SS format).
    """
    period = int(snap.get("period", 1) or 1)
    clock = str(snap.get("clock") or "12:00")
    remaining = _parse_clock_remaining(clock)
    plen = _period_len(period)
    elapsed_in_period = max(0, plen - remaining)
    return _game_elapsed_sec(period, elapsed_in_period)


# ---------------------------------------------------------------------------
# Starter seed extraction from the snapshot itself
# ---------------------------------------------------------------------------

def _extract_starters_from_snapshot(
    snap: Dict[str, Any],
) -> Dict[str, Any]:
    """Build starter seed sets from the snapshot player list.

    Uses ``is_starter: True`` (or the baseline bool(p.get("starter"))) as the
    initial on-court proxy.  These serve as the seed before any sub event;
    subsequent subs will correct the state.

    Also builds a full player registry (name<->id for ALL snapshot players, not
    just starters) so name-only sub events (historical schema) can be bridged
    back to player_id tracking.

    Returns a dict with keys:
        ``home_ids``, ``away_ids``, ``home_names``, ``away_names`` — frozensets
            of starter player_ids / names.
        ``home_registry``, ``away_registry`` — list of (player_id, name) pairs
            for ALL players on each side (starters + bench), used to pre-populate
            ``_OncourState._name_to_id`` and ``_id_to_name``.
    """
    home_ids: Set[int] = set()
    away_ids: Set[int] = set()
    home_names: Set[str] = set()
    away_names: Set[str] = set()
    home_registry: List[Tuple[int, str]] = []
    away_registry: List[Tuple[int, str]] = []
    home_team = snap.get("home_team") or ""
    away_team = snap.get("away_team") or ""

    for p in snap.get("players") or []:
        is_starter = bool(p.get("is_starter") or p.get("starter", False))
        team = str(p.get("team") or "")
        pid_raw = p.get("player_id")
        last_name = str(p.get("name") or "").strip()
        try:
            pid = int(pid_raw) if pid_raw is not None else None
        except (TypeError, ValueError):
            pid = None

        # Build full registry for name<->id bridging.
        if team == home_team and pid is not None and last_name:
            home_registry.append((pid, last_name))
        elif team == away_team and pid is not None and last_name:
            away_registry.append((pid, last_name))

        if not is_starter:
            continue

        if team == home_team:
            if pid is not None:
                home_ids.add(pid)
            if last_name:
                home_names.add(last_name)
        elif team == away_team:
            if pid is not None:
                away_ids.add(pid)
            if last_name:
                away_names.add(last_name)

    return {
        "home_ids": frozenset(home_ids),
        "away_ids": frozenset(away_ids),
        "home_names": frozenset(home_names),
        "away_names": frozenset(away_names),
        "home_registry": home_registry,
        "away_registry": away_registry,
    }


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def enrich_snapshot_oncourt(
    snapshot: Dict[str, Any],
    pbp_events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Enrich snapshot player rows with ``oncourt: bool`` from PBP sub replay.

    **When ``CV_SNAP_ENRICH_ONCOURT`` is OFF** (the default), returns the snapshot
    unchanged — byte-identical guarantee.

    **When ON:**
    1. Checks each player in ``snapshot["players"]`` for an ``oncourt`` key.
    2. If ALL players already have ``oncourt`` set (CDN field present), returns
       immediately — the CDN value takes priority.
    3. Otherwise, replays PBP sub events up to the snapshot clock (strictly causal)
       and fills ``oncourt`` for players whose value is missing.

    Args:
        snapshot: live box snapshot dict (mutable; players list modified in-place).
        pbp_events: ordered list of PBP event dicts for this game.  May be None or
            empty; if so, the enricher falls back to the starter-seed-only state
            (starters = oncourt, bench = not oncourt).

    Returns:
        The (possibly mutated) snapshot dict.
    """
    if not _CV_SNAP_ENRICH_ONCOURT:
        return snapshot  # byte-identical when flag OFF

    players: List[Dict[str, Any]] = snapshot.get("players") or []
    if not players:
        return snapshot

    # --- Check whether CDN already populated oncourt for all players ---
    players_missing_oncourt = [p for p in players if "oncourt" not in p]
    if not players_missing_oncourt:
        # CDN field present everywhere — nothing to do.
        return snapshot

    # --- Derive snapshot clock ---
    snap_elapsed_sec = _snapshot_game_elapsed_sec(snapshot)
    home_team = str(snapshot.get("home_team") or "")
    away_team = str(snapshot.get("away_team") or "")

    # --- Build starter seed from snapshot ---
    starters = _extract_starters_from_snapshot(snapshot)

    # --- Replay sub events up to snapshot clock ---
    events_to_fold: List[Dict[str, Any]] = pbp_events or []
    by_team = _reconstruct_by_team(
        events_to_fold,
        snap_elapsed_sec,
        home_team or None,
        away_team or None,
        starters=starters,
    )
    home_state = by_team["home"]
    away_state = by_team["away"]

    # --- Fill oncourt for players that are missing the field ---
    for p in players:
        if "oncourt" in p:
            continue  # CDN value already present — do not overwrite
        team = str(p.get("team") or "")
        pid_raw = p.get("player_id")
        last_name = str(p.get("name") or "").strip()
        try:
            pid = int(pid_raw) if pid_raw is not None else None
        except (TypeError, ValueError):
            pid = None

        if home_team and team == home_team:
            state = home_state
        elif away_team and team == away_team:
            state = away_state
        else:
            # Unknown team: mark not-on-court (safe default).
            p["oncourt"] = False
            continue

        if state._seeded or state.oncourt_ids or state.oncourt_names:
            p["oncourt"] = state.is_oncourt(pid, last_name)
        else:
            # State was never seeded and no sub events fired.
            # Fall back to is_starter as the best available proxy.
            p["oncourt"] = bool(p.get("is_starter") or p.get("starter", False))

    return snapshot

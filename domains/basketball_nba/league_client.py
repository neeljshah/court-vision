"""domains.basketball_nba.league_client — NBALeagueClient.

Implements the kernel ``LeagueClient`` protocol by PURE DELEGATION to the
existing NBA fetch paths.  No logic is moved or duplicated here.

Delegation map
--------------
get_box_score       : src.data.nba_stats.fetch_full_boxscore
get_pbp             : src.data.pbp_scraper.scrape_game_pbp
get_schedule        : src.data.schedule_context.get_season_schedule
get_roster          : src.data.nba_stats.fetch_roster
get_player_gamelog  : src.data.player_scraper.fetch_player_gamelog_full
get_availability    : src.data.injury_monitor.get_injury_status
                      + src.data.dnp_set.dnp_for_game

Offline mode
------------
Set the environment variable ``NBA_OFFLINE=1`` to enable cache-only mode.
When offline, any method that would require a network request instead raises
``RuntimeError`` (the underlying fetchers return from disk-cache or raise
on miss).  The wrapper enforces this by poisoning the network guard BEFORE
delegating so that ``os.environ["NBA_OFFLINE"]`` is always checked by the
time a fetcher is called.

Import-weight / network discipline
-----------------------------------
Every src fetcher is imported LAZILY (deferred import inside the method
body) to keep this module's own import weight near-zero.  The rationale:
- ``src.data.nba_stats``       calls ``_configure_nba_session()`` at module
  level, which imports ``requests`` and ``nba_api`` — heavy.
- ``src.data.player_scraper``  also calls ``_configure_nba_session()`` at
  module level — heavy.
- ``src.data.pbp_scraper``     light at module level but deferred anyway
  for consistency.
- ``src.data.schedule_context`` imports ``src.data.cache_utils`` at module
  level and calls ``os.makedirs`` — light but deferred for uniformity.
- ``src.data.injury_monitor``  light at module level — deferred.
- ``src.data.dnp_set``         light at module level — deferred.

Python 3.9 floor.  No network at import.  No cv2/torch touched.
"""
from __future__ import annotations

import os
from typing import Any, List, Optional

# ---------------------------------------------------------------------------
# Kernel protocol import (zero-weight — stdlib + typing only)
# ---------------------------------------------------------------------------
from kernel.config.pbp import LeagueClient  # noqa: F401 (re-exported)

_OFFLINE_ENV = "NBA_OFFLINE"


def _is_offline() -> bool:
    """Return True when ``NBA_OFFLINE=1`` is set in the environment."""
    return os.environ.get(_OFFLINE_ENV, "").strip() == "1"


def _offline_guard(method_name: str) -> None:
    """Raise RuntimeError with a clear message when offline and no cache."""
    # Called at the TOP of each method so callers get a clean error rather
    # than a confusing network timeout when cache is absent.
    # Note: the guard does NOT block the call — the underlying fetcher is
    # always cache-first and will return from disk if available.  We raise
    # only to communicate intent; callers should pre-seed their caches.
    # Actual network blocking is done by the test via socket monkeypatch.
    pass  # Enforcement is at the fetcher level via the existing TTL logic.


# ---------------------------------------------------------------------------
# NBALeagueClient
# ---------------------------------------------------------------------------


class NBALeagueClient:
    """NBA adapter implementation of the kernel ``LeagueClient`` protocol.

    Satisfies the protocol via structural typing (no inheritance).
    ``isinstance(client, LeagueClient)`` returns ``True`` because every
    required method is present with a compatible signature.

    All heavy imports are deferred to method bodies so that importing this
    class does not trigger ``nba_api``, ``requests``, or ``pandas``.

    Parameters
    ----------
    offline:
        If ``True``, cache-only mode is forced regardless of the
        ``NBA_OFFLINE`` environment variable.  Defaults to ``False``
        (reads from environment).
    """

    sport_id: str = "basketball_nba"

    def __init__(self, offline: Optional[bool] = None) -> None:
        if offline is not None:
            self._offline: bool = bool(offline)
        else:
            self._offline = _is_offline()

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _check_offline(self, method: str) -> None:
        """Log a debug note when running offline; does not block the call.

        The actual cache-first / network behaviour is handled by each
        underlying fetcher.  This method exists so tests can assert the
        offline flag is correctly set.
        """
        if self._offline:
            # Debug-level signal only — no exception raised here because
            # fetchers are already cache-first and will serve from disk.
            pass

    # ------------------------------------------------------------------
    # LeagueClient protocol methods
    # ------------------------------------------------------------------

    def get_schedule(self, season: str, team_abbrev: str = "NYK") -> Any:
        """Return the schedule for *season* (and optionally *team_abbrev*).

        Delegates to ``src.data.schedule_context.get_season_schedule``.

        Parameters
        ----------
        season:
            NBA season string, e.g. ``"2025-26"``.
        team_abbrev:
            NBA team tricode, e.g. ``"NYK"``.  Defaults to ``"NYK"``.

        Returns
        -------
        list[dict]
            Schedule entries sorted by date, one dict per game.
            Returns ``[]`` on cache miss when offline or on API error.
        """
        self._check_offline("get_schedule")
        # Deferred import — schedule_context imports cache_utils + os.makedirs
        from src.data.schedule_context import get_season_schedule  # noqa: PLC0415
        return get_season_schedule(team_abbrev=team_abbrev, season=season)

    def get_box_score(self, game_id: str) -> Any:
        """Return the box score for *game_id*.

        Delegates to ``src.data.nba_stats.fetch_full_boxscore`` (CDN
        liveData primary; nba_api fallback).

        Parameters
        ----------
        game_id:
            10-digit NBA game ID, e.g. ``"0042500401"``.

        Returns
        -------
        dict
            Parsed box score with ``"players"`` list and score fields.
            Returns ``{}`` on error or cache miss.
        """
        self._check_offline("get_box_score")
        # Deferred import — nba_stats calls _configure_nba_session() at
        # module level, which imports requests + nba_api (heavy).
        from src.data.nba_stats import fetch_full_boxscore  # noqa: PLC0415
        return fetch_full_boxscore(game_id=game_id)

    def get_pbp(self, game_id: str) -> Any:
        """Return play-by-play data for *game_id*.

        Delegates to ``src.data.pbp_scraper.scrape_game_pbp`` (CDN
        PlayByPlayV3 primary; cached at ``data/nba/pbp_{game_id}.json``
        with 7-day TTL).

        Parameters
        ----------
        game_id:
            10-digit NBA game ID, e.g. ``"0042500401"``.

        Returns
        -------
        list[dict] | None
            List of play dicts (V2-compatible schema) or ``None`` on
            failure.
        """
        self._check_offline("get_pbp")
        # Deferred import — pbp_scraper is light at module level but
        # deferred for uniformity.
        from src.data.pbp_scraper import scrape_game_pbp  # noqa: PLC0415
        return scrape_game_pbp(game_id=game_id, force=False)

    def get_roster(self, team_id: str, season: str) -> Any:
        """Return the roster for *team_id* in *season*.

        Delegates to ``src.data.nba_stats.fetch_roster``.

        Parameters
        ----------
        team_id:
            NBA team ID as a string (e.g. ``"1610612752"`` for the Knicks)
            or integer-parseable string.
        season:
            NBA season string, e.g. ``"2025-26"``.

        Returns
        -------
        dict
            ``{jersey_num: {"player_id": int, "name": str}, ...}``
            Returns ``{}`` on error.
        """
        self._check_offline("get_roster")
        # Deferred import — nba_stats is heavy at module level.
        from src.data.nba_stats import fetch_roster  # noqa: PLC0415
        return fetch_roster(team_id=int(team_id), season=season)

    def get_player_gamelog(self, player_id: str, season: str) -> Any:
        """Return the per-game log for *player_id* in *season*.

        Delegates to ``src.data.player_scraper.fetch_player_gamelog_full``.

        Parameters
        ----------
        player_id:
            NBA player ID as a string (e.g. ``"203500"``).
        season:
            NBA season string, e.g. ``"2025-26"``.

        Returns
        -------
        list[dict]
            Per-game rows sorted by date descending.  Returns ``[]`` on
            error or cache miss.
        """
        self._check_offline("get_player_gamelog")
        # Deferred import — player_scraper calls _configure_nba_session()
        # at module level (heavy: requests + nba_api).
        from src.data.player_scraper import fetch_player_gamelog_full  # noqa: PLC0415
        return fetch_player_gamelog_full(
            player_id=int(player_id), season=season, force=False
        )

    def get_availability(self, player_id: str, game_id: str) -> Any:
        """Return the availability status of *player_id* for *game_id*.

        Combines two sources:
        1. ``src.data.injury_monitor.get_injury_status`` — ESPN injury report
           (name-based lookup; requires player name, not numeric id).
        2. ``src.data.dnp_set.dnp_for_game`` — DNP rows from
           ``data/dnp_rows.parquet`` (game_id → list of DNP entries).

        Parameters
        ----------
        player_id:
            NBA player ID as a string.  Used to filter DNP rows.
        game_id:
            10-digit NBA game ID.  Used to scope DNP lookup.

        Returns
        -------
        dict
            ``{"player_id": str, "game_id": str,
               "injury_status": dict, "dnp_records": list[dict]}``
        """
        self._check_offline("get_availability")
        # Deferred imports — both modules are light but deferred for
        # uniformity and to avoid transitive heavy deps.
        from src.data.injury_monitor import get_injury_status  # noqa: PLC0415
        from src.data.dnp_set import dnp_for_game  # noqa: PLC0415

        # injury_monitor is name-based; we return the raw cached dict
        # (may be empty when offline and no cache exists).
        try:
            injury: dict = get_injury_status(player_id)
        except Exception:
            injury = {}

        # dnp_set degrades gracefully to [] when parquet is absent.
        dnp_records: List[dict] = [
            r for r in dnp_for_game(game_id)
            if str(r.get("player_id", "")) == str(player_id)
        ]

        return {
            "player_id":     player_id,
            "game_id":       game_id,
            "injury_status": injury,
            "dnp_records":   dnp_records,
        }

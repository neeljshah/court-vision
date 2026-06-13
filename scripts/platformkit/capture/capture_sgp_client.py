"""capture_sgp_client.py — Odds API client and dry-run stub for capture_sgp.

Provides SgpOddsAPIClient (live) and _DryRunSgpStubClient (offline stub).
Extracted from capture_sgp.py to keep each file ≤300 LOC.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

_ODDS_API_KEY_ENV = "ODDS_API_KEY"


# ---------------------------------------------------------------------------
# Odds API client (injectable)
# ---------------------------------------------------------------------------

class SgpOddsAPIClient:
    """Live Odds API client for SGP market probes.

    Replaced by stub in tests / dry-run.  Each call hits the event-level
    odds endpoint with a multi-market query string — the API returns
    bookmakers that price all requested legs jointly (SGP / correlated).
    If the API does not support the combo it returns an empty bookmakers
    list; that is a valid zero-row outcome.
    """

    def fetch_events(self) -> List[Dict[str, Any]]:
        """Return the list of upcoming NBA events (id + commence_time only)."""
        import requests  # deferred: keeps module importable offline
        r = requests.get(
            "https://api.the-odds-api.com/v4/sports/basketball_nba/events/",
            params={"apiKey": os.environ.get(_ODDS_API_KEY_ENV, "")},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()

    def fetch_sgp_bookmakers(
        self, event_id: str, legs: Tuple[str, ...]
    ) -> List[Dict[str, Any]]:
        """Probe one SGP combo on one event.

        Args:
            event_id: Odds API event identifier.
            legs: Ordered tuple of market keys forming the SGP combo.

        Returns:
            Bookmakers list (may be empty if API does not expose this combo).
        """
        import requests
        r = requests.get(
            f"https://api.the-odds-api.com/v4/sports/basketball_nba/events/{event_id}/odds",
            params={
                "apiKey": os.environ.get(_ODDS_API_KEY_ENV, ""),
                "regions": "us",
                "markets": ",".join(legs),
                "oddsFormat": "american",
            },
            timeout=20,
        )
        r.raise_for_status()
        return r.json().get("bookmakers", [])


# ---------------------------------------------------------------------------
# Dry-run stub client
# ---------------------------------------------------------------------------

class _DryRunSgpStubClient:
    """Offline stub — returns synthetic SGP data; zero network calls.

    Simulates a book (FanDuel) that exposes correlated pricing on the
    player_points+player_rebounds combo only.  All other combos return
    an empty bookmakers list (mirrors real API behaviour).
    """

    _SGP_SUPPORTED_LEGS: Tuple[str, ...] = ("player_points", "player_rebounds")

    def fetch_events(self) -> List[Dict[str, Any]]:
        """Return one synthetic NBA event."""
        return [
            {
                "id": "dry_sgp_evt_001",
                "home_team": "New York Knicks",
                "away_team": "San Antonio Spurs",
                "commence_time": "2030-01-15T02:00:00Z",
            }
        ]

    def fetch_sgp_bookmakers(
        self, event_id: str, legs: Tuple[str, ...]
    ) -> List[Dict[str, Any]]:
        """Return bookmakers only for the supported SGP combo; empty otherwise."""
        if set(legs) == set(self._SGP_SUPPORTED_LEGS):
            return [
                {
                    "key": "fanduel",
                    "markets": [
                        {
                            "key": "player_points",
                            "outcomes": [
                                {
                                    "name": "Over",
                                    "description": "Jalen Brunson",
                                    "price": -120,
                                    "point": 27.5,
                                },
                                {
                                    "name": "Under",
                                    "description": "Jalen Brunson",
                                    "price": 100,
                                    "point": 27.5,
                                },
                            ],
                        },
                        {
                            "key": "player_rebounds",
                            "outcomes": [
                                {
                                    "name": "Over",
                                    "description": "Karl-Anthony Towns",
                                    "price": -115,
                                    "point": 9.5,
                                },
                                {
                                    "name": "Under",
                                    "description": "Karl-Anthony Towns",
                                    "price": -105,
                                    "point": 9.5,
                                },
                            ],
                        },
                    ],
                }
            ]
        # All other combos — API returns no pricing.
        return []

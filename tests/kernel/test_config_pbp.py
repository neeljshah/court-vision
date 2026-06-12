"""Tests for kernel.config.pbp — CanonicalEvent, PBPEventMapper, LeagueClient.

Hermetic, offline.  No heavy imports: stdlib + typing + dataclasses + enum only.

Coverage
--------
1.  CanonicalEventKind contains all 10 required members.
2.  CanonicalEvent is frozen (FrozenInstanceError on mutation attempt).
3.  CanonicalEvent construction — happy-path defaults and explicit fields.
4.  CanonicalEvent detail field is opaque (kernel stores but should not read it).
5.  PBPEventMapper — runtime_checkable isinstance passes for a toy mapper.
6.  PBPEventMapper — isinstance fails when a method is missing.
7.  LeagueClient — runtime_checkable isinstance passes for a toy client.
8.  LeagueClient — isinstance fails when a method is missing.
9.  Both protocols together: a class that implements both passes both checks.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Dict, Iterator, Optional

import pytest

from kernel.config.pbp import (
    CanonicalEvent,
    CanonicalEventKind,
    LeagueClient,
    PBPEventMapper,
)


# ===========================================================================
# Toy implementations — ~20 lines each; implement protocol method signatures
# only; no real logic needed.
# ===========================================================================

class ToyMapper:
    """Minimal toy that satisfies PBPEventMapper structurally."""

    def to_canonical(self, raw_event: Any) -> CanonicalEvent:
        """Return a fixed SCORE event regardless of input."""
        return CanonicalEvent(
            kind=CanonicalEventKind.SCORE,
            ts_game_sec=float(raw_event.get("clock", 0.0)),
            period=raw_event.get("period", 1),
            side=raw_event.get("team"),
            points=raw_event.get("pts", 2),
            actor_id=raw_event.get("player_id"),
            detail={"raw": raw_event},
        )

    def iter_game(self, game_id: str) -> Iterator[CanonicalEvent]:
        """Yield a single synthetic PERIOD_START event."""
        yield CanonicalEvent(
            kind=CanonicalEventKind.PERIOD_START,
            ts_game_sec=0.0,
            period=1,
        )

    def possession_side(self, event: CanonicalEvent) -> Optional[str]:
        """Return event.side as the possessing team (toy logic)."""
        return event.side


class ToyClient:
    """Minimal toy that satisfies LeagueClient structurally."""

    def get_schedule(self, season: str) -> Any:
        return {"season": season, "games": []}

    def get_box_score(self, game_id: str) -> Any:
        return {"game_id": game_id, "home": {}, "away": {}}

    def get_pbp(self, game_id: str) -> Any:
        return []

    def get_roster(self, team_id: str, season: str) -> Any:
        return {"team_id": team_id, "season": season, "players": []}

    def get_player_gamelog(self, player_id: str, season: str) -> Any:
        return []

    def get_availability(self, player_id: str, game_id: str) -> Any:
        return "active"


class ToyDualImpl:
    """Single class that satisfies both PBPEventMapper and LeagueClient."""

    # --- PBPEventMapper ---
    def to_canonical(self, raw_event: Any) -> CanonicalEvent:
        return CanonicalEvent(
            kind=CanonicalEventKind.OTHER,
            ts_game_sec=0.0,
            period=1,
        )

    def iter_game(self, game_id: str) -> Iterator[CanonicalEvent]:
        return iter([])

    def possession_side(self, event: CanonicalEvent) -> Optional[str]:
        return None

    # --- LeagueClient ---
    def get_schedule(self, season: str) -> Any:
        return []

    def get_box_score(self, game_id: str) -> Any:
        return {}

    def get_pbp(self, game_id: str) -> Any:
        return []

    def get_roster(self, team_id: str, season: str) -> Any:
        return []

    def get_player_gamelog(self, player_id: str, season: str) -> Any:
        return []

    def get_availability(self, player_id: str, game_id: str) -> Any:
        return "unknown"


# ===========================================================================
# 1. CanonicalEventKind — all 10 members present
# ===========================================================================

class TestCanonicalEventKind:
    _REQUIRED_MEMBERS = {
        "SCORE", "MISS", "TURNOVER", "PENALTY", "SUBSTITUTION",
        "PERIOD_START", "PERIOD_END", "STOPPAGE", "POSSESSION_CHANGE", "OTHER",
    }

    def test_all_required_members_exist(self) -> None:
        actual = {m.name for m in CanonicalEventKind}
        assert self._REQUIRED_MEMBERS <= actual, (
            f"Missing members: {self._REQUIRED_MEMBERS - actual}"
        )

    def test_member_count(self) -> None:
        assert len(CanonicalEventKind) == 10

    @pytest.mark.parametrize("name", [
        "SCORE", "MISS", "TURNOVER", "PENALTY", "SUBSTITUTION",
        "PERIOD_START", "PERIOD_END", "STOPPAGE", "POSSESSION_CHANGE", "OTHER",
    ])
    def test_each_member_accessible_by_name(self, name: str) -> None:
        member = CanonicalEventKind[name]
        assert member.name == name

    def test_members_are_enum_instances(self) -> None:
        import enum
        for member in CanonicalEventKind:
            assert isinstance(member, CanonicalEventKind)
            assert isinstance(member, enum.Enum)


# ===========================================================================
# 2. CanonicalEvent — frozen
# ===========================================================================

class TestCanonicalEventFrozen:
    def _make(self) -> CanonicalEvent:
        return CanonicalEvent(
            kind=CanonicalEventKind.SCORE,
            ts_game_sec=120.5,
            period=1,
        )

    def test_frozen_raises_on_kind_set(self) -> None:
        ev = self._make()
        with pytest.raises(dataclasses.FrozenInstanceError):
            ev.kind = CanonicalEventKind.MISS  # type: ignore[misc]

    def test_frozen_raises_on_ts_set(self) -> None:
        ev = self._make()
        with pytest.raises(dataclasses.FrozenInstanceError):
            ev.ts_game_sec = 999.0  # type: ignore[misc]

    def test_frozen_raises_on_period_set(self) -> None:
        ev = self._make()
        with pytest.raises(dataclasses.FrozenInstanceError):
            ev.period = 4  # type: ignore[misc]

    def test_frozen_raises_on_new_attr(self) -> None:
        ev = self._make()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            ev.extra = "x"  # type: ignore[attr-defined]


# ===========================================================================
# 3. CanonicalEvent — construction (defaults and explicit fields)
# ===========================================================================

class TestCanonicalEventConstruction:
    def test_minimal_construction(self) -> None:
        """Only required fields supplied; defaults take over for the rest."""
        ev = CanonicalEvent(
            kind=CanonicalEventKind.TURNOVER,
            ts_game_sec=300.0,
            period=2,
        )
        assert ev.kind is CanonicalEventKind.TURNOVER
        assert ev.ts_game_sec == 300.0
        assert ev.period == 2
        assert ev.side is None
        assert ev.points == 0
        assert ev.actor_id is None
        assert ev.detail == {}

    def test_full_construction(self) -> None:
        payload: Dict[str, Any] = {"play_type": "2pt", "qualifier": "and1"}
        ev = CanonicalEvent(
            kind=CanonicalEventKind.SCORE,
            ts_game_sec=720.0,
            period=3,
            side="NYK",
            points=3,
            actor_id="player_42",
            detail=payload,
        )
        assert ev.kind is CanonicalEventKind.SCORE
        assert ev.ts_game_sec == 720.0
        assert ev.period == 3
        assert ev.side == "NYK"
        assert ev.points == 3
        assert ev.actor_id == "player_42"
        assert ev.detail is payload  # same object — no copy by default

    @pytest.mark.parametrize("kind", list(CanonicalEventKind))
    def test_all_kinds_constructible(self, kind: CanonicalEventKind) -> None:
        ev = CanonicalEvent(kind=kind, ts_game_sec=0.0, period=1)
        assert ev.kind is kind

    def test_detail_default_is_empty_dict(self) -> None:
        ev = CanonicalEvent(
            kind=CanonicalEventKind.OTHER,
            ts_game_sec=0.0,
            period=1,
        )
        assert ev.detail == {}
        assert isinstance(ev.detail, dict)

    def test_detail_default_independent_instances(self) -> None:
        """Each instance must get its own empty dict, not a shared default."""
        ev1 = CanonicalEvent(kind=CanonicalEventKind.OTHER, ts_game_sec=0.0, period=1)
        ev2 = CanonicalEvent(kind=CanonicalEventKind.OTHER, ts_game_sec=0.0, period=1)
        assert ev1.detail is not ev2.detail

    def test_ts_game_sec_accepts_float(self) -> None:
        ev = CanonicalEvent(
            kind=CanonicalEventKind.MISS,
            ts_game_sec=2879.99,
            period=4,
        )
        assert ev.ts_game_sec == pytest.approx(2879.99)

    def test_period_zero_allowed(self) -> None:
        """period=0 might be used for pre-game events; no validation at kernel level."""
        ev = CanonicalEvent(kind=CanonicalEventKind.STOPPAGE, ts_game_sec=0.0, period=0)
        assert ev.period == 0


# ===========================================================================
# 4. CanonicalEvent.detail — kernel must treat it as opaque
# ===========================================================================

class TestCanonicalEventDetailOpaque:
    def test_detail_roundtrips_arbitrary_keys(self) -> None:
        """Adapters can store arbitrary league-specific data in detail."""
        raw_payload: Dict[str, Any] = {
            "personId": 203954,
            "actionType": "2pt",
            "subType": "layup",
            "qualifiers": ["and1", "fastbreak"],
            "teamId": 1610612752,
            "xLegacy": 42,
            "yLegacy": -87,
        }
        ev = CanonicalEvent(
            kind=CanonicalEventKind.SCORE,
            ts_game_sec=45.0,
            period=1,
            detail=raw_payload,
        )
        # Kernel stores it unchanged — structural test only
        assert ev.detail["actionType"] == "2pt"
        assert len(ev.detail["qualifiers"]) == 2

    def test_detail_accepts_nested_dicts(self) -> None:
        nested: Dict[str, Any] = {"player": {"id": "p1", "name": "Brunson"}}
        ev = CanonicalEvent(
            kind=CanonicalEventKind.SUBSTITUTION,
            ts_game_sec=600.0,
            period=2,
            detail=nested,
        )
        assert ev.detail["player"]["name"] == "Brunson"


# ===========================================================================
# 5. PBPEventMapper — isinstance passes for ToyMapper
# ===========================================================================

class TestPBPEventMapperProtocol:
    def test_toy_mapper_is_pbp_event_mapper(self) -> None:
        mapper = ToyMapper()
        assert isinstance(mapper, PBPEventMapper), (
            "ToyMapper implements all PBPEventMapper methods but isinstance() returned False"
        )

    def test_to_canonical_returns_canonical_event(self) -> None:
        mapper = ToyMapper()
        raw = {"clock": 30.0, "period": 1, "team": "NYK", "pts": 2, "player_id": "p1"}
        ev = mapper.to_canonical(raw)
        assert isinstance(ev, CanonicalEvent)
        assert ev.kind is CanonicalEventKind.SCORE

    def test_iter_game_yields_canonical_events(self) -> None:
        mapper = ToyMapper()
        events = list(mapper.iter_game("0042500401"))
        assert len(events) == 1
        assert isinstance(events[0], CanonicalEvent)

    def test_possession_side_returns_str_or_none(self) -> None:
        mapper = ToyMapper()
        ev = CanonicalEvent(
            kind=CanonicalEventKind.SCORE, ts_game_sec=0.0, period=1, side="SAS"
        )
        result = mapper.possession_side(ev)
        assert result == "SAS" or result is None


# ===========================================================================
# 6. PBPEventMapper — isinstance fails when a method is missing
# ===========================================================================

class TestPBPEventMapperMissingMethod:
    def test_missing_to_canonical_fails(self) -> None:
        class BadMapper:
            # Missing to_canonical
            def iter_game(self, game_id: str) -> Iterator[CanonicalEvent]:
                return iter([])

            def possession_side(self, event: CanonicalEvent) -> Optional[str]:
                return None

        assert not isinstance(BadMapper(), PBPEventMapper)

    def test_missing_iter_game_fails(self) -> None:
        class BadMapper:
            def to_canonical(self, raw_event: Any) -> CanonicalEvent:
                return CanonicalEvent(
                    kind=CanonicalEventKind.OTHER, ts_game_sec=0.0, period=1
                )
            # Missing iter_game

            def possession_side(self, event: CanonicalEvent) -> Optional[str]:
                return None

        assert not isinstance(BadMapper(), PBPEventMapper)

    def test_missing_possession_side_fails(self) -> None:
        class BadMapper:
            def to_canonical(self, raw_event: Any) -> CanonicalEvent:
                return CanonicalEvent(
                    kind=CanonicalEventKind.OTHER, ts_game_sec=0.0, period=1
                )

            def iter_game(self, game_id: str) -> Iterator[CanonicalEvent]:
                return iter([])
            # Missing possession_side

        assert not isinstance(BadMapper(), PBPEventMapper)

    def test_empty_class_fails(self) -> None:
        class Empty:
            pass

        assert not isinstance(Empty(), PBPEventMapper)


# ===========================================================================
# 7. LeagueClient — isinstance passes for ToyClient
# ===========================================================================

class TestLeagueClientProtocol:
    def test_toy_client_is_league_client(self) -> None:
        client = ToyClient()
        assert isinstance(client, LeagueClient), (
            "ToyClient implements all LeagueClient methods but isinstance() returned False"
        )

    def test_get_schedule_returns_something(self) -> None:
        client = ToyClient()
        result = client.get_schedule("2025-26")
        assert result is not None

    def test_get_box_score_returns_something(self) -> None:
        client = ToyClient()
        result = client.get_box_score("0042500401")
        assert result is not None

    def test_get_pbp_returns_something(self) -> None:
        client = ToyClient()
        result = client.get_pbp("0042500401")
        assert result is not None

    def test_get_roster_returns_something(self) -> None:
        client = ToyClient()
        result = client.get_roster("1610612752", "2025-26")
        assert result is not None

    def test_get_player_gamelog_returns_something(self) -> None:
        client = ToyClient()
        result = client.get_player_gamelog("203954", "2025-26")
        assert result is not None

    def test_get_availability_returns_something(self) -> None:
        client = ToyClient()
        result = client.get_availability("203954", "0042500401")
        assert result is not None


# ===========================================================================
# 8. LeagueClient — isinstance fails when a method is missing
# ===========================================================================

class TestLeagueClientMissingMethod:
    def test_missing_get_schedule_fails(self) -> None:
        class BadClient:
            # Missing get_schedule
            def get_box_score(self, game_id: str) -> Any: return {}
            def get_pbp(self, game_id: str) -> Any: return []
            def get_roster(self, team_id: str, season: str) -> Any: return []
            def get_player_gamelog(self, player_id: str, season: str) -> Any: return []
            def get_availability(self, player_id: str, game_id: str) -> Any: return "active"

        assert not isinstance(BadClient(), LeagueClient)

    def test_missing_get_pbp_fails(self) -> None:
        class BadClient:
            def get_schedule(self, season: str) -> Any: return []
            def get_box_score(self, game_id: str) -> Any: return {}
            # Missing get_pbp
            def get_roster(self, team_id: str, season: str) -> Any: return []
            def get_player_gamelog(self, player_id: str, season: str) -> Any: return []
            def get_availability(self, player_id: str, game_id: str) -> Any: return "active"

        assert not isinstance(BadClient(), LeagueClient)

    def test_empty_class_fails(self) -> None:
        class Empty:
            pass

        assert not isinstance(Empty(), LeagueClient)


# ===========================================================================
# 9. ToyDualImpl — satisfies both protocols simultaneously
# ===========================================================================

class TestDualProtocolImpl:
    def test_dual_impl_is_pbp_event_mapper(self) -> None:
        obj = ToyDualImpl()
        assert isinstance(obj, PBPEventMapper)

    def test_dual_impl_is_league_client(self) -> None:
        obj = ToyDualImpl()
        assert isinstance(obj, LeagueClient)

    def test_dual_impl_satisfies_both(self) -> None:
        """Primary assertion: structural isinstance for both protocols."""
        obj = ToyDualImpl()
        assert isinstance(obj, PBPEventMapper) and isinstance(obj, LeagueClient), (
            "ToyDualImpl must satisfy both PBPEventMapper and LeagueClient protocols"
        )

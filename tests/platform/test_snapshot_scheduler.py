"""tests.platform.test_snapshot_scheduler — acceptance tests for the multi-sport
snapshot scheduler.

All tests are fully offline: a fake OddsFeed is injected; no network, no real
data/domains/ tree (all writes go to pytest's tmp_path).  Confirms:
* capture_once writes snapshots for every sport and returns a correct manifest.
* A feed that raises for one sport is logged+skipped; all other sports still captured.
* forward_clv_candidates pairs opener vs closer when >=2 snapshots exist; single-
  snapshot keys are excluded.
* honest_note present on all outputs; no edge-claim tokens anywhere.

Python 3.9 compatible.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional

import pytest

from scripts.platformkit.frontend.feed import GameOdds, OddsFeed, Quote
from scripts.platformkit.frontend.snapshot_scheduler import (
    SPORTS,
    capture_once,
    forward_clv_candidates,
)

# ------------------------------------------------------------------- helpers --

_EDGE_TOKENS = re.compile(
    r"\b(roi|beat the market|profit|edge claim|model edge)\b", re.IGNORECASE
)


def _no_edge_tokens(text: str) -> bool:
    """Return True if the string contains none of the forbidden edge-claim tokens."""
    return _EDGE_TOKENS.search(text) is None


def _make_quote(book: str = "dk", market: str = "h2h",
                side: str = "home", decimal_odds: float = 1.80,
                line: Optional[float] = None) -> Quote:
    return Quote(book=book, market=market, side=side,
                 decimal_odds=decimal_odds, line=line)


def _make_game(sport: str, game_id: Optional[str] = None,
               home_ml: float = 1.80, away_ml: float = 2.10) -> GameOdds:
    gid = game_id or f"{sport}:2026-06-14:away@home"
    return GameOdds(
        game_id=gid, sport=sport, home="home_team", away="away_team",
        commence_time="2026-06-14T20:00Z",
        quotes=[
            _make_quote("dk", "h2h", "home", home_ml),
            _make_quote("dk", "h2h", "away", away_ml),
            _make_quote("dk", "totals", "over", 1.9091, line=220.5),
        ],
        source="stub_test",
    )


class _StubFeed(OddsFeed):
    """Offline fake feed: returns fixed GameOdds regardless of sport."""

    name = "stub_test"

    def __init__(self, games: List[GameOdds]) -> None:
        self._games = games

    def is_live(self) -> bool:
        return False

    def fetch(self, sport: str, *, date: Optional[str] = None) -> List[GameOdds]:
        return [
            GameOdds(
                game_id=g.game_id.replace(g.sport, sport), sport=sport,
                home=g.home, away=g.away, commence_time=g.commence_time,
                quotes=list(g.quotes), source=g.source,
            )
            for g in self._games
        ]


class _ExplodingFeed(OddsFeed):
    """Feed that raises on fetch — used to test the per-sport error guard."""

    name = "exploding"

    def is_live(self) -> bool:
        return False

    def fetch(self, sport: str, *, date: Optional[str] = None) -> List[GameOdds]:
        raise RuntimeError(f"exploding feed raised for sport={sport}")


class _SelectiveFeed(OddsFeed):
    """Raises for one sport; returns a game for all others."""

    name = "selective"

    def __init__(self, boom_sport: str, games: List[GameOdds]) -> None:
        self._boom = boom_sport
        self._games = games

    def is_live(self) -> bool:
        return False

    def fetch(self, sport: str, *, date: Optional[str] = None) -> List[GameOdds]:
        if sport == self._boom:
            raise RuntimeError(f"selective explosion for {sport}")
        return [GameOdds(
            game_id=f"{sport}:2026-06-14:away@home", sport=sport,
            home="home_team", away="away_team",
            commence_time="2026-06-14T20:00Z",
            quotes=list(self._games[0].quotes) if self._games else [],
            source="stub_test",
        )]


# ==================================================================== tests ==

# ------------------------------------------------------------------ 1. basic capture

def test_capture_once_all_sports_manifest(tmp_path: Path) -> None:
    """capture_once writes snapshots for all 4 sports and returns correct counts."""
    feed = _StubFeed([_make_game("basketball_nba")])
    manifest = capture_once(sports=SPORTS, feed=feed, root=tmp_path,
                            ts_utc="2026-06-14T18:00:00+00:00")

    assert "ts" in manifest
    assert "sports" in manifest
    assert "total_rows" in manifest
    assert "honest_note" in manifest

    for sport in SPORTS:
        assert sport in manifest["sports"], f"missing sport: {sport}"

    for sport in SPORTS:
        assert manifest["sports"][sport]["rows"] == 3, (
            f"expected 3 rows for {sport}, got {manifest['sports'][sport]['rows']}"
        )

    assert manifest["total_rows"] == 4 * 3

    for sport in SPORTS:
        path = Path(manifest["sports"][sport]["path"])
        assert path.exists(), f"snapshot file missing for {sport}: {path}"
        assert "odds_snapshots" in str(path)

    assert not (tmp_path / "data" / "registry").exists()


def test_capture_once_honest_note_no_edge_tokens(tmp_path: Path) -> None:
    """honest_note present; no edge-claim tokens in manifest."""
    feed = _StubFeed([_make_game("basketball_nba")])
    manifest = capture_once(sports=SPORTS[:1], feed=feed, root=tmp_path,
                            ts_utc="2026-06-14T18:00:00+00:00")
    assert manifest["honest_note"], "honest_note must be non-empty"
    full_text = json.dumps(manifest)
    assert _no_edge_tokens(full_text), f"edge-claim token found in manifest: {full_text[:300]}"


# ------------------------------------------------------------------ 2. error resilience

def test_capture_once_one_sport_explodes_others_succeed(tmp_path: Path) -> None:
    """A feed that raises for one sport must not abort the others."""
    boom_sport = SPORTS[1]  # mlb_sbro
    feed = _SelectiveFeed(boom_sport=boom_sport, games=[_make_game("basketball_nba")])
    manifest = capture_once(sports=SPORTS, feed=feed, root=tmp_path,
                            ts_utc="2026-06-14T19:00:00+00:00")

    assert boom_sport in manifest["sports"]
    assert manifest["sports"][boom_sport]["rows"] == 0

    for sport in SPORTS:
        if sport == boom_sport:
            continue
        entry = manifest["sports"][sport]
        assert entry["rows"] > 0, (
            f"sport={sport} should have rows>0 after partial failure; got {entry}"
        )


def test_capture_once_all_sports_explode_returns_manifest(tmp_path: Path) -> None:
    """Even when every sport's feed raises, capture_once returns a manifest (no crash)."""
    manifest = capture_once(sports=SPORTS, feed=_ExplodingFeed(), root=tmp_path,
                            ts_utc="2026-06-14T20:00:00+00:00")
    assert manifest["total_rows"] == 0
    for sport in SPORTS:
        assert manifest["sports"][sport]["rows"] == 0


# ------------------------------------------------------------------ 3. forward CLV candidates

def test_forward_clv_candidates_two_snapshots_produces_candidate(tmp_path: Path) -> None:
    """Two captures at different ts -> one opener/closer candidate per (game,book,market,side)."""
    sport = "basketball_nba"
    feed1 = _StubFeed([_make_game(sport, home_ml=1.80, away_ml=2.10)])
    feed2 = _StubFeed([_make_game(sport, home_ml=1.75, away_ml=2.20)])  # lines moved

    capture_once(sports=[sport], feed=feed1, root=tmp_path,
                 ts_utc="2026-06-14T18:00:00+00:00")
    capture_once(sports=[sport], feed=feed2, root=tmp_path,
                 ts_utc="2026-06-14T20:00:00+00:00")

    result = forward_clv_candidates(sport, root=tmp_path)
    assert result["sport"] == sport
    assert result["n_candidates"] > 0
    assert "honest_note" in result

    candidates = result["candidates"]
    home_cand = next(
        (c for c in candidates
         if c["market"] == "h2h" and c["side"] == "home" and c["book"] == "dk"),
        None,
    )
    assert home_cand is not None, "expected a home h2h candidate"
    assert home_cand["opener_ts"] == "2026-06-14T18:00:00+00:00"
    assert home_cand["closer_ts"] == "2026-06-14T20:00:00+00:00"
    assert home_cand["opener_odds"] == pytest.approx(1.80)
    assert home_cand["closer_odds"] == pytest.approx(1.75)
    assert home_cand["n_snapshots"] == 2

    away_cand = next(
        (c for c in candidates
         if c["market"] == "h2h" and c["side"] == "away" and c["book"] == "dk"),
        None,
    )
    assert away_cand is not None
    assert away_cand["opener_odds"] == pytest.approx(2.10)
    assert away_cand["closer_odds"] == pytest.approx(2.20)


def test_forward_clv_candidates_single_snapshot_yields_no_candidate(tmp_path: Path) -> None:
    """One snapshot only -> no candidates (opener==closer is not useful)."""
    sport = "soccer_fd"
    feed = _StubFeed([_make_game(sport)])
    capture_once(sports=[sport], feed=feed, root=tmp_path,
                 ts_utc="2026-06-14T18:00:00+00:00")
    result = forward_clv_candidates(sport, root=tmp_path)
    assert result["n_candidates"] == 0
    assert result["candidates"] == []


def test_forward_clv_candidates_absent_sport_no_crash(tmp_path: Path) -> None:
    """Missing snapshots file -> empty result, no crash."""
    result = forward_clv_candidates("tennis_atp", root=tmp_path)
    assert result["n_candidates"] == 0
    assert result["candidates"] == []
    assert "honest_note" in result


def test_forward_clv_candidates_no_edge_tokens(tmp_path: Path) -> None:
    """honest_note and candidates contain no forbidden edge-claim tokens."""
    sport = "mlb_sbro"
    feed = _StubFeed([_make_game(sport)])
    capture_once(sports=[sport], feed=feed, root=tmp_path,
                 ts_utc="2026-06-14T17:00:00+00:00")
    capture_once(sports=[sport], feed=feed, root=tmp_path,
                 ts_utc="2026-06-14T19:00:00+00:00")
    result = forward_clv_candidates(sport, root=tmp_path)
    full_text = json.dumps(result)
    assert _no_edge_tokens(full_text), (
        f"edge-claim token found in CLV candidates: {full_text[:300]}"
    )


# ------------------------------------------------------------------ 4. path / registry guard

def test_capture_never_writes_registry(tmp_path: Path) -> None:
    """capture_once must NEVER write to data/registry/."""
    feed = _StubFeed([_make_game("basketball_nba")])
    capture_once(sports=["basketball_nba"], feed=feed, root=tmp_path,
                 ts_utc="2026-06-14T21:00:00+00:00")
    assert not (tmp_path / "data" / "registry").exists()


# ------------------------------------------------------------------ 5. capture with sport filter

def test_capture_once_single_sport_arg(tmp_path: Path) -> None:
    """capture_once with sports=['basketball_nba'] only writes that sport."""
    feed = _StubFeed([_make_game("basketball_nba")])
    manifest = capture_once(sports=["basketball_nba"], feed=feed, root=tmp_path,
                            ts_utc="2026-06-14T22:00:00+00:00")
    assert "basketball_nba" in manifest["sports"]
    assert manifest["sports"]["basketball_nba"]["rows"] > 0
    # Other sports not in the sports arg must not appear in manifest
    assert "mlb_sbro" not in manifest["sports"]


# ------------------------------------------------------------------ 6. line-movement CLI dispatch

def test_line_movement_cli_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """'line-movement <sport>' CLI command returns valid JSON with honest_note."""
    import sys
    from scripts.platformkit.frontend import snapshot_scheduler

    sport = "basketball_nba"
    feed = _StubFeed([_make_game(sport, home_ml=1.85, away_ml=2.05)])
    # Write two snapshots at different times so line_movement has records
    capture_once(sports=[sport], feed=feed, root=tmp_path, ts_utc="2026-06-14T12:00:00+00:00")
    feed2 = _StubFeed([_make_game(sport, home_ml=1.80, away_ml=2.10)])
    capture_once(sports=[sport], feed=feed2, root=tmp_path, ts_utc="2026-06-14T14:00:00+00:00")

    # Monkeypatch _repo_root so line_movement reads from tmp_path
    import scripts.platformkit.frontend.odds_snapshot as os_mod
    monkeypatch.setattr(os_mod, "_repo_root", lambda: tmp_path)

    output_lines: list = []
    monkeypatch.setattr("builtins.print", lambda *a, **k: output_lines.append(" ".join(str(x) for x in a)))

    rc = snapshot_scheduler._main(["line-movement", sport])
    assert rc == 0

    # Collect printed JSON (skip the banner lines)
    json_text = "\n".join(l for l in output_lines if l.strip().startswith("{"))
    result = json.loads(json_text)
    assert result["sport"] == sport
    assert "movements" in result
    assert "honest_note" in result

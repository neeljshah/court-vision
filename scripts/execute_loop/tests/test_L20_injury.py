"""test_L20_injury.py — Tests for L20_injury_feed.py

Nine tests using mocked requests and tmp_path; no live network calls.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# -- path setup ----------------------------------------------------------------
_TEST_DIR    = Path(__file__).resolve().parent
_LOOP_DIR    = _TEST_DIR.parent
_PROJECT_DIR = _LOOP_DIR.parents[1]
sys.path.insert(0, str(_PROJECT_DIR))
sys.path.insert(0, str(_LOOP_DIR))

import L20_injury_feed as L20  # noqa: E402

# ── HTML fixture ──────────────────────────────────────────────────────────────
_RW_HTML_FIXTURE = """
<!DOCTYPE html>
<html>
<body>
<table id="injury-report">
  <tbody>
    <tr>
      <td>LeBron James</td>
      <td>LAL</td>
      <td>Out</td>
      <td>Knee soreness — day-to-day evaluation ongoing</td>
    </tr>
    <tr>
      <td>Stephen Curry</td>
      <td>GSW</td>
      <td>Questionable</td>
      <td>Left ankle sprain, listed as questionable for tonight</td>
    </tr>
    <tr>
      <td>Joel Embiid</td>
      <td>PHI</td>
      <td>Doubtful</td>
      <td>Knee swelling — doubtful to play</td>
    </tr>
  </tbody>
</table>
</body>
</html>
"""


def _make_mock_response(text: str = "", status: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status
    mock.text = text
    mock.raise_for_status = MagicMock()
    if status >= 400:
        import requests
        mock.raise_for_status.side_effect = requests.HTTPError(response=mock)
    return mock


# ── test 1: fetch_rotowire_injuries parses HTML fixture ───────────────────────
def test_fetch_rotowire_injuries_parses_html():
    """fetch_rotowire_injuries with HTML fixture returns ≥1 InjuryUpdate
    containing status='OUT' and severity='critical' for LeBron James."""
    mock_resp = _make_mock_response(_RW_HTML_FIXTURE, 200)

    with patch("L20_injury_feed.requests.get", return_value=mock_resp):
        updates = L20.fetch_rotowire_injuries()

    assert len(updates) >= 1, "Should return at least one update"

    # verify LeBron OUT → critical
    lebron = next(
        (u for u in updates if "lebron" in u.player.lower()),
        None,
    )
    assert lebron is not None, "LeBron James should appear in results"
    assert lebron.status == "OUT"
    assert lebron.severity == "critical"
    assert lebron.source == "rotowire"
    assert lebron.team == "LAL"

    # verify Curry QUESTIONABLE → warning
    curry = next(
        (u for u in updates if "curry" in u.player.lower()),
        None,
    )
    assert curry is not None
    assert curry.status == "QUESTIONABLE"
    assert curry.severity == "warning"

    # verify Embiid DOUBTFUL → critical
    embiid = next(
        (u for u in updates if "embiid" in u.player.lower()),
        None,
    )
    assert embiid is not None
    assert embiid.status == "DOUBTFUL"
    assert embiid.severity == "critical"


# ── test 2: run_all_sources merges and dedups across sources ──────────────────
def test_run_all_sources_merges_and_dedups():
    """run_all_sources merges results from multiple sources and deduplicates
    same player+date entries, keeping the highest severity."""
    # Official source returns LeBron OUT (critical)
    official_upd = L20.InjuryUpdate(
        player="lebron james", team="LAL", status="OUT",
        source="nba_official", body="Knee",
        timestamp="2026-05-25T12:00:00+00:00", severity="critical",
    )
    official_upd._hash = official_upd.compute_hash()

    # RotoWire returns same LeBron as DOUBTFUL (also critical) + Curry QUESTIONABLE
    rw_lebron = L20.InjuryUpdate(
        player="lebron james", team="LAL", status="DOUBTFUL",
        source="rotowire", body="Knee — doubtful",
        timestamp="2026-05-25T13:00:00+00:00", severity="critical",
    )
    rw_lebron._hash = rw_lebron.compute_hash()

    curry_upd = L20.InjuryUpdate(
        player="stephen curry", team="GSW", status="QUESTIONABLE",
        source="rotowire", body="Ankle",
        timestamp="2026-05-25T12:00:00+00:00", severity="warning",
    )
    curry_upd._hash = curry_upd.compute_hash()

    with (
        patch.object(L20, "fetch_nba_official_injuries", return_value=[official_upd]),
        patch.object(L20, "fetch_rotowire_injuries",     return_value=[rw_lebron, curry_upd]),
        patch.object(L20, "fetch_underdog_lineup_news",  return_value=[]),
    ):
        results = L20.run_all_sources()

    players = [u.player for u in results]
    # LeBron should appear exactly once after merge
    lebron_count = sum(1 for p in players if "lebron" in p.lower())
    assert lebron_count == 1, f"LeBron should be deduped to 1 entry, got {lebron_count}"

    # Curry should still appear
    assert any("curry" in p.lower() for p in players)
    assert len(results) == 2


# ── test 3: diff_against_seen deduplication across calls ─────────────────────
def test_diff_against_seen_first_call_returns_all_second_returns_zero(tmp_path):
    """First call to diff_against_seen returns all N updates;
    second call with same updates returns 0 (all already seen)."""
    seen_file = tmp_path / "injury_seen.json"

    updates = [
        L20.InjuryUpdate(
            player="giannis antetokounmpo", team="MIL", status="OUT",
            source="nba_official", body="Knee",
            timestamp="2026-05-25T10:00:00+00:00", severity="critical",
        ),
        L20.InjuryUpdate(
            player="luka doncic", team="DAL", status="GTD",
            source="rotowire", body="Ankle",
            timestamp="2026-05-25T10:00:00+00:00", severity="warning",
        ),
    ]
    for u in updates:
        u._hash = u.compute_hash()

    with patch.object(L20, "_SEEN_PATH", seen_file):
        first  = L20.diff_against_seen(updates)
        second = L20.diff_against_seen(updates)

    assert len(first)  == 2, f"Expected 2 on first call, got {len(first)}"
    assert len(second) == 0, f"Expected 0 on second call, got {len(second)}"


# ── test 4: Q/GTD → OUT downgrade triggers critical ──────────────────────────
def test_downgrade_q_to_out_forces_critical(tmp_path):
    """When a player was previously QUESTIONABLE and is now OUT,
    severity must be 'critical' even if the OUT hash was already seen."""
    seen_file = tmp_path / "injury_seen.json"

    # Seed _seen.json with the OUT hash already present + prior status = QUESTIONABLE
    player_norm = "kevin durant"
    date_str    = "2026-05-25"
    out_raw     = f"{player_norm}|OUT|{date_str}"
    out_hash    = __import__("hashlib").sha1(out_raw.encode()).hexdigest()

    q_raw   = f"{player_norm}|QUESTIONABLE|{date_str}"
    q_hash  = __import__("hashlib").sha1(q_raw.encode()).hexdigest()

    pre_seen = {
        out_hash: {"status": "OUT",          "last_seen_iso": "2026-05-24T09:00:00", "player_norm": player_norm},
        q_hash:   {"status": "QUESTIONABLE", "last_seen_iso": "2026-05-24T08:00:00", "player_norm": player_norm},
    }
    seen_file.write_text(json.dumps(pre_seen), encoding="utf-8")

    # New update: Kevin Durant OUT — hash is already in seen, but prior was Q
    upd = L20.InjuryUpdate(
        player="Kevin Durant", team="PHX", status="OUT",
        source="rotowire", body="Ankle — ruled out",
        timestamp=f"{date_str}T15:00:00+00:00", severity="info",  # starts as info
    )
    upd._hash = upd.compute_hash()

    with patch.object(L20, "_SEEN_PATH", seen_file):
        novel = L20.diff_against_seen([upd])

    # Should be returned and upgraded to critical despite hash being seen
    assert len(novel) == 1, "Downgrade must surface even if hash was seen"
    assert novel[0].severity == "critical", (
        f"Expected critical for downgrade, got {novel[0].severity}"
    )


# ── test 5: alert_on_critical calls send_alert twice for 2 critical updates ──
def test_alert_on_critical_calls_send_alert_for_each_critical():
    """alert_on_critical with 2 critical updates calls send_alert twice
    with channel='news'."""
    critical_updates = [
        L20.InjuryUpdate(
            player="jayson tatum", team="BOS", status="OUT",
            source="nba_official", body="Knee — ruled out",
            timestamp="2026-05-25T14:00:00+00:00", severity="critical",
        ),
        L20.InjuryUpdate(
            player="nikola jokic", team="DEN", status="DOUBTFUL",
            source="rotowire", body="Wrist soreness",
            timestamp="2026-05-25T14:00:00+00:00", severity="critical",
        ),
    ]

    mock_send = MagicMock(return_value=True)

    with patch.object(L20, "_send_alert", mock_send):
        count = L20.alert_on_critical(critical_updates)

    assert count == 2
    assert mock_send.call_count == 2

    # verify both calls used channel='news'
    for call_args in mock_send.call_args_list:
        args, kwargs = call_args
        channel = args[0] if args else kwargs.get("channel")
        assert channel == "news", f"Expected channel='news', got {channel!r}"


# ── helpers for L46 tests ─────────────────────────────────────────────────────

def _get_bus():
    """Return the L46 default bus, or None if L46 is unavailable."""
    if L20._L46 is None:
        return None
    return L20._L46.get_default_bus()


def _make_injury(player, team, status, ts="2026-05-25T10:00:00+00:00", source="nba_official"):
    upd = L20.InjuryUpdate(
        player=player, team=team, status=status,
        source=source, body="Test reason",
        timestamp=ts,
        severity=L20._STATUS_TO_SEVERITY.get(status, "info"),
    )
    upd._hash = upd.compute_hash()
    return upd


# ── test 6: new injury publishes event; pre-existing one does not ──────────────
def test_new_injury_publishes_event(tmp_path):
    """diff_against_seen publishes 'injury.announced' for new injuries only.

    A pre-existing record (already in _seen.json with matching hash) must NOT
    produce a second event.  A brand-new record must produce exactly one event
    with the correct schema.
    """
    bus = _get_bus()
    if bus is None:
        pytest.skip("L46_event_bus not available in this environment")

    bus.clear_subscribers()

    seen_file = tmp_path / "injury_seen.json"

    # Seed: Anthony Davis is already cached (no event expected)
    ad = _make_injury("Anthony Davis", "LAL", "OUT", ts="2026-05-25T08:00:00+00:00")
    existing_seen = {
        ad._hash: {
            "status": "OUT",
            "last_seen_iso": "2026-05-25T08:00:00",
            "player_norm": "anthony davis",
        }
    }
    seen_file.write_text(json.dumps(existing_seen), encoding="utf-8")

    # New injury: Damian Lillard not in cache yet
    dame = _make_injury("Damian Lillard", "MIL", "QUESTIONABLE", ts="2026-05-25T10:00:00+00:00")

    received: list = []
    bus.subscribe("injury.announced", lambda evt: received.append(evt), layer="test")

    with patch.object(L20, "_SEEN_PATH", seen_file):
        novel = L20.diff_against_seen([ad, dame])

    # Only Lillard is novel
    assert len(novel) == 1
    assert "lillard" in novel[0].player.lower()

    # Exactly one event published (not two)
    assert len(received) == 1, f"Expected 1 event, got {len(received)}"

    evt = received[0]
    assert evt.name == "injury.announced"
    assert evt.source == "L20"
    payload = evt.payload
    assert "lillard" in payload["player"].lower()
    assert payload["team"] == "MIL"
    assert payload["status"] == "QUESTIONABLE"
    assert payload["previously_known"] is None   # first-ever appearance
    assert "fetched_at" in payload
    assert "reason" in payload

    bus.clear_subscribers()


# ── test 7: no new injuries → no events published ────────────────────────────
def test_no_new_injuries_publishes_nothing(tmp_path):
    """When all injuries are already in the cache, zero events are published."""
    bus = _get_bus()
    if bus is None:
        pytest.skip("L46_event_bus not available in this environment")

    bus.clear_subscribers()

    seen_file = tmp_path / "injury_seen.json"

    upd = _make_injury("Jaylen Brown", "BOS", "GTD", ts="2026-05-25T10:00:00+00:00")
    pre_seen = {
        upd._hash: {
            "status": "GTD",
            "last_seen_iso": "2026-05-25T09:00:00",
            "player_norm": "jaylen brown",
        }
    }
    seen_file.write_text(json.dumps(pre_seen), encoding="utf-8")

    received: list = []
    bus.subscribe("injury.announced", lambda evt: received.append(evt), layer="test")

    with patch.object(L20, "_SEEN_PATH", seen_file):
        novel = L20.diff_against_seen([upd])

    assert len(novel) == 0, "Same data → no novel updates"
    assert len(received) == 0, "Same data → no events published"

    bus.clear_subscribers()


# ── test 8: atomic write leaves valid JSON even on concurrent reads ────────────
def test_atomic_write_json_produces_valid_file(tmp_path):
    """_atomic_write_json creates a valid JSON file that can be re-read."""
    target = tmp_path / "sub" / "test_atomic.json"
    data = {"key": "value", "count": 42, "nested": {"a": 1}}

    L20._atomic_write_json(target, data)

    assert target.exists(), "Target file should exist after atomic write"
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded == data, f"Round-trip mismatch: {loaded}"

    # Overwrite with new data — must replace cleanly
    data2 = {"key": "updated", "count": 99}
    L20._atomic_write_json(target, data2)
    loaded2 = json.loads(target.read_text(encoding="utf-8"))
    assert loaded2 == data2

    # No leftover .tmp files
    tmp_files = list(tmp_path.rglob("*.tmp"))
    assert tmp_files == [], f"Leftover temp files: {tmp_files}"


# ── test 9: publish failure does not break fetch pipeline ────────────────────
def test_publish_failure_does_not_break_fetch(tmp_path):
    """If the EventBus publish call raises, diff_against_seen still returns
    the novel updates and saves _seen.json correctly."""
    seen_file = tmp_path / "injury_seen.json"

    upd = _make_injury("Trae Young", "ATL", "OUT", ts="2026-05-25T10:00:00+00:00")

    # Patch _L46 with a mock whose publish() raises
    broken_bus = MagicMock()
    broken_bus.publish.side_effect = RuntimeError("bus exploded")

    broken_L46 = MagicMock()
    broken_L46.get_default_bus.return_value = broken_bus

    with (
        patch.object(L20, "_SEEN_PATH", seen_file),
        patch.object(L20, "_L46", broken_L46),
    ):
        novel = L20.diff_against_seen([upd])  # must not raise

    # Novel updates are still returned despite publish failure
    assert len(novel) == 1, "Novel update must be returned even when publish fails"
    assert "trae" in novel[0].player.lower()

    # _seen.json must have been written correctly
    assert seen_file.exists(), "_seen.json must be persisted even when publish fails"
    persisted = json.loads(seen_file.read_text(encoding="utf-8"))
    assert len(persisted) == 1, "Exactly one hash should be in _seen.json"

"""Unit tests for PolymarketReader — no network required."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from venues.polymarket_reader import BASE_URL, PolymarketReader


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


def test_list_markets_returns_list() -> None:
    """list_markets parses {'data': [...]} and returns the list."""
    payload = {"data": [{"condition_id": "ABC"}]}
    with patch("requests.Session.get", return_value=_mock_response(payload)) as mock_get:
        reader = PolymarketReader()
        result = reader.list_markets()
    assert result == [{"condition_id": "ABC"}]


def test_list_markets_missing_key_returns_empty() -> None:
    """Returns [] when 'data' key absent."""
    with patch("requests.Session.get", return_value=_mock_response({})):
        reader = PolymarketReader()
        result = reader.list_markets()
    assert result == []


def test_get_orderbook_returns_dict() -> None:
    """get_orderbook returns the full response dict."""
    payload = {"bids": [], "asks": []}
    with patch("requests.Session.get", return_value=_mock_response(payload)):
        reader = PolymarketReader()
        result = reader.get_orderbook("tok123")
    assert result == {"bids": [], "asks": []}


def test_list_markets_with_cursor() -> None:
    """list_markets passes next_cursor as query param when non-empty."""
    payload = {"data": []}
    with patch("requests.Session.get", return_value=_mock_response(payload)) as mock_get:
        reader = PolymarketReader()
        reader.list_markets(next_cursor="TOKEN")
    call_kwargs = mock_get.call_args
    params = call_kwargs.kwargs.get("params", {})
    assert params.get("next_cursor") == "TOKEN"

"""Unit tests for KalshiReader — no network required."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from venues.kalshi_reader import KalshiReader


def _make_mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


def test_list_markets_returns_list() -> None:
    """list_markets parses {'markets': [...]} and returns the list."""
    mock_resp = _make_mock_response({"markets": [{"ticker": "FOO"}]})
    session = MagicMock()
    session.get.return_value = mock_resp

    reader = KalshiReader(session=session)
    result = reader.list_markets()

    assert result == [{"ticker": "FOO"}]


def test_list_markets_missing_key_returns_empty() -> None:
    """list_markets returns [] if 'markets' key absent."""
    mock_resp = _make_mock_response({})
    session = MagicMock()
    session.get.return_value = mock_resp

    reader = KalshiReader(session=session)
    result = reader.list_markets()

    assert result == []


def test_get_orderbook_returns_dict() -> None:
    """get_orderbook parses {'orderbook': {...}} and returns the inner dict."""
    inner = {"yes": [], "no": []}
    mock_resp = _make_mock_response({"orderbook": inner})
    session = MagicMock()
    session.get.return_value = mock_resp

    reader = KalshiReader(session=session)
    result = reader.get_orderbook("FOO-BAR")

    assert result == {"yes": [], "no": []}


def test_get_orderbook_fallback_returns_raw() -> None:
    """get_orderbook returns raw response dict if 'orderbook' key absent."""
    raw = {"foo": "bar"}
    mock_resp = _make_mock_response(raw)
    session = MagicMock()
    session.get.return_value = mock_resp

    reader = KalshiReader(session=session)
    result = reader.get_orderbook("FOO-BAR")

    assert result == {"foo": "bar"}

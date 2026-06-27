"""Smoke test for predict_service.run -- the thin CLI dispatcher.

Verifies:
  * The parser wires each subcommand (produce-once, serve, loop) and their flags.
  * `produce-once` dispatches to a stubbed produce.produce_once + store.read_latest.
  * `serve` dispatches to a stubbed uvicorn.run (no real port binding).
  * `loop` dispatches to a stubbed scheduler.serve_forever (no real looping).
  * --sport / --interval / --out-dir flags are plumbed through correctly.
  * No real network, no port binding, no corpus access.

Per-file run only:
    python -m pytest tests/predict_service/test_run.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from predict_service import run as run_module
from predict_service.run import _build_parser, main


# --------------------------------------------------------------------------- #
# Parser wiring                                                                #
# --------------------------------------------------------------------------- #

class TestParserWiring:
    """The parser builds without error and wires each subcommand's flags."""

    def test_parser_builds(self):
        ap = _build_parser()
        assert ap is not None

    def test_produce_once_defaults(self):
        ap = _build_parser()
        args = ap.parse_args(["produce-once"])
        assert args.subcommand == "produce-once"
        assert args.sport == "nba"
        assert args.out_dir is None
        assert callable(args.func)

    def test_produce_once_sport_flag(self):
        ap = _build_parser()
        args = ap.parse_args(["produce-once", "--sport", "mlb"])
        assert args.sport == "mlb"

    def test_produce_once_out_dir_flag(self):
        ap = _build_parser()
        args = ap.parse_args(["produce-once", "--out-dir", "/tmp/x"])
        assert args.out_dir == "/tmp/x"

    def test_serve_subcommand(self):
        ap = _build_parser()
        args = ap.parse_args(["serve"])
        assert args.subcommand == "serve"
        assert callable(args.func)

    def test_loop_defaults(self):
        ap = _build_parser()
        args = ap.parse_args(["loop"])
        assert args.subcommand == "loop"
        assert args.interval == 1200
        assert args.out_dir is None
        assert callable(args.func)

    def test_loop_interval_flag(self):
        ap = _build_parser()
        args = ap.parse_args(["loop", "--interval", "600"])
        assert args.interval == 600

    def test_loop_out_dir_flag(self):
        ap = _build_parser()
        args = ap.parse_args(["loop", "--out-dir", "/tmp/store"])
        assert args.out_dir == "/tmp/store"

    def test_no_subcommand_exits(self):
        ap = _build_parser()
        with pytest.raises(SystemExit):
            ap.parse_args([])

    def test_unknown_subcommand_exits(self):
        ap = _build_parser()
        with pytest.raises(SystemExit):
            ap.parse_args(["notacommand"])


# --------------------------------------------------------------------------- #
# produce-once dispatch                                                        #
# --------------------------------------------------------------------------- #

class TestProduceOnceDispatch:
    """produce-once calls produce.produce_once and store.read_latest."""

    def _fake_env(self):
        env = MagicMock()
        env.status = "ok"
        env.predictions = [MagicMock()]
        env.edges = [MagicMock(), MagicMock()]
        return env

    def test_produce_once_dispatches(self, tmp_path, capsys):
        fake_path = str(tmp_path / "nba" / "latest.json")
        fake_env = self._fake_env()
        with patch("predict_service.produce.produce_once",
                   return_value=fake_path) as mock_produce, \
             patch("predict_service.store.read_latest",
                   return_value=fake_env) as mock_read:
            rc = main(["produce-once"])
        assert rc == 0
        mock_produce.assert_called_once_with("nba", out_dir=None)
        mock_read.assert_called_once_with("nba", out_dir=None)
        out = capsys.readouterr().out
        assert "sport=nba" in out
        assert "status=ok" in out
        assert "saved=" in out

    def test_produce_once_custom_sport(self, tmp_path, capsys):
        fake_env = self._fake_env()
        with patch("predict_service.produce.produce_once",
                   return_value="/some/path") as mock_produce, \
             patch("predict_service.store.read_latest", return_value=fake_env):
            rc = main(["produce-once", "--sport", "soccer"])
        assert rc == 0
        mock_produce.assert_called_once_with("soccer", out_dir=None)

    def test_produce_once_out_dir(self, tmp_path, capsys):
        fake_env = self._fake_env()
        with patch("predict_service.produce.produce_once",
                   return_value="/p") as mock_produce, \
             patch("predict_service.store.read_latest", return_value=fake_env):
            rc = main(["produce-once", "--out-dir", str(tmp_path)])
        mock_produce.assert_called_once_with("nba", out_dir=str(tmp_path))
        assert rc == 0

    def test_produce_once_returns_1_on_error(self, capsys):
        with patch("predict_service.produce.produce_once",
                   side_effect=RuntimeError("boom")):
            rc = main(["produce-once"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "ERROR" in err


# --------------------------------------------------------------------------- #
# serve dispatch                                                               #
# --------------------------------------------------------------------------- #

class TestServeDispatch:
    """serve calls uvicorn.run with the correct app and env-derived port/host."""

    def test_serve_dispatches(self, monkeypatch):
        monkeypatch.setenv("PREDICT_SERVICE_PORT", "9111")
        monkeypatch.setenv("PREDICT_SERVICE_HOST", "0.0.0.0")
        mock_uvicorn = MagicMock()
        mock_app = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}), \
             patch("predict_service.app.app", mock_app):
            rc = main(["serve"])
        assert rc == 0
        mock_uvicorn.run.assert_called_once()
        _, kwargs = mock_uvicorn.run.call_args
        assert kwargs["port"] == 9111
        assert kwargs["host"] == "0.0.0.0"

    def test_serve_default_port(self, monkeypatch):
        monkeypatch.delenv("PREDICT_SERVICE_PORT", raising=False)
        monkeypatch.delenv("PREDICT_SERVICE_HOST", raising=False)
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}), \
             patch("predict_service.app.app", MagicMock()):
            rc = main(["serve"])
        assert rc == 0
        _, kwargs = mock_uvicorn.run.call_args
        assert kwargs["port"] == 8099
        assert kwargs["host"] == "127.0.0.1"

    def test_serve_missing_uvicorn_returns_1(self, capsys):
        with patch.dict("sys.modules", {"uvicorn": None}):
            # Force ImportError path by making import raise
            import builtins
            real_import = builtins.__import__

            def _fake_import(name, *args, **kwargs):
                if name == "uvicorn":
                    raise ImportError("no uvicorn")
                return real_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=_fake_import):
                rc = main(["serve"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "uvicorn" in err.lower() or "ERROR" in err


# --------------------------------------------------------------------------- #
# loop dispatch                                                                #
# --------------------------------------------------------------------------- #

class TestLoopDispatch:
    """loop calls scheduler.serve_forever with the correct interval."""

    def test_loop_dispatches(self):
        with patch("predict_service.scheduler.serve_forever") as mock_sched:
            rc = main(["loop"])
        assert rc == 0
        mock_sched.assert_called_once()
        _, kwargs = mock_sched.call_args
        assert kwargs["interval"] == 1200

    def test_loop_custom_interval(self):
        with patch("predict_service.scheduler.serve_forever") as mock_sched:
            rc = main(["loop", "--interval", "300"])
        assert rc == 0
        _, kwargs = mock_sched.call_args
        assert kwargs["interval"] == 300

    def test_loop_out_dir(self, tmp_path):
        with patch("predict_service.scheduler.serve_forever") as mock_sched:
            rc = main(["loop", "--out-dir", str(tmp_path)])
        assert rc == 0
        _, kwargs = mock_sched.call_args
        assert kwargs["out_dir"] == str(tmp_path)

    def test_loop_keyboard_interrupt_is_clean(self):
        """KeyboardInterrupt from serve_forever should not propagate; rc == 0."""
        with patch("predict_service.scheduler.serve_forever",
                   side_effect=KeyboardInterrupt):
            rc = main(["loop"])
        assert rc == 0

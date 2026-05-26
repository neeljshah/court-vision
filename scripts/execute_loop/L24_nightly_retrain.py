"""L24_nightly_retrain.py — Nightly model retrain cron (BUILD L24).

Runs the prop_pergame walk-forward, gates the candidate on 4/4 WF folds +
single-split MAE improvement, then either promotes live or submits to the
L25 shadow harness for 50-game observation.

Public API
----------
    run_nightly(via_shadow=True, dry_run=False) -> RetrainRun
    compute_production_metrics() -> dict[str, float]
    run_walk_forward_candidate() -> dict[str, float]
    check_promotion_gate(candidate, prod) -> tuple[bool, bool, bool]
    deploy_candidate(via_shadow=True) -> bool

CLI
---
    python L24_nightly_retrain.py run
    python L24_nightly_retrain.py dry-run
    python L24_nightly_retrain.py status
    python L24_nightly_retrain.py rollback --to <run_id>

Paper vs Live Mode (MODE GATING)
---------------------------------
    Default deploy path is always ``via_shadow=True`` (paper/shadow observation
    via L25 for 50 games) unless the caller explicitly passes ``via_shadow=False``.
    Live copy to the production WF JSON requires RETRAIN_DEPLOY_TOKEN to be set;
    without the token the live branch is a no-op. Never default to live.

Environment Variables
---------------------
    RETRAIN_DEPLOY_TOKEN  Token required to authorise a direct live deploy
                          (via_shadow=False path). If unset, live deploy is
                          aborted and deploy_mode remains "none".
"""
from __future__ import annotations

import argparse
import errno
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SCRIPT_DIR  = Path(__file__).resolve().parent
_PROJECT_DIR = _SCRIPT_DIR.parent.parent
_MODELS_DIR  = _PROJECT_DIR / "data" / "models"
_LEDGER_DIR  = _PROJECT_DIR / "data" / "ledger"
_HISTORY_PATH = _LEDGER_DIR / "retrain_history.json"
_LOCK_PATH    = _PROJECT_DIR / "data" / ".retrain_lock"
_WF_OUT_PATH  = _MODELS_DIR / "prop_pergame_walk_forward.json"
_WF_SCRIPT    = _PROJECT_DIR / "scripts" / "prop_pergame_walk_forward.py"

# Hardcoded baseline MAE (fallback when WF JSON is malformed)
_BASELINE_MAE: dict[str, float] = {
    "pts":  4.621,
    "reb":  1.902,
    "ast":  1.356,
    "fg3m": 0.894,
    "stl":  0.715,
    "blk":  0.440,
    "tov":  0.893,
}

_STATS = list(_BASELINE_MAE.keys())

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class RetrainRun:
    run_id:            str
    started_at:        str
    finished_at:       Optional[str] = None
    prod_mae_before:   dict = field(default_factory=dict)
    candidate_mae:     dict = field(default_factory=dict)
    wf_4_of_4:         bool = False
    single_split_better: bool = False
    gate_pass:         bool = False
    deployed:          bool = False
    deploy_mode:       str  = "none"   # "shadow" | "live" | "none"
    status:            str  = "ok"     # ok | no_new_data | locked | wf_failed | gate_warn | error
    summary_notes:     str  = ""


# ---------------------------------------------------------------------------
# History helpers (atomic write)
# ---------------------------------------------------------------------------
def _load_history() -> list[dict]:
    _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _HISTORY_PATH.exists():
        return []
    try:
        return json.loads(_HISTORY_PATH.read_text(encoding="utf-8")) or []
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("[L24] Could not read retrain_history.json: %s", exc)
        return []


def _save_history(history: list[dict]) -> None:
    _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _HISTORY_PATH.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(history, indent=2), encoding="utf-8")
    tmp.replace(_HISTORY_PATH)


def _append_run(run: RetrainRun) -> None:
    history = _load_history()
    history.append(asdict(run))
    _save_history(history)


# ---------------------------------------------------------------------------
# Lock helpers (JSON lock: pid + hostname + created_at + run_id)
# ---------------------------------------------------------------------------
_LOCK_STALE_SECONDS = 6 * 3600  # 6 hours


def _pid_alive(pid: int) -> Optional[bool]:
    """Check whether a process with *pid* is alive.

    Returns:
        True  — process exists (or exists but inaccessible).
        False — process definitively does not exist.
        None  — uncertain (unexpected exception).

    On Windows, uses OpenProcess via ctypes (avoids os.kill which can hang for
    out-of-range PIDs on some Windows builds).
    """
    if sys.platform == "win32":
        return _pid_alive_windows(pid)

    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        # errno EPERM: process exists, we just can't signal it
        return True
    except OSError as exc:
        esrch = getattr(errno, "ESRCH", None)
        if esrch is not None and exc.errno == esrch:
            return False
        return None
    except Exception:
        return None


def _pid_alive_windows(pid: int) -> Optional[bool]:
    """Windows-specific pid liveness check via OpenProcess (no hang risk)."""
    try:
        import ctypes
        import ctypes.wintypes

        SYNCHRONIZE = 0x00100000
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle == 0:
            # OpenProcess failed
            err = kernel32.GetLastError()
            # ERROR_INVALID_PARAMETER (87): pid does not exist
            # ERROR_NOT_FOUND (1168): pid does not exist
            if err in (87, 1168):
                return False
            # ERROR_ACCESS_DENIED (5): process exists but inaccessible
            if err == 5:
                return True
            # Unknown error → uncertain
            return None

        # Check exit code — if process has exited, ExitCode != STILL_ACTIVE (259)
        exit_code = ctypes.wintypes.DWORD(0)
        ret = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        kernel32.CloseHandle(handle)
        if not ret:
            return None
        STILL_ACTIVE = 259
        return exit_code.value == STILL_ACTIVE
    except Exception:
        return None


def _read_lock(path: Path) -> Optional[dict]:
    """Return parsed JSON dict from *path*, or None if missing/empty/corrupt."""
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return None
        return json.loads(text)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _write_lock_atomic(path: Path, payload: dict) -> None:
    """Write *payload* as JSON to *path* atomically via a sibling temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".lock.tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.replace(tmp_name, str(path))
    except Exception:
        # Clean up the temp file if replace failed
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _is_stale(
    lock: dict,
    now_ts: float,
    stale_seconds: int = _LOCK_STALE_SECONDS,
) -> tuple[bool, str]:
    """Return (is_stale, reason) for *lock* dict.

    Reasons: "age" | "dead_pid" | "age_cross_host" | "fresh"
    """
    try:
        created_ts = datetime.fromisoformat(lock["created_at"]).timestamp()
    except (KeyError, ValueError, TypeError):
        # Malformed created_at → treat as maximally stale
        return True, "age"

    age = now_ts - created_ts
    current_host = socket.gethostname()
    lock_host = lock.get("hostname", "")

    if age > stale_seconds:
        return True, "age"

    if lock_host == current_host:
        pid = lock.get("pid")
        if pid is not None:
            alive = _pid_alive(int(pid))
            if alive is False:
                return True, "dead_pid"
            if alive is None:
                # Uncertain — fall through to age-only (not stale yet)
                pass
    else:
        # Cross-host: we already checked age > stale_seconds above (False here)
        # so age <= stale_seconds → fresh from the cross-host perspective
        pass

    return False, "fresh"


def _acquire_lock() -> bool:
    """Return True if lock acquired. Reclaims stale locks with a warning."""
    lock_path = _LOCK_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    now_ts = datetime.now(timezone.utc).timestamp()
    payload = {
        "pid":        os.getpid(),
        "hostname":   socket.gethostname(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_id":     str(uuid.uuid4()),
    }

    if lock_path.exists():
        existing = _read_lock(lock_path)
        if existing is None:
            log.warning("[L24] Lock file corrupt/empty — reclaiming.")
            _write_lock_atomic(lock_path, payload)
            return True

        stale, reason = _is_stale(existing, now_ts)
        if stale:
            log.warning(
                "[L24] Stale lock found (reason=%s, holder=%s@%s) — reclaiming.",
                reason,
                existing.get("pid", "?"),
                existing.get("hostname", "?"),
            )
            _write_lock_atomic(lock_path, payload)
            return True
        else:
            log.info(
                "[L24] Lock held by pid=%s hostname=%s run_id=%s. Exiting.",
                existing.get("pid", "?"),
                existing.get("hostname", "?"),
                existing.get("run_id", "?"),
            )
            return False

    # Lock does not exist — create it atomically via helper (tmp + os.replace)
    try:
        _write_lock_atomic(lock_path, payload)
        return True
    except FileExistsError:
        # Race: another process created it between our check and the write
        log.info("[L24] Lock contention (race). Exiting.")
        return False
    except OSError as exc:
        log.error("[L24] Could not create lock: %s", exc)
        return False


def _release_lock() -> None:
    """Unlink the lock only if it belongs to this process+host."""
    try:
        if not _LOCK_PATH.exists():
            return
        existing = _read_lock(_LOCK_PATH)
        if existing is None:
            # Corrupt/empty — safe to remove
            _LOCK_PATH.unlink()
            return
        if (
            existing.get("pid") == os.getpid()
            and existing.get("hostname") == socket.gethostname()
        ):
            _LOCK_PATH.unlink()
        else:
            log.warning(
                "[L24] Lock is held by a different holder (pid=%s host=%s) — not releasing.",
                existing.get("pid", "?"),
                existing.get("hostname", "?"),
            )
    except OSError as exc:
        log.warning("[L24] Could not release lock: %s", exc)


# ---------------------------------------------------------------------------
# NBA API: games-final check
# ---------------------------------------------------------------------------
def _all_games_final() -> bool:
    """Return True if every game on today's slate is FINAL via scoreboardv2."""
    try:
        from nba_api.live.nba.endpoints import scoreboard as live_sb  # type: ignore

        sb = live_sb.ScoreBoard()
        games = sb.games.get_dict()
        if not games:
            log.info("[L24] No games today — treating as all-final.")
            return True
        not_final = [
            g for g in games
            if str(g.get("gameStatus", "")).strip() != "3"
            and str(g.get("gameStatusText", "")).upper().strip() not in ("FINAL", "FINAL/OT")
        ]
        if not_final:
            log.info("[L24] %d game(s) not FINAL yet.", len(not_final))
            return False
        return True
    except ImportError:
        # Fallback to nba_api v1 scoreboardv2
        try:
            from nba_api.stats.endpoints import scoreboardv2  # type: ignore
            sb = scoreboardv2.ScoreboardV2()
            gls = sb.game_header.get_dict()
            rows = gls.get("data", [])
            headers = gls.get("headers", [])
            if not rows:
                log.info("[L24] scoreboardv2 returned no games — treating as all-final.")
                return True
            try:
                status_idx = headers.index("GAME_STATUS_ID")
            except ValueError:
                log.warning("[L24] GAME_STATUS_ID not in scoreboardv2 headers.")
                return True
            not_final = [r for r in rows if r[status_idx] != 3]
            if not_final:
                log.info("[L24] %d game(s) not FINAL (scoreboardv2).", len(not_final))
                return False
            return True
        except Exception as exc:
            log.warning("[L24] scoreboardv2 unavailable: %s", exc)
            raise


# ---------------------------------------------------------------------------
# Production MAE (from last WF output or baseline)
# ---------------------------------------------------------------------------
def compute_production_metrics() -> dict[str, float]:
    """Read current production MAE from prop_pergame_walk_forward.json.

    Falls back to hardcoded _BASELINE_MAE if the file is absent or malformed.
    Returns {stat: mae_float}.
    """
    if not _WF_OUT_PATH.exists():
        log.info("[L24] No WF JSON found — using hardcoded baseline MAE.")
        return dict(_BASELINE_MAE)
    try:
        data = json.loads(_WF_OUT_PATH.read_text(encoding="utf-8"))
        by_stat = data.get("by_stat", {})
        result: dict[str, float] = {}
        for stat in _STATS:
            entry = by_stat.get(stat, {})
            mae = entry.get("mae_3way_mean") or entry.get("mae_2way_mean")
            result[stat] = float(mae) if mae is not None else _BASELINE_MAE.get(stat, 99.0)
        return result
    except (json.JSONDecodeError, KeyError, TypeError, OSError) as exc:
        log.warning("[L24] Could not parse WF JSON (%s) — using baseline.", exc)
        return dict(_BASELINE_MAE)


# ---------------------------------------------------------------------------
# Walk-forward candidate run
# ---------------------------------------------------------------------------
def run_walk_forward_candidate() -> dict[str, float]:
    """Invoke prop_pergame_walk_forward.py as a subprocess and parse results.

    Returns {stat: candidate_mae} on success.
    Raises RuntimeError on non-zero exit, timeout, or bad JSON.
    """
    cmd = [sys.executable, str(_WF_SCRIPT)]
    log.info("[L24] Launching WF subprocess: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            timeout=3600,
            text=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"WF subprocess timed out after {exc.timeout}s") from exc

    if result.returncode != 0:
        log.error("[L24] WF subprocess failed (rc=%d):\n%s", result.returncode, result.stderr[-2000:])
        raise RuntimeError(f"WF subprocess exited with rc={result.returncode}")

    # Parse freshly written JSON
    return _parse_wf_json()


def _parse_wf_json() -> dict[str, float]:
    """Load prop_pergame_walk_forward.json and extract per-stat 3-way MAE."""
    if not _WF_OUT_PATH.exists():
        log.warning("[L24] WF JSON not found after subprocess — using baseline.")
        return dict(_BASELINE_MAE)
    try:
        data = json.loads(_WF_OUT_PATH.read_text(encoding="utf-8"))
        by_stat = data.get("by_stat", {})
        result: dict[str, float] = {}
        for stat in _STATS:
            entry = by_stat.get(stat, {})
            mae = entry.get("mae_3way_mean") or entry.get("mae_2way_mean")
            if mae is None:
                log.warning("[L24] Missing MAE for stat=%s in WF JSON — using baseline.", stat)
                result[stat] = _BASELINE_MAE.get(stat, 99.0)
            else:
                result[stat] = float(mae)
        return result
    except (json.JSONDecodeError, KeyError, TypeError, OSError) as exc:
        log.warning("[L24] Bad WF JSON shape (%s) — using baseline.", exc)
        return dict(_BASELINE_MAE)


def _count_wf_4_of_4(wf_json_path: Optional[Path] = None) -> bool:
    """Check that all 4 WF folds show MAE improvement (3-way < 2-way) for each stat."""
    if wf_json_path is None:
        wf_json_path = _WF_OUT_PATH
    if not wf_json_path.exists():
        return False
    try:
        data = json.loads(wf_json_path.read_text(encoding="utf-8"))
        folds_per_stat = data.get("folds_per_stat", {})
        if not folds_per_stat:
            return False
        for stat in _STATS:
            folds = folds_per_stat.get(stat, [])
            if len(folds) < 4:
                return False
            for fold in folds:
                if fold.get("three_way", {}).get("mae", 99.0) >= fold.get("two_way", {}).get("mae", 0.0):
                    return False
        return True
    except (json.JSONDecodeError, KeyError, TypeError, OSError):
        return False


# ---------------------------------------------------------------------------
# Gate check
# ---------------------------------------------------------------------------
def check_promotion_gate(
    candidate: dict[str, float],
    prod: dict[str, float],
) -> tuple[bool, bool, bool]:
    """Determine if candidate passes the dual gate.

    Returns (wf_4_of_4, single_split_better, gate_pass).
    gate_pass = True only when BOTH are True.
    """
    wf_4_of_4 = _count_wf_4_of_4()

    # Single-split: candidate MAE strictly below prod for every stat
    single_split_better = all(
        candidate.get(stat, 99.0) < prod.get(stat, 99.0)
        for stat in _STATS
    )

    gate_pass = wf_4_of_4 and single_split_better
    log.info(
        "[L24] Gate check — wf_4_of_4=%s single_split_better=%s gate_pass=%s",
        wf_4_of_4, single_split_better, gate_pass,
    )
    return wf_4_of_4, single_split_better, gate_pass


# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------
def deploy_candidate(via_shadow: bool = True) -> bool:
    """Deploy candidate models.

    via_shadow=True  → submit to L25.start_shadow (50-game observation).
    via_shadow=False → live copy requires RETRAIN_DEPLOY_TOKEN env var.

    Returns True on success.
    """
    if via_shadow:
        try:
            import importlib
            l25 = importlib.import_module("scripts.execute_loop.L25_ab_shadow")
            start_shadow = l25.start_shadow
        except (ImportError, AttributeError) as exc:
            log.error("[L24] L25 not available for shadow deploy: %s", exc)
            raise ImportError(str(exc)) from exc

        variant_name = f"retrain_{date.today().isoformat()}"
        try:
            start_shadow(variant_name, lambda _: None, n_games=50)
            log.info("[L24] Shadow variant registered: %s", variant_name)
            return True
        except ValueError as exc:
            # Already registered (idempotent on same-day re-run)
            log.warning("[L24] start_shadow error (variant may exist): %s", exc)
            return True

    # Live deploy requires token
    token = os.environ.get("RETRAIN_DEPLOY_TOKEN", "").strip()
    if not token:
        log.error("[L24] RETRAIN_DEPLOY_TOKEN not set — live deploy aborted.")
        return False

    # Copy candidate WF JSON to signal new production metrics are live
    dest = _MODELS_DIR / "prop_pergame_walk_forward_live.json"
    try:
        shutil.copy2(_WF_OUT_PATH, dest)
        log.info("[L24] Live deploy: copied WF JSON to %s", dest)
        return True
    except OSError as exc:
        log.error("[L24] Live deploy copy failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Alert helper (soft import)
# ---------------------------------------------------------------------------
def _send_alert(level: str, title: str, body: str) -> None:
    try:
        from scripts.execute_loop.L22_alerting import send_alert  # type: ignore
        send_alert("system", level, title, body)
    except ImportError:
        log.info("[L24] L22 alerting not available — skipping alert.")
    except Exception as exc:
        log.warning("[L24] Alert send failed: %s", exc)


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------
def _backup_models(ts: str) -> Path:
    """Copy data/models/ to data/models/_backup_<ts>/. Raises on disk full."""
    tag = ts.replace(":", "").replace("-", "").replace("T", "_")[:15]
    dest = _MODELS_DIR / f"_backup_{tag}"
    log.info("[L24] Backing up %s -> %s", _MODELS_DIR, dest)
    shutil.copytree(str(_MODELS_DIR), str(dest))
    return dest


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------
def run_nightly(via_shadow: bool = True, dry_run: bool = False) -> RetrainRun:
    """Full nightly retrain pipeline.

    Returns a RetrainRun describing what happened.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    ts_now  = datetime.now(timezone.utc)
    run_id  = f"{date.today().isoformat()}_{ts_now:%H%M%S}"
    started = ts_now.isoformat()

    log.info("[L24] run_nightly start run_id=%s dry_run=%s via_shadow=%s",
             run_id, dry_run, via_shadow)

    # ------------------------------------------------------------------
    # 1. Idempotency: if today already has a status=="ok" run, return it
    # ------------------------------------------------------------------
    today_str = date.today().isoformat()
    history = _load_history()
    for entry in reversed(history):
        if (
            entry.get("run_id", "").startswith(today_str)
            and entry.get("status") == "ok"
        ):
            log.info("[L24] Idempotency: today already has an ok run (%s).", entry["run_id"])
            return RetrainRun(**{k: v for k, v in entry.items() if k in RetrainRun.__dataclass_fields__})

    # ------------------------------------------------------------------
    # 2. Acquire lock
    # ------------------------------------------------------------------
    if not _acquire_lock():
        log.info("[L24] Could not acquire lock — exiting with status=locked.")
        return RetrainRun(run_id=run_id, started_at=started, status="locked")

    run = RetrainRun(run_id=run_id, started_at=started)

    try:
        # --------------------------------------------------------------
        # 3. Games-final check
        # --------------------------------------------------------------
        try:
            all_final = _all_games_final()
        except Exception as exc:
            log.error("[L24] scoreboardv2 check failed: %s", exc)
            run.status = "error"
            run.summary_notes = f"scoreboardv2 unavailable: {exc}"
            _send_alert("warning", "L24 Retrain Error", run.summary_notes)
            return run

        if not all_final:
            log.info("[L24] Not all games FINAL — deferring retrain.")
            run.status = "no_new_data"
            run.summary_notes = "Games not yet final."
            _append_run(run)
            return run

        # --------------------------------------------------------------
        # 4. Snapshot production MAE BEFORE retrain
        # --------------------------------------------------------------
        run.prod_mae_before = compute_production_metrics()
        log.info("[L24] Production MAE snapshot: %s", run.prod_mae_before)

        # --------------------------------------------------------------
        # 5. Backup models
        # --------------------------------------------------------------
        if not dry_run:
            try:
                _backup_models(ts_now.strftime("%Y%m%d_%H%M%S"))
            except OSError as exc:
                log.error("[L24] Backup failed (disk full?): %s", exc)
                run.status = "error"
                run.summary_notes = f"Backup failed: {exc}"
                raise SystemExit(1) from exc

        # --------------------------------------------------------------
        # 6. Run walk-forward (subprocess)
        # --------------------------------------------------------------
        if dry_run:
            log.info("[L24] dry_run=True — skipping WF subprocess.")
            # In dry-run, parse existing JSON if present
            run.candidate_mae = _parse_wf_json()
        else:
            try:
                run.candidate_mae = run_walk_forward_candidate()
            except RuntimeError as exc:
                log.error("[L24] Walk-forward failed: %s", exc)
                run.status = "wf_failed"
                run.summary_notes = str(exc)
                _send_alert("warning", "L24 WF Failed", run.summary_notes)
                _append_run(run)
                return run

        log.info("[L24] Candidate MAE: %s", run.candidate_mae)

        # --------------------------------------------------------------
        # 7. Gate check
        # --------------------------------------------------------------
        wf_4_of_4, single_split_better, gate_pass = check_promotion_gate(
            run.candidate_mae, run.prod_mae_before
        )
        run.wf_4_of_4         = wf_4_of_4
        run.single_split_better = single_split_better
        run.gate_pass         = gate_pass

        if not gate_pass:
            run.status = "gate_warn"
            failing = []
            if not wf_4_of_4:
                failing.append("wf_4_of_4=False")
            if not single_split_better:
                regressions = [
                    s for s in _STATS
                    if run.candidate_mae.get(s, 99.0) >= run.prod_mae_before.get(s, 99.0)
                ]
                failing.append(f"single_split_regressions={regressions}")
            run.summary_notes = "Gate failed: " + "; ".join(failing)
            log.info("[L24] Gate not passed — no deploy. %s", run.summary_notes)
            _send_alert("warning", "L24 Gate Warn", run.summary_notes)
            _append_run(run)
            return run

        # --------------------------------------------------------------
        # 8. Deploy
        # --------------------------------------------------------------
        if not dry_run:
            try:
                ok = deploy_candidate(via_shadow=via_shadow)
                run.deployed = ok
                run.deploy_mode = "shadow" if via_shadow else ("live" if ok else "none")
            except ImportError as exc:
                log.error("[L24] Deploy import error: %s", exc)
                run.status = "error"
                run.summary_notes = f"Deploy import error: {exc}"
                _send_alert("error", "L24 Deploy Error", run.summary_notes)
                _append_run(run)
                return run
        else:
            log.info("[L24] dry_run=True — skipping deploy.")
            run.deploy_mode = "none"

        run.status = "ok"
        run.summary_notes = (
            f"Gate passed. deployed={run.deployed} mode={run.deploy_mode}. "
            + " ".join(
                f"{s}:{run.candidate_mae.get(s, 0):.4f}"
                for s in _STATS
            )
        )
        _send_alert("info", "L24 Retrain OK", run.summary_notes)

    finally:
        run.finished_at = datetime.now(timezone.utc).isoformat()
        _release_lock()
        # Always persist (unless locked — status=locked never reaches here)
        if run.status != "locked":
            _append_run(run)

    log.info("[L24] run_nightly complete run_id=%s status=%s", run.run_id, run.status)
    return run


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------
def _cli_run(args) -> int:
    run = run_nightly(via_shadow=True, dry_run=False)
    print(f"[L24] status={run.status}  run_id={run.run_id}")
    print(f"      gate_pass={run.gate_pass}  deployed={run.deployed}  mode={run.deploy_mode}")
    print(f"      notes: {run.summary_notes}")
    return 0 if run.status in ("ok", "no_new_data") else 1


def _cli_dry_run(args) -> int:
    run = run_nightly(via_shadow=True, dry_run=True)
    print(f"[L24] DRY-RUN status={run.status}  gate_pass={run.gate_pass}")
    print(f"      candidate_mae={run.candidate_mae}")
    return 0


def _cli_status(args) -> int:
    history = _load_history()
    last5 = history[-5:]
    if not last5:
        print("[L24] No retrain history found.")
        return 0
    print(f"[L24] Last {len(last5)} retrain run(s):")
    for entry in reversed(last5):
        print(
            f"  {entry.get('run_id','?'):30s}  status={entry.get('status','?'):12s}"
            f"  gate={entry.get('gate_pass',False)}  deployed={entry.get('deployed',False)}"
            f"  mode={entry.get('deploy_mode','none')}"
        )
    return 0


def _cli_rollback(args) -> int:
    target_id: str = args.to
    history = _load_history()
    run_ids = [e.get("run_id", "") for e in history]
    if target_id not in run_ids:
        print(f"[L24] ERROR: run_id {target_id!r} not found in history.")
        return 1

    backup_key = "_backup_" + target_id.replace("-", "").replace("_", "")[:13]
    candidates = sorted(_MODELS_DIR.glob("_backup_*"))
    match = next((p for p in candidates if backup_key[:12] in p.name), None)

    if match is None:
        # Try date-prefix match
        date_part = target_id[:10].replace("-", "")
        match = next((p for p in candidates if date_part in p.name), None)

    if match is None:
        print(f"[L24] ERROR: No backup directory found for run_id={target_id!r}")
        print(f"  Available backups: {[p.name for p in candidates]}")
        return 1

    print(f"[L24] Rolling back from backup: {match}")
    # Move current models to a temp dir then restore backup
    temp_aside = _MODELS_DIR.parent / f"_models_rollback_tmp_{os.getpid()}"
    try:
        _MODELS_DIR.rename(temp_aside)
        shutil.copytree(str(match), str(_MODELS_DIR))
        shutil.rmtree(str(temp_aside), ignore_errors=True)
        print(f"[L24] Rollback complete — models restored from {match.name}.")
        return 0
    except OSError as exc:
        print(f"[L24] Rollback failed: {exc}")
        if temp_aside.exists() and not _MODELS_DIR.exists():
            temp_aside.rename(_MODELS_DIR)
        return 1


def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(prog="L24_nightly_retrain", description="Nightly retrain cron")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("run",     help="Run nightly retrain").set_defaults(func=_cli_run)
    sub.add_parser("dry-run", help="Dry-run (no subprocess, no deploy)").set_defaults(func=_cli_dry_run)
    sub.add_parser("status",  help="Print last 5 retrain runs").set_defaults(func=_cli_status)

    p_rb = sub.add_parser("rollback", help="Restore models from a prior run backup")
    p_rb.add_argument("--to", required=True, metavar="RUN_ID", help="run_id to roll back to")
    p_rb.set_defaults(func=_cli_rollback)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

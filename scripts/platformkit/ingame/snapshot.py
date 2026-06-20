"""scripts.platformkit.ingame.snapshot -- atomic per-game live snapshot I/O.

Writes and reads per-game live market sets as JSON under:
  data/frontend/ingame/<sport>/<game_id>.json

plus a per-sport latest index:
  data/frontend/ingame/<sport>/_latest.json

Writes are ATOMIC (write .tmp, then os.replace) so a concurrent reader never
sees a torn file.  Reads are GUARDED (never raise; a missing/corrupt file returns
a clean unavailable sentinel).

This module is the read-model that the live_loop publishes and /api/live reads.

CONTRACT for serve.py /api/live repoint:
  * serve.py currently reads _read_snapshot_part(sport, "live") from snapshot_writer.
  * A near-drop-in substitution replaces that path with:
      from scripts.platformkit.ingame import snapshot as igsnap
      snap = igsnap.read_live_part(sport)     # returns the "live" block or None
      if snap is None:
          # fall back to live_board.todays_live_games(sport)  (unchanged)
  * The shape of read_live_part() matches what _read_snapshot_part currently stamps:
      {"sport", "status", "games", "as_of", "freshness", "served_from", ...}

HONEST + SAFE:
  * No dollar edge. edge_claimed is always False.
  * MAE wins from shrinking toward the current score are MEDIAN-vs-MEAN ARTIFACTS;
    variance (which shrinks as fraction_elapsed rises) is the honest measure.
  * Unavailable / missing -> clean sentinel (never fabricates a number).
  * data/ is gitignored -- snapshots are a local cache, never committed.

INVARIANTS: <=300 LOC; ASCII-only; no network; never edits src/ or kernel/.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Snapshots live under the gitignored data/ tree.
# __file__ = scripts/platformkit/ingame/snapshot.py -> parents[3] = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = _REPO_ROOT / "data" / "frontend" / "ingame"

_EDGE_CLAIMED = False

_HONEST_NOTE = (
    "Live in-game snapshot. Variance shrinks as the game progresses. "
    "No dollar edge is claimed. Markets are efficient."
)

_UNAVAILABLE_SENTINEL: Dict[str, Any] = {
    "sport": "unknown",
    "status": "unavailable",
    "games": [],
    "available": False,
    "edge_claimed": _EDGE_CLAIMED,
    "_honest_note": _HONEST_NOTE,
}


# ---- helpers -----------------------------------------------------------------

def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sport_dir(sport: str, out_dir: Path) -> Path:
    return out_dir / str(sport).lower()


def _game_path(sport: str, game_id: str, out_dir: Path) -> Path:
    return _sport_dir(sport, out_dir) / f"{game_id}.json"


def _latest_path(sport: str, out_dir: Path) -> Path:
    return _sport_dir(sport, out_dir) / "_latest.json"


def _atomic_write(path: Path, payload: Dict[str, Any]) -> None:
    """Write *payload* as JSON to *path* atomically via a .tmp then os.replace.

    A concurrent reader always sees either the old complete file or the new
    complete file -- never a half-written one. Creates parent dirs as needed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="ascii") as fh:
        json.dump(payload, fh, default=str, ensure_ascii=True)
    os.replace(tmp, path)


def _unavailable_sentinel(sport: str, reason: str = "unavailable") -> Dict[str, Any]:
    return {
        "sport": str(sport).lower(),
        "status": "unavailable",
        "games": [],
        "available": False,
        "reason": reason,
        "edge_claimed": _EDGE_CLAIMED,
        "_honest_note": _HONEST_NOTE,
    }


# ---- public write API --------------------------------------------------------

def write_live(game_id: str, market_set: Dict[str, Any], *,
               out_dir: Optional[Path] = None) -> Path:
    """Write a per-game live market set atomically; update the per-sport latest index.

    market_set must carry a 'sport' key.  Returns the path written
    (data/frontend/ingame/<sport>/<game_id>.json).  Never raises.
    """
    try:
        return _write_live_inner(game_id, market_set, out_dir)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("write_live failed game_id=%s: %s", game_id, exc)
        base = Path(out_dir) if out_dir else DEFAULT_OUT_DIR
        return _game_path(
            market_set.get("sport", "unknown") if isinstance(market_set, dict) else "unknown",
            str(game_id), base)


def _write_live_inner(game_id: str, market_set: Dict[str, Any],
                      out_dir: Optional[Path]) -> Path:
    base = Path(out_dir) if out_dir is not None else DEFAULT_OUT_DIR
    sport = str(market_set.get("sport", "unknown")).lower()
    gid = str(game_id)
    path = _game_path(sport, gid, base)

    envelope: Dict[str, Any] = {
        "game_id": gid,
        "sport": sport,
        "generated_at": _utc_iso(),
        "status": "ok",
        "edge_claimed": _EDGE_CLAIMED,
        "market_set": market_set,
    }

    _atomic_write(path, envelope)

    # Update the per-sport latest index (best-effort; never blocks the primary write).
    try:
        latest_path = _latest_path(sport, base)
        # Load existing index to merge; start fresh on any read failure.
        existing: Dict[str, Any] = {}
        if latest_path.exists():
            try:
                with latest_path.open("r", encoding="utf-8") as fh:
                    existing = json.load(fh)
            except Exception:
                existing = {}
        game_index = existing.get("games") if isinstance(existing, dict) else {}
        if not isinstance(game_index, dict):
            game_index = {}
        game_index[gid] = str(path)
        latest_payload: Dict[str, Any] = {
            "sport": sport,
            "updated_at": _utc_iso(),
            "games": game_index,
        }
        _atomic_write(latest_path, latest_payload)
    except Exception as exc:  # pragma: no cover - index update is best-effort
        logger.warning("write_live index update failed sport=%s: %s", sport, exc)

    return path


# ---- public read API ---------------------------------------------------------

def read_live(game_id: str, sport: str = "nba", *,
              out_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Read the live snapshot envelope for *game_id*, or None on miss/corrupt.

    Returns the raw envelope dict (with 'market_set' sub-key) or None.
    The caller is responsible for extracting market_set if it only needs that.
    Never raises.
    """
    try:
        base = Path(out_dir) if out_dir is not None else DEFAULT_OUT_DIR
        path = _game_path(sport, str(game_id), base)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return None
        return data
    except Exception as exc:  # noqa: BLE001 - a corrupt file is just a cache miss
        logger.warning("read_live failed game_id=%s sport=%s: %s", game_id, sport, exc)
        return None


def read_live_part(sport: str, *, out_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Read ALL live market sets for *sport* and return them as a "live" block.

    This is the shape that serve.py /api/live expects (matching the existing
    _read_snapshot_part(sport, "live") contract from snapshot_writer):

    {
      "sport": str,
      "status": "ok" | "unavailable",
      "games": [ market_set, ... ],      # one per written game
      "as_of": str,                      # ISO UTC timestamp
      "freshness": {"as_of": ..., "source": "ingame_snapshot"},
      "served_from": "ingame_snapshot",
      "edge_claimed": False,
      "_honest_note": str,
    }

    Returns None on a complete miss (no files) so the caller can fall back to
    live_board.todays_live_games(sport). Never raises.
    """
    try:
        return _read_live_part_inner(sport, out_dir)
    except Exception as exc:  # pragma: no cover - defensive; read must never raise
        logger.warning("read_live_part failed sport=%s: %s", sport, exc)
        return None


def _read_live_part_inner(sport: str,
                          out_dir: Optional[Path]) -> Optional[Dict[str, Any]]:
    base = Path(out_dir) if out_dir is not None else DEFAULT_OUT_DIR
    sp = str(sport).lower()
    latest_path = _latest_path(sp, base)
    if not latest_path.exists():
        return None

    try:
        with latest_path.open("r", encoding="utf-8") as fh:
            index = json.load(fh)
    except Exception:
        return None

    if not isinstance(index, dict):
        return None

    game_index: Dict[str, str] = {}
    gi = index.get("games")
    if isinstance(gi, dict):
        game_index = {str(k): str(v) for k, v in gi.items()}

    if not game_index:
        return None

    games: List[Dict[str, Any]] = []
    for gid, path_str in game_index.items():
        envelope = read_live(gid, sport=sp, out_dir=base)
        if envelope is None:
            continue
        ms = envelope.get("market_set")
        if isinstance(ms, dict) and ms:
            games.append(ms)

    # Return None (cache miss) rather than an empty list -- lets the caller fall
    # back to live_board (preserves the existing serve.py fallback logic).
    if not games:
        return None

    as_of = _utc_iso()
    return {
        "sport": sp,
        "status": "ok",
        "games": games,
        "as_of": as_of,
        "freshness": {"as_of": as_of, "source": "ingame_snapshot"},
        "served_from": "ingame_snapshot",
        "edge_claimed": _EDGE_CLAIMED,
        "_honest_note": _HONEST_NOTE,
    }


def list_live_game_ids(sport: str, *, out_dir: Optional[Path] = None) -> List[str]:
    """Return the list of game ids currently indexed for *sport*. Empty on miss.

    Never raises.
    """
    try:
        base = Path(out_dir) if out_dir is not None else DEFAULT_OUT_DIR
        sp = str(sport).lower()
        latest_path = _latest_path(sp, base)
        if not latest_path.exists():
            return []
        with latest_path.open("r", encoding="utf-8") as fh:
            index = json.load(fh)
        if not isinstance(index, dict):
            return []
        gi = index.get("games")
        return list(gi.keys()) if isinstance(gi, dict) else []
    except Exception:  # noqa: BLE001
        return []

"""scripts.platformkit.ingame.kbo_baseout_accrual -- KBO base-out state
accrual for HISTORICAL/completed games (census rank 5: "ports the proven
MLB base-out state machine to a live-daily sport").

PORTS ingame_baseout_mlb.py's RE24 run-expectancy table + base-out-state
derivation (base_state 3-bit mask bit0=1st/bit1=2nd/bit2=3rd,
base_out_state=base_state*3+outs, the standard published RE24 matrix -- run
expectancy is a UNIVERSAL baseball constant, not MLB-specific, so the SAME
table applies unmodified to KBO) to KBO's feed shape: kbo_naver_relay.
extract_base_out_state's {outs, base1, base2, base3} booleans (Naver relay)
instead of ESPN's onFirst/onSecond/onThird event fields -- a field-shape
adapter, not a new run-expectancy model. Reuses _BASE_LABEL/_RE24 directly
from ingame_baseout_mlb (same cross-module private-constant reuse pattern
domains/basketball_wnba already uses across its own sibling modules).

ACCRUAL (the new piece this module adds, beyond MLB's per-tick parser):
given an ordered sequence of per-tick capture rows for ONE completed game
(the SAME row shape kbo_relay_state_provider.py already writes to
data/cache/kbo_relay_state/<game_id>.jsonl -- no live daemon wiring here,
this module only READS that existing capture-only corpus), collapse
consecutive ticks sharing one base-out state into SEGMENTS (a state held
across N repeated polls), then emit one per-game summary: distinct states
visited, tick counts per segment, and each segment's RE24 run expectancy --
descriptive only, no probability model, no gate, no market/$ edge.

HONEST GAP (this wave, real data checked): every currently-captured
data/cache/kbo_relay_state/<gid>.jsonl file for a COMPLETED game holds
outs==3 on every row (the relay's tail-window freezes at the final
end-of-game snapshot and the daemon kept polling after the game ended,
capturing the same frozen tick repeatedly -- verified this wave across every
2026-07-05/07/08 KBO capture on disk: each file collapses to exactly ONE
distinct content-state once fetch_ts is dropped). outs==3 is not a valid
in-play base-out state (3 outs ends the half-inning -- same convention
ingame_baseout_mlb.parse_baseout already enforces: outs must be 0/1/2), so
accrual over TODAY's on-disk KBO captures honestly yields zero valid in-play
segments per game. This is a REAL LIMIT of the current capture cadence (it
only ever observed games already at/after their final out this wave), not a
bug in this module's logic -- test_kbo_baseout_accrual.py proves the accrual
mechanism itself is correct against a synthetic multi-state in-play
sequence.

INVARIANTS: <=300 LOC; ASCII only; no pip installs; no $/edge fields; never
raises (a malformed/absent capture degrades to an empty/partial summary,
never an aborted run); no writes to data/registry/, src/, kernel/, api/.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_kbo_baseout_accrual.py -q
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.ingame.ingame_baseout_mlb import _BASE_LABEL, _RE24

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STATE_DIR = _REPO_ROOT / "data" / "cache" / "kbo_relay_state"
DEFAULT_OUT_DIR = _REPO_ROOT / "data" / "cache" / "kbo_baseout_accrual"

_LABEL_TO_MASK = {v: k for k, v in _BASE_LABEL.items()}


def parse_kbo_baseout(bos: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """kbo_naver_relay.extract_base_out_state's {outs, base1, base2, base3,
    ...} booleans -> the SAME output shape as ingame_baseout_mlb.
    parse_baseout ({outs, on_first/second/third, base_state, base_label,
    base_out_state, run_expectancy}). None if outs is missing/invalid (0/1/2
    only -- 3 outs ends the half-inning, not an in-play state; never
    fabricated)."""
    if not isinstance(bos, dict):
        return None
    outs = bos.get("outs")
    try:
        outs = int(outs)
    except (TypeError, ValueError):
        return None
    if outs < 0 or outs > 2:
        return None
    on1, on2, on3 = bool(bos.get("base1")), bool(bos.get("base2")), bool(bos.get("base3"))
    base_state = (1 if on1 else 0) | (2 if on2 else 0) | (4 if on3 else 0)
    return {
        "outs": outs, "on_first": on1, "on_second": on2, "on_third": on3,
        "base_state": base_state, "base_label": _BASE_LABEL[base_state],
        "base_out_state": base_state * 3 + outs,
        "run_expectancy": round(_RE24[base_state][outs], 3),
    }


def _label_to_baseout(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """kbo_relay_state_provider row (base_state as a '1--'-style compact
    label, not raw booleans) -> the same parse_kbo_baseout shape, plus the
    row's own inning/half/score/fetch_ts context. None if the label/outs are
    absent or outs is out of the 0-2 in-play range."""
    outs = row.get("outs")
    try:
        outs = int(outs)
    except (TypeError, ValueError):
        return None
    if outs < 0 or outs > 2:
        return None
    mask = _LABEL_TO_MASK.get(row.get("base_state"))
    if mask is None:
        return None
    return {
        "outs": outs, "base_state": mask, "base_label": _BASE_LABEL[mask],
        "base_out_state": mask * 3 + outs,
        "run_expectancy": round(_RE24[mask][outs], 3),
        "inning": row.get("inning"), "half": row.get("half"),
        "score_home": row.get("score_home"), "score_away": row.get("score_away"),
        "fetch_ts": row.get("fetch_ts"),
    }


def accrue_game_states(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Ordered per-tick capture rows (kbo_relay_state_provider shape) for ONE
    game -> a segment-collapsed accrual summary. Consecutive ticks sharing
    the identical (base_out_state, inning, half, score) are ONE segment (a
    state held across N repeated polls); ticks that fail the honest outs<=2
    gate are excluded from segments but counted in n_ticks_excluded. Never
    raises; [] input -> a zero-segment summary."""
    segments: List[Dict[str, Any]] = []
    n_excluded = 0
    for row in rows:
        parsed = _label_to_baseout(row)
        if parsed is None:
            n_excluded += 1
            continue
        key = (parsed["base_out_state"], parsed["inning"], parsed["half"],
               parsed["score_home"], parsed["score_away"])
        if segments and segments[-1]["_key"] == key:
            segments[-1]["n_ticks"] += 1
            segments[-1]["last_fetch_ts"] = parsed["fetch_ts"]
            continue
        segments.append({
            "_key": key, "base_out_state": parsed["base_out_state"],
            "base_label": parsed["base_label"], "outs": parsed["outs"],
            "run_expectancy": parsed["run_expectancy"], "inning": parsed["inning"],
            "half": parsed["half"], "score_home": parsed["score_home"],
            "score_away": parsed["score_away"], "n_ticks": 1,
            "first_fetch_ts": parsed["fetch_ts"], "last_fetch_ts": parsed["fetch_ts"],
        })
    for s in segments:
        s.pop("_key", None)
    return {
        "n_ticks_total": len(rows), "n_ticks_excluded": n_excluded,
        "n_segments": len(segments), "segments": segments,
    }


def load_state_rows(game_id: str, state_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read data/cache/kbo_relay_state/<game_id>.jsonl (kbo_relay_state_
    provider's own append format) into an ordered row list. [] if the file
    is absent/malformed (never raises)."""
    path = (state_dir or DEFAULT_STATE_DIR) / f"{game_id}.jsonl"
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError as exc:
        logger.debug("kbo_baseout_accrual load_state_rows(%s) failed: %s", game_id, exc)
        return []
    return rows


def accrue_and_write(game_id: str, state_dir: Optional[Path] = None,
                      out_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Load + accrue one game's captured state rows, write the summary to
    data/cache/kbo_baseout_accrual/<game_id>.json (atomic .tmp+os.replace).
    Returns the summary dict, or None if no rows were found (never raises)."""
    rows = load_state_rows(game_id, state_dir)
    if not rows:
        return None
    summary = accrue_game_states(rows)
    summary["game_id"] = str(game_id)
    out = out_dir or DEFAULT_OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{game_id}.json"
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(summary, sort_keys=True), encoding="ascii")
        os.replace(str(tmp), str(path))
    except OSError as exc:
        logger.warning("kbo_baseout_accrual accrue_and_write(%s) failed: %s", game_id, exc)
    return summary


def run_accrue_all(state_dir: Optional[Path] = None, out_dir: Optional[Path] = None
                    ) -> Dict[str, int]:
    """Walk every captured game under state_dir and write its accrual
    summary. Returns {n_games, n_segments_total}."""
    base = state_dir or DEFAULT_STATE_DIR
    if not base.exists():
        return {"n_games": 0, "n_segments_total": 0}
    n_games, n_segments = 0, 0
    for p in sorted(base.glob("*.jsonl")):
        summary = accrue_and_write(p.stem, state_dir=base, out_dir=out_dir)
        if summary is not None:
            n_games += 1
            n_segments += summary["n_segments"]
    return {"n_games": n_games, "n_segments_total": n_segments}


def _main() -> int:
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_accrue_all(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "parse_kbo_baseout", "accrue_game_states", "load_state_rows",
    "accrue_and_write", "run_accrue_all", "DEFAULT_STATE_DIR", "DEFAULT_OUT_DIR",
]

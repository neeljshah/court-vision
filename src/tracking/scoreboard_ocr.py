"""
scoreboard_ocr.py — Broadcast scoreboard overlay reader.

Extracts game state from the broadcast overlay every _OCR_INTERVAL frames
using EasyOCR. Falls back to last-known cached values on skipped or failed
frames.

Public API
----------
    ScoreboardOCR(frame_width, frame_height)
    .read(frame) -> dict with keys:
        game_clock_sec  — float, seconds remaining in period (-1 = unknown)
        shot_clock      — float, shot clock value 1-24 (-1 = unknown)
        home_score      — int   (-1 = unknown)
        away_score      — int   (-1 = unknown)
        period          — int, 1-4 or 5 for OT (-1 = unknown)
        home_timeouts   — int   (-1 = unknown)
        away_timeouts   — int   (-1 = unknown)
        home_fouls      — int   (-1 = unknown)
        away_fouls      — int   (-1 = unknown)
        score_diff      — int, home_score - away_score (0 when unknown)
"""

from __future__ import annotations

import logging
import re
from typing import Dict, Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)

_OCR_INTERVAL = 15      # run OCR every N frames (EasyOCR is expensive)
_TOP_FRAC     = 0.06    # top 6% of frame — ESPN/TNT scoreboard always in top ~5%
_OCR_CONF_MIN = 0.35    # minimum EasyOCR confidence to accept a text token

_DEFAULT_STATE: Dict = {
    "game_clock_sec": -1.0,
    "shot_clock":     -1.0,
    "home_score":     -1,
    "away_score":     -1,
    "period":         -1,
    "home_timeouts":  -1,
    "away_timeouts":  -1,
    "home_fouls":     -1,
    "away_fouls":     -1,
    "score_diff":      0,
}

_reader_sb: Optional[object] = None   # module-level EasyOCR singleton


def _get_reader() -> object:
    """Lazy-init EasyOCR reader (GPU when available, CPU fallback)."""
    global _reader_sb
    if _reader_sb is None:
        import easyocr  # optional dependency — may not be installed
        try:
            _reader_sb = easyocr.Reader(["en"], gpu=True, verbose=False)
        except Exception:
            _reader_sb = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _reader_sb


class ScoreboardOCR:
    """
    Reads broadcast scoreboard overlay every _OCR_INTERVAL frames.

    Scans only the top 6% of the frame (ESPN/TNT scoreboard is always in
    the top ~5%). Caches the last successfully parsed value for each field
    and returns the cache on non-OCR frames or when OCR fails.

    Args:
        frame_width:  Width of the input frame in pixels (post-TOPCUT).
        frame_height: Height of the input frame in pixels (post-TOPCUT).
    """

    def __init__(self, frame_width: int, frame_height: int) -> None:
        self.fw = frame_width
        self.fh = frame_height
        self._frame_counter = 0
        self._last_state: Dict = dict(_DEFAULT_STATE)

    def read(self, frame: np.ndarray) -> Dict:
        """
        Return game-state dict for this frame.

        Runs OCR every _OCR_INTERVAL frames; returns cached state otherwise.

        Args:
            frame: BGR frame (already cropped by TOPCUT).

        Returns:
            Dict with all scoreboard keys. Unknown fields are -1.
        """
        self._frame_counter += 1
        if self._frame_counter % _OCR_INTERVAL != 0:
            return dict(self._last_state)

        parsed = self._ocr_frame(frame)
        # Merge — only overwrite fields that were successfully read this frame
        for k, v in parsed.items():
            if v not in (-1, -1.0):
                self._last_state[k] = v

        # Recompute score_diff from best known scores
        hs = self._last_state["home_score"]
        as_ = self._last_state["away_score"]
        self._last_state["score_diff"] = (hs - as_) if (hs >= 0 and as_ >= 0) else 0

        return dict(self._last_state)

    # ── internal ──────────────────────────────────────────────────────────

    def _ocr_frame(self, frame: np.ndarray) -> Dict:
        """Run EasyOCR on top/bottom overlay regions and parse the results."""
        state = dict(_DEFAULT_STATE)
        try:
            reader = _get_reader()
        except Exception as e:
            log.debug("ScoreboardOCR: EasyOCR init failed — %s", e)
            return state

        h = frame.shape[0]
        region = frame[:int(h * _TOP_FRAC), :]
        if region.size == 0:
            return state
        try:
            results = reader.readtext(region, detail=1, paragraph=False)
            tokens = [r[1] for r in results if r[2] >= _OCR_CONF_MIN]
            text = " ".join(tokens)
            parsed = _parse_scoreboard_text(text)
            for k, v in parsed.items():
                if v not in (-1, -1.0) and state[k] in (-1, -1.0):
                    state[k] = v
        except Exception as e:
            log.debug("ScoreboardOCR: region OCR failed — %s", e)

        return state


# ── text parsing helpers ───────────────────────────────────────────────────────

def _parse_scoreboard_text(text: str) -> Dict:
    """
    Extract game-state values from raw OCR text using regex heuristics.

    Values outside expected ranges are discarded.  Returns a state dict
    with -1 for any field that could not be parsed.
    """
    state = dict(_DEFAULT_STATE)

    # ── Game clock: MM:SS or M:SS ─────────────────────────────────────────
    clock = re.search(r"\b(\d{1,2})[:\.](\d{2})\b", text)
    if clock:
        mins, secs = int(clock.group(1)), int(clock.group(2))
        if 0 <= mins <= 12 and 0 <= secs <= 59:
            state["game_clock_sec"] = float(mins * 60 + secs)

    # ── Shot clock: decimal "xx.x" format first (e.g. "14.3", "0.8"), then int ─
    # Skip digits that are part of a MM:SS clock pattern (followed by ':').
    # Match optional integer part + decimal fraction, not preceded/followed by digit.
    sc_dec = re.search(r"(?<!\d)((?:2[0-4]|1\d|\d)\.\d)(?!\d)", text)
    if sc_dec:
        val_dec = float(sc_dec.group(1))
        if 0.0 < val_dec <= 24.0:
            state["shot_clock"] = val_dec
    else:
        # Exclude digits immediately followed by ':' (they are clock minutes)
        sc = re.search(r"(?<!\d)(2[0-4]|1\d|[1-9])(?!\d)(?!:)", text)
        if sc:
            val = int(sc.group(1))
            if 1 <= val <= 24:
                state["shot_clock"] = float(val)

    # ── Period: Q1-Q4 / 1st-4th / OT ─────────────────────────────────────
    period = re.search(
        r"\bQ([1-4])\b|\b([1-4])(?:st|nd|rd|th)\b|\b(OT\d?)\b",
        text, re.IGNORECASE
    )
    if period:
        if period.group(3):                         # overtime
            state["period"] = 5
        else:
            state["period"] = int(period.group(1) or period.group(2))

    # ── Scores: two integers in typical NBA game-score range (30-175) ─────
    candidates = [
        int(m) for m in re.findall(r"\b(\d{1,3})\b", text)
        if 30 <= int(m) <= 175
    ]
    if len(candidates) >= 2:
        state["home_score"] = candidates[0]
        state["away_score"] = candidates[1]

    # ── Timeouts: small integer 0-7 that appears twice ────────────────────
    timeout_cands = [
        int(m) for m in re.findall(r"\b([0-7])\b", text)
    ]
    if len(timeout_cands) >= 2:
        state["home_timeouts"] = timeout_cands[0]
        state["away_timeouts"] = timeout_cands[1]

    # ── Fouls: small integer 0-6 that appears twice ───────────────────────
    foul_cands = [
        int(m) for m in re.findall(r"\b([0-6])\b", text)
    ]
    if len(foul_cands) >= 2:
        state["home_fouls"] = foul_cands[0]
        state["away_fouls"] = foul_cands[1]

    return state

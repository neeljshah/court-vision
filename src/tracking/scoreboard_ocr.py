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
from dataclasses import dataclass
from typing import Dict, Optional

import cv2
import numpy as np


@dataclass
class ScoreboardReading:
    """Single scoreboard OCR reading for one frame.

    Fields that could not be parsed are None.
    confidence is 0.0–1.0 based on how many of the 5 primary fields were read.
    """
    frame_idx:  int
    game_clock: Optional[str]   # "MM:SS" e.g. "10:42"
    shot_clock: Optional[int]   # 1-24
    home_score: Optional[int]
    away_score: Optional[int]
    period:     Optional[int]   # 1-4 or 5 for OT
    confidence: float           # 0.0-1.0


def read_scoreboard(frame: "np.ndarray", frame_idx: int) -> ScoreboardReading:
    """
    Read scoreboard state from a single frame.

    Convenience wrapper around ScoreboardOCR for one-shot reads.
    For streaming use (every N frames with caching), instantiate ScoreboardOCR
    and call .read() directly.

    Args:
        frame:     BGR numpy array (post-TOPCUT).
        frame_idx: Absolute video frame index (for logging/CSV).

    Returns:
        ScoreboardReading with populated fields and a 0–1 confidence score.
        Any field that could not be parsed is None.
    """
    _state = _one_shot_ocr(frame)
    gc_sec  = _state.get("game_clock_sec", -1.0)
    sc      = _state.get("shot_clock",    -1.0)
    hs      = _state.get("home_score",    -1)
    as_     = _state.get("away_score",    -1)
    period  = _state.get("period",        -1)

    # Convert game_clock_sec to "MM:SS" string
    if gc_sec >= 0:
        mins = int(gc_sec) // 60
        secs = int(gc_sec) % 60
        clock_str: Optional[str] = f"{mins}:{secs:02d}"
    else:
        clock_str = None

    parsed = [
        clock_str is not None,
        sc      > 0,
        hs      >= 0,
        as_     >= 0,
        period  > 0,
    ]
    conf = sum(parsed) / len(parsed)

    return ScoreboardReading(
        frame_idx  = frame_idx,
        game_clock = clock_str,
        shot_clock = int(sc)  if sc   > 0  else None,
        home_score = hs       if hs   >= 0 else None,
        away_score = as_      if as_  >= 0 else None,
        period     = period   if period > 0 else None,
        confidence = round(conf, 3),
    )


def _one_shot_ocr(frame: "np.ndarray") -> Dict:
    """Run one OCR pass (no caching). Used by read_scoreboard()."""
    _tmp = ScoreboardOCR(
        frame_width=frame.shape[1],
        frame_height=frame.shape[0],
    )
    # Force the internal counter to trigger on the first call
    _tmp._frame_counter = _tmp._ocr_interval - 1
    return _tmp._ocr_frame(frame)

log = logging.getLogger(__name__)

_OCR_INTERVAL = 15      # FIX-J: 30→15 — halves max stale-clock gap; PBP mapper needs ±2s tolerance
# BUG 41 FIX: raised 0.06→0.10 so the scan window covers the full 60-pixel
# scoreboard strip on 720p (0.06 * 720 = 43px < 60px; 0.10 * 720 = 72px > 60px).
# On 1080p this expands to 108px, still well within the broadcast overlay area.
_TOP_FRAC     = 0.10    # top 10% of frame — covers 60px TOPCUT strip at 720p/1080p
_OCR_CONF_MIN = 0.30    # R8: PaddleOCR clusters 0.8-0.95 — 0.30 only filters obvious garbage

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
    # FIX 5: None instead of 0 so downstream code can distinguish "unknown"
    # from a genuine tied game.  score_diff=0 was misleading — the game is
    # almost never tied on every single frame.
    "score_diff":     None,
}

_reader_sb: Optional[object] = None    # module-level OCR singleton
_sb_use_paddle: bool = False           # True when PaddleOCR init succeeded


def _get_reader() -> object:
    """Lazy-init OCR reader: PaddleOCR (GPU) first, EasyOCR fallback."""
    global _reader_sb, _sb_use_paddle
    if _reader_sb is not None:
        return _reader_sb

    # PaddleOCR — run on CPU to save ~1.5GB VRAM for tracking models.
    # Scoreboard OCR is lightweight (top 6% of frame, every ~30 frames)
    # and CPU is fast enough.
    try:
        import os as _os
        _os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        from paddleocr import PaddleOCR  # type: ignore
        _reader_sb = PaddleOCR(
            use_angle_cls=False,
            lang="en",
            use_gpu=False,
            show_log=False,
            rec_char_dict_path=None,
        )
        _sb_use_paddle = True
        log.debug("scoreboard_ocr: using PaddleOCR (CPU — saves VRAM)")
        return _reader_sb
    except Exception as e:
        log.debug("scoreboard_ocr: PaddleOCR unavailable (%s) — falling back to EasyOCR", e)

    # EasyOCR fallback — also CPU to save VRAM
    try:
        import easyocr  # type: ignore
        _reader_sb = easyocr.Reader(["en"], gpu=False, verbose=False)
    except Exception:
        import easyocr  # type: ignore
        _reader_sb = easyocr.Reader(["en"], gpu=False, verbose=False)
    _sb_use_paddle = False
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
        self._ocr_interval = _OCR_INTERVAL
        self._last_state: Dict = dict(_DEFAULT_STATE)
        # current_scan_result: None when no OCR ran this call (cached return),
        # True when OCR ran and found a shot clock, False when OCR ran but didn't.
        # Callers poll this after read() to drive non-live detection.
        self._current_scan_result: Optional[bool] = None
        # BUG 1+2 FIX: monotonic score enforcement — scores can never decrease.
        # -1 means "no valid score seen yet" (first real read will always be accepted).
        self._prev_home_score: int = -1
        self._prev_away_score: int = -1

    def configure(self, fps: float, stride: int = 1) -> None:
        """Set OCR cadence based on video fps and processing stride."""
        self._ocr_interval = max(15, int(fps / stride))

    @property
    def current_scan_result(self) -> Optional[bool]:
        """
        Whether the most recent actual OCR scan found a shot clock.

        Returns:
            None  — no OCR ran on this frame (cached return).
            True  — OCR ran and found a shot clock value.
            False — OCR ran but found no shot clock (possible non-live frame).
        """
        return self._current_scan_result

    def read(self, frame: np.ndarray) -> Dict:
        """
        Return game-state dict for this frame.

        Runs OCR every _OCR_INTERVAL frames; returns cached state otherwise.
        After each call, current_scan_result is set to None (cached) or
        True/False (actual scan result).

        Args:
            frame: BGR frame (already cropped by TOPCUT).

        Returns:
            Dict with all scoreboard keys. Unknown fields are -1.
        """
        self._frame_counter += 1
        if self._frame_counter % self._ocr_interval != 0:
            self._current_scan_result = None   # no OCR ran this call
            return dict(self._last_state)

        parsed = self._ocr_frame(frame)
        # Track whether this scan found a shot clock (before merging into cache)
        self._current_scan_result = (parsed.get("shot_clock", -1.0) != -1.0)

        # ── BUG 1+2 FIX: score validation before merging into cache ──────────
        raw_hs  = parsed.get("home_score", -1)
        raw_as_ = parsed.get("away_score", -1)

        # BUG 2: if BOTH parsed scores land in shot-clock range [1,24] this
        # frame, the parser almost certainly grabbed shot-clock digits as scores.
        # Discard both for this frame; do NOT update _prev_* counters.
        if (raw_hs != -1 and raw_as_ != -1
                and 1 <= raw_hs <= 24 and 1 <= raw_as_ <= 24):
            log.debug(
                "ScoreboardOCR frame %d: both scores in shot-clock range "
                "(%d, %d) — treating as shot-clock misread, discarding",
                self._frame_counter, raw_hs, raw_as_,
            )
            parsed["home_score"] = -1
            parsed["away_score"] = -1
        else:
            # BUG 1: monotonic enforcement — scores may only stay same or increase.
            if raw_hs != -1:
                if self._prev_home_score >= 0 and raw_hs < self._prev_home_score:
                    log.debug(
                        "ScoreboardOCR frame %d: home_score decreased %d→%d — "
                        "rejecting, keeping prev=%d",
                        self._frame_counter, self._prev_home_score, raw_hs,
                        self._prev_home_score,
                    )
                    parsed["home_score"] = -1   # suppress this read
                else:
                    self._prev_home_score = raw_hs

            if raw_as_ != -1:
                if self._prev_away_score >= 0 and raw_as_ < self._prev_away_score:
                    log.debug(
                        "ScoreboardOCR frame %d: away_score decreased %d→%d — "
                        "rejecting, keeping prev=%d",
                        self._frame_counter, self._prev_away_score, raw_as_,
                        self._prev_away_score,
                    )
                    parsed["away_score"] = -1   # suppress this read
                else:
                    self._prev_away_score = raw_as_
        # ─────────────────────────────────────────────────────────────────────

        # Merge — only overwrite fields that were successfully read this frame
        for k, v in parsed.items():
            if v not in (-1, -1.0):
                self._last_state[k] = v

        # Recompute score_diff from best known scores
        hs = self._last_state["home_score"]
        as_ = self._last_state["away_score"]
        # FIX 5: use None when scores are unknown (not 0 — that implies a tied game)
        self._last_state["score_diff"] = (hs - as_) if (hs >= 0 and as_ >= 0) else None

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
            if _sb_use_paddle:
                # PaddleOCR returns [[[bbox, (text, conf)], ...]] or None
                raw = reader.ocr(region, cls=False)
                lines = (raw[0] or []) if raw else []
                tokens = []
                for line in lines:
                    if line is None:
                        continue
                    try:
                        _, (text_tok, conf_tok) = line
                        if float(conf_tok) >= _OCR_CONF_MIN:
                            tokens.append(str(text_tok))
                    except (TypeError, ValueError):
                        continue
            else:
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

    # ── Period: Q1-Q4 / 1st-4th / FIRST-FOURTH / OT ─────────────────────
    # BUG 3 FIX: widened to handle broadcast variants:
    #   "Q1", "Q 1", "Q-1", "1st", "1 ST", "1ST", "1stQTR", "FIRST", "FOURTH"
    # Group layout: g1=Q-prefixed, g2=ordinal(digit), g3=ordinal(word), g4=OT
    period = re.search(
        r"Q[\s\-]?([1-4])(?:\b|ST|ND|RD|TH|QTR|QUARTER)"  # R8: Q1, Q1ST, Q1QTR stuck-together
        r"|\b([1-4])\s*(?:st|nd|rd|th)\b"         # 1st / 1 ST / 1stQTR
        r"|\b(FIRST|SECOND|THIRD|FOURTH)\b"        # spelled-out period names
        r"|\b(OT\d?)\b",                           # OT / OT1 / OT2
        text, re.IGNORECASE
    )
    _WORD_PERIOD = {"first": 1, "second": 2, "third": 3, "fourth": 4}
    if period:
        if period.group(4):                         # overtime
            state["period"] = 5
        elif period.group(3):                       # spelled-out word
            state["period"] = _WORD_PERIOD[period.group(3).lower()]
        else:
            state["period"] = int(period.group(1) or period.group(2))

    # ── Scores: two integers in NBA game-score range ──────────────────────
    # Two-pass approach: prefer the established [30, 175] window (avoids
    # clock/shot-clock digits) but fall back to [10, 175] when no pair is
    # found (early Q1 when both teams score < 30).  In both passes take the
    # first ordered pair in text order with diff ≤ 60.
    def _find_score_pair(cands):
        for _si, _a in enumerate(cands):
            for _b in cands[_si + 1:]:
                if abs(_a - _b) <= 60:
                    return _a, _b
        return None, None

    # Cap at 120: max realistic NBA score. Prevents shot clock (1-24) and game
    # clock digits from being mistaken for team scores.
    # R8: lowered floor 30→25 to accept late Q1/early Q2 broadcasts where both teams are in mid-20s
    _score_cands_30 = [int(m) for m in re.findall(r"\b(\d{1,3})\b", text) if 25 <= int(m) <= 175]
    _hs, _as = _find_score_pair(_score_cands_30)
    if _hs is None:
        # R8: fallback lowered 10→5 for early-game scores. Stays above shot-clock (1-24) and game-clock seconds tail digits.
        _score_cands_10 = [int(m) for m in re.findall(r"\b(\d{1,3})\b", text) if 5 <= int(m) <= 175]
        _hs, _as = _find_score_pair(_score_cands_10)
    if _hs is not None:
        state["home_score"] = _hs
        state["away_score"] = _as

    # ── Timeouts / fouls: require keyword context to avoid mixing stray digits
    # Pattern: look for labeled pairs like "HOME X ... AWAY Y" or just take
    # the first two standalone small integers that appear after a digit-free
    # region.  Fallback: original blind extraction if no label match.
    def _extract_labeled_pair(pattern: str, t: str, lo: int, hi: int):
        """Try labeled regex first; fall back to first two in-range digits."""
        m = re.search(pattern, t, re.IGNORECASE)
        if m:
            return int(m.group(1)), int(m.group(2))
        raw = [int(x) for x in re.findall(r"\b(\d)\b", t) if lo <= int(x) <= hi]
        return (raw[0], raw[1]) if len(raw) >= 2 else (None, None)

    _to_pat = (
        r"(?:home|team\s*a)[^\d]{0,10}([0-7])[^\d]{1,40}(?:away|team\s*b)[^\d]{0,10}([0-7])"
    )
    h_to, a_to = _extract_labeled_pair(_to_pat, text, 0, 7)
    if h_to is not None:
        state["home_timeouts"] = h_to
        state["away_timeouts"] = a_to

    _foul_pat = (
        r"(?:home|team\s*a)[^\d]{0,10}([0-6])[^\d]{1,40}(?:away|team\s*b)[^\d]{0,10}([0-6])"
    )
    h_f, a_f = _extract_labeled_pair(_foul_pat, text, 0, 6)
    if h_f is not None:
        state["home_fouls"] = h_f
        state["away_fouls"] = a_f

    return state

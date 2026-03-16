"""
player_identity.py — Multi-frame jersey number voting buffer.

Uses a sliding window of consecutive OCR reads per tracker slot to confirm
a jersey number only when the same digit appears CONFIRM_THRESHOLD times in
a row. This eliminates single-frame OCR noise.

Public API
----------
    CONFIRM_THRESHOLD       int — reads required to confirm a number (default 3)
    SAMPLE_EVERY_N          int — run OCR only every N frames (default 5)
    JerseyVotingBuffer      class — per-slot vote accumulator
    run_ocr_annotation_pass function — frame-level integration helper
"""

from __future__ import annotations

from collections import deque
from typing import Dict, Optional

import numpy as np

CONFIRM_THRESHOLD: int = 3   # identical consecutive reads needed to confirm
SAMPLE_EVERY_N: int = 5      # run OCR every N frames to save CPU


class JerseyVotingBuffer:
    """
    Per-slot sliding-window buffer for jersey number confirmation.

    Each tracker slot accumulates up to ``confirm_threshold`` consecutive
    OCR reads. When all reads in the window are identical non-None integers,
    that number is recorded as confirmed for the slot.

    Attributes:
        _votes:     Dict mapping slot → deque of recent reads (int or None)
        _confirmed: Dict mapping slot → confirmed jersey number (int)
    """

    def __init__(self, confirm_threshold: int = CONFIRM_THRESHOLD) -> None:
        """
        Initialise the voting buffer.

        Args:
            confirm_threshold: Number of identical consecutive reads required
                               before a jersey number is confirmed.
        """
        self._threshold: int = confirm_threshold
        self._votes: Dict[int, deque] = {}
        self._confirmed: Dict[int, int] = {}

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def record(self, slot: int, number: Optional[int]) -> None:
        """
        Record a single OCR read for a tracker slot.

        Appends ``number`` to the slot's deque (max length = confirm_threshold).
        If the deque is full and every entry is the same non-None integer,
        that integer is stored as the confirmed jersey number for the slot.

        Args:
            slot:   Tracker slot index (0-9 players, 10 referee).
            number: OCR result — an integer 0-99, or None if OCR failed.
        """
        if slot not in self._votes:
            self._votes[slot] = deque(maxlen=self._threshold)

        self._votes[slot].append(number)

        # Confirm only when the window is full and all entries agree
        dq = self._votes[slot]
        if len(dq) == self._threshold:
            first = dq[0]
            if first is not None and all(v == first for v in dq):
                self._confirmed[slot] = first

    def get_confirmed(self, slot: int) -> Optional[int]:
        """
        Return the confirmed jersey number for a slot, or None.

        Args:
            slot: Tracker slot index.

        Returns:
            Confirmed jersey number (int) or None if not yet confirmed.
        """
        return self._confirmed.get(slot, None)

    def reset_slot(self, slot: int) -> None:
        """
        Clear all vote history and confirmed state for a slot.

        Safe to call on a slot that has never been recorded.

        Args:
            slot: Tracker slot index to reset.
        """
        self._votes.pop(slot, None)
        self._confirmed.pop(slot, None)

    def all_confirmed(self) -> Dict[int, int]:
        """
        Return a shallow copy of all currently confirmed slot→jersey mappings.

        Returns:
            Dict[int, int]: {slot: jersey_number} for every confirmed slot.
        """
        return dict(self._confirmed)


# ─────────────────────────────────────────────────────────────────────────────
# Frame-level integration helper
# ─────────────────────────────────────────────────────────────────────────────

def run_ocr_annotation_pass(
    frame: np.ndarray,
    player_crops: Dict[int, np.ndarray],
    frame_index: int,
    buffer: JerseyVotingBuffer,
) -> Dict[int, Optional[int]]:
    """
    Run jersey OCR on all player crops for the current frame and update buffer.

    OCR is only executed when ``frame_index % SAMPLE_EVERY_N == 0`` to avoid
    redundant CPU/GPU work on every single frame. The confirmed mapping is
    returned regardless of whether OCR ran this frame.

    Args:
        frame:        Full BGR frame (not currently used but passed for future
                      context like shot-clock overlays).
        player_crops: Dict mapping tracker slot → BGR crop ndarray.
        frame_index:  Current frame counter (0-based).
        buffer:       Shared JerseyVotingBuffer instance to record reads into.

    Returns:
        Dict[int, Optional[int]]: {slot: confirmed_jersey_number_or_None}
        for every slot in player_crops.
    """
    from .jersey_ocr import read_jersey_number

    if frame_index % SAMPLE_EVERY_N == 0:
        for slot, crop in player_crops.items():
            number = read_jersey_number(crop)
            buffer.record(slot, number)

    # Return the current confirmed state for all provided slots
    return {slot: buffer.get_confirmed(slot) for slot in player_crops}

"""
player_identity.py — Multi-frame jersey number voting buffer.

Uses a sliding window of consecutive OCR reads per tracker slot to confirm
a jersey number only when the same digit appears CONFIRM_THRESHOLD times in
a row. This eliminates single-frame OCR noise.

Public API
----------
    CONFIRM_THRESHOLD       int — reads required to confirm a number (default 3)
    SAMPLE_EVERY_N          int — run OCR only every N frames (default 30)
    JerseyVotingBuffer      class — per-slot vote accumulator
    OCRWorker               class — async daemon that runs OCR off the main loop
    run_ocr_annotation_pass function — frame-level integration helper
"""

from __future__ import annotations

import queue
import threading
from collections import deque
from typing import Dict, Optional, Set

import numpy as np

CONFIRM_THRESHOLD: int = 3    # identical consecutive reads needed to confirm
SAMPLE_EVERY_N: int = 30      # run OCR every N frames — jersey numbers don't change mid-game


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
# Async OCR worker
# ─────────────────────────────────────────────────────────────────────────────

class OCRWorker:
    """
    Background daemon thread that runs jersey OCR off the main tracking loop.

    Usage::
        worker = OCRWorker()
        worker.enqueue(slot, crop_bgr)         # non-blocking; drop if full
        number = worker.get_result(slot)       # latest read (None if pending)
        worker.stop()                          # shut down (daemon dies on exit anyway)

    The worker processes ``(slot, crop_bgr)`` tuples from an input queue and
    writes results into a thread-safe output dict.  The queue has a bounded
    size so that if the main loop produces faster than the worker can consume,
    old un-processed crops are dropped (OCR is best-effort; confirmed jerseys
    are never re-queried).
    """

    _QUEUE_SIZE = 20  # max pending (slot, crop) items; older items dropped when full

    def __init__(self) -> None:
        self._in_q: queue.Queue = queue.Queue(maxsize=self._QUEUE_SIZE)
        self._results: Dict[int, Optional[int]] = {}
        self._results_lock = threading.Lock()
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def enqueue(self, slot: int, crop_bgr: np.ndarray) -> None:
        """
        Non-blocking enqueue of a crop for OCR.

        Silently drops the crop if the queue is full — the next frame will
        retry, and confirmed slots are never enqueued (see run_ocr_annotation_pass).

        Args:
            slot:     Tracker slot index.
            crop_bgr: BGR image crop to read the jersey number from.
        """
        try:
            self._in_q.put_nowait((slot, crop_bgr))
        except queue.Full:
            pass  # drop oldest work — OCR is best-effort

    def get_result(self, slot: int) -> Optional[int]:
        """
        Return the most recent OCR result for a slot (None if never read).

        Args:
            slot: Tracker slot index.

        Returns:
            int jersey number or None.
        """
        with self._results_lock:
            return self._results.get(slot, None)

    def stop(self) -> None:
        """Send sentinel to stop the worker thread (optional — daemon exits anyway)."""
        try:
            self._in_q.put_nowait(None)
        except queue.Full:
            pass

    # ── internal ──────────────────────────────────────────────────────────────

    def _worker_loop(self) -> None:
        """Continuously pop (slot, crop) pairs and run OCR."""
        from .jersey_ocr import read_jersey_number
        while True:
            item = self._in_q.get()
            if item is None:  # sentinel — shut down
                break
            slot, crop = item
            try:
                number = read_jersey_number(crop)
            except Exception:
                number = None
            with self._results_lock:
                self._results[slot] = number


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singletons
# ─────────────────────────────────────────────────────────────────────────────

_ocr_worker: Optional[OCRWorker] = None
_confirmed_slots: Set[int] = set()   # slots whose jersey number is already confirmed


def _get_ocr_worker() -> OCRWorker:
    """Return shared OCRWorker singleton (lazy-init)."""
    global _ocr_worker
    if _ocr_worker is None:
        _ocr_worker = OCRWorker()
    return _ocr_worker


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

    Optimisation 1 — confirmed-slot skip: once a slot's jersey number is
    confirmed, OCR is permanently skipped for that slot until reset_slot() is
    called.  Jersey numbers never change mid-game.

    Optimisation 2 — async worker: unconfirmed slots are enqueued to a
    background OCR daemon thread instead of blocking the main loop.  Results
    are read back from the worker's output dict each frame.

    OCR results are only enqueued when ``frame_index % SAMPLE_EVERY_N == 0``
    to avoid saturating the queue on consecutive frames.

    Args:
        frame:        Full BGR frame (not currently used but kept for future
                      context like shot-clock overlays).
        player_crops: Dict mapping tracker slot → BGR crop ndarray.
        frame_index:  Current frame counter (0-based).
        buffer:       Shared JerseyVotingBuffer instance to record reads into.

    Returns:
        Dict[int, Optional[int]]: {slot: confirmed_jersey_number_or_None}
        for every slot in player_crops.
    """
    worker = _get_ocr_worker()

    run_this_frame = (frame_index % SAMPLE_EVERY_N == 0)

    for slot, crop in player_crops.items():
        # Skip permanently if already confirmed (jersey numbers don't change)
        if slot in _confirmed_slots:
            continue

        # Check if the worker has a fresh result to record
        result = worker.get_result(slot)
        if result is not None:
            buffer.record(slot, result)

        # Check if this slot just became confirmed after recording
        confirmed = buffer.get_confirmed(slot)
        if confirmed is not None:
            _confirmed_slots.add(slot)
            continue

        # Enqueue OCR work for this frame (if it's an OCR frame)
        if run_this_frame and crop is not None and crop.size > 0:
            worker.enqueue(slot, crop)

    # Return the current confirmed state for all provided slots
    return {slot: buffer.get_confirmed(slot) for slot in player_crops}


def reset_confirmed_slot(slot: int, buffer: JerseyVotingBuffer) -> None:
    """
    Clear confirmed state for a slot — called when a tracker slot is evicted.

    Removes the slot from the module-level confirmed set and clears the buffer.

    Args:
        slot:   Tracker slot index.
        buffer: Shared JerseyVotingBuffer to clear.
    """
    _confirmed_slots.discard(slot)
    buffer.reset_slot(slot)

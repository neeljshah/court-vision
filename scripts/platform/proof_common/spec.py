"""sport-blind proof-harness (V1-V4) parameterized by a per-sport ProofSpec"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
import pandas as pd


@dataclass(frozen=True)
class EvalWindow:
    """One held-out evaluation window for V1 calibration.

    regime_note: None -> NO 'regime_note' key emitted (e.g. when no regime split
                 is applicable); "" or text -> the key IS emitted (some domains
                 emit for every window).
    """

    label: str
    seasons: List[int]
    regime_note: Optional[str] = None


@dataclass(frozen=True)
class ProofSpec:
    """Sport-blind parameterization of the V1-V4 honest proof harness (side A / side B convention).

    All sport-specific divergence is DATA here (columns, seasons, key names, note
    strings) or a small leaf callable copied verbatim from the original runner.
    Generic harness code carries ZERO sport tokens and ZERO sport-conditionals.

    Fields
    ------
    hyp_v1_name        : short name for V1 hypothesis (e.g. "V1-CALIBRATION")
    hyp_v1_statement   : full written statement of the V1 hypothesis
    hyp_v4_name        : short name for V4 hypothesis (e.g. "V4-PORTFOLIO")
    train_seasons      : seasons used for model training (not eval)
    eval_windows       : ordered list of held-out EvalWindow objects
    all_seasons        : union of train + all eval seasons in corpus order
    signal_defs        : V3 signal classes paired with their expected verdict string
    close_a_col        : column name for side-A closing probability in the market frame
    close_b_col        : column name for side-B closing probability in the market frame
    open_a_col         : column for side-A opening probability (None if open == close)
    open_b_col         : column for side-B opening probability (None if open == close)
    model_prob_col     : column name for the model's win-probability for side A
    market_brier_key   : key in the V1 result dict for the market Brier score
    market_beats_key   : key in the V1 result dict for the market-beats-model boolean
    v2_note            : verbatim note string emitted when CLV data is present
    v2_absent_note     : verbatim note string emitted when CLV data is absent
    v2_skip_note_fmt   : format string used when a single row is skipped in V2
    load_market_frame  : callable that loads the market / odds data frame (or None)
    outcome_market     : callable that extracts side-A outcome (float) from a row
    outcome_v4         : callable that extracts V4 outcome (int 0/1) from a row
    bundle_kwargs      : callable mapping an optional season tag to extra loader kwargs
    filter_v4_eval     : callable that filters the corpus frame to V4-eligible rows
    filter_v2_odds     : callable that filters the corpus frame to V2-eligible rows
    get_frames_v4      : callable returning (train_frame, eval_frame) for V4
    book_filename      : callable mapping an optional season tag to a filename string
    """

    # ---- identity / hypotheses -----------------------------------------------
    hyp_v1_name: str
    hyp_v1_statement: str
    hyp_v4_name: str

    # ---- season geometry -------------------------------------------------------
    train_seasons: List[int]
    eval_windows: List[EvalWindow]
    all_seasons: List[int]

    # ---- V3 signals: (Signal subclass, expected-verdict string) ----------------
    signal_defs: List[Tuple[type, str]]

    # ---- market geometry (side A / side B, sport-blind) -----------------------
    close_a_col: str
    close_b_col: str
    open_a_col: Optional[str]   # None,None -> open==close (no opening line available)
    open_b_col: Optional[str]
    model_prob_col: str

    # ---- V1 result-dict key names (exact-output parity with the originals) ----
    market_brier_key: str
    market_beats_key: str

    # ---- note strings (verbatim per domain) -----------------------------------
    v2_note: str
    v2_absent_note: str
    v2_skip_note_fmt: str

    # ---- leaf callables -------------------------------------------------------
    # Bodies live in the per-domain spec module; expressions are verbatim copies
    # of the logic from the original domain-specific runner.
    load_market_frame: Callable[..., Optional["pd.DataFrame"]]
    outcome_market: Callable[[Any], Optional[float]]
    outcome_v4: Callable[[Any], Optional[int]]
    bundle_kwargs: Callable[[Optional[str]], Dict[str, Any]]
    filter_v4_eval: Callable[..., "pd.DataFrame"]
    filter_v2_odds: Callable[..., "pd.DataFrame"]
    get_frames_v4: Callable[[Any], Tuple["pd.DataFrame", "pd.DataFrame"]]
    book_filename: Callable[[Optional[str]], str]

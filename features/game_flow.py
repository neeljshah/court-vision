"""
Game Flow Modeling

Computes momentum, scoring run probabilities, and comeback probability.
Extends existing momentum_snapshots with more granular flow metrics.
Triggered per possession, not per frame.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np


@dataclass
class GameFlowSnapshot:
    frame_number: int
    momentum_index: float
    scoring_run_probability: float
    possession_pressure_index: float
    comeback_probability: float
    offensive_flow_score: float


def compute_game_flow(
    possession_history: List[dict],
    current_frame: int,
    current_score_diff: int = 0,
    quarter: int = 2,
    possession_number: int = 0,
) -> GameFlowSnapshot:
    """
    Compute game flow metrics from recent possession history.

    Args:
        possession_history: List of recent possession outcome dicts
                            with keys: scored (bool), team, duration_frames.
        current_frame:      Current frame number.
        current_score_diff: Home - away score differential.
        quarter:            Current quarter (1-4).
        possession_number:  Possession count in this game.

    Returns:
        GameFlowSnapshot for this moment.
    """
    if not possession_history:
        return GameFlowSnapshot(current_frame, 0.5, 0.5, 0.5, 0.5, 0.5)

    recent = possession_history[-10:]  # last 10 possessions

    # Momentum: weighted scoring rate over recent possessions
    weights = np.exp(np.linspace(-2, 0, len(recent)))
    scores = np.array([1.0 if p.get("scored") else 0.0 for p in recent])
    momentum = float(np.average(scores, weights=weights))

    # Scoring run probability: if last 3 possessions all scored = high
    last_3 = [p.get("scored", False) for p in recent[-3:]]
    run_prob = sum(last_3) / max(len(last_3), 1)
    scoring_run_prob = min(0.3 + run_prob * 0.6, 0.95)

    # Possession pressure: how fast are possessions going?
    durations = [p.get("duration_frames", 90) for p in recent]
    avg_duration = float(np.mean(durations)) if durations else 90.0
    pressure = max(0, 1.0 - avg_duration / 180.0)  # 180 frames = 6s = low pressure

    # Comeback probability: based on score diff and time remaining
    quarters_remaining = max(0, 4 - quarter)
    possessions_remaining = max(1, quarters_remaining * 50 + 25)
    pts_per_possession = 1.1  # NBA average
    catchup_expected = possessions_remaining * pts_per_possession * 0.5
    comeback = float(max(0, min(1, 0.5 - current_score_diff / max(catchup_expected * 2, 1))))

    # Offensive flow: combination of scoring rate and pace
    flow = float(np.mean(scores) * 0.6 + (1.0 - pressure) * 0.4)

    return GameFlowSnapshot(
        frame_number=current_frame,
        momentum_index=momentum,
        scoring_run_probability=scoring_run_prob,
        possession_pressure_index=pressure,
        comeback_probability=comeback,
        offensive_flow_score=flow,
    )

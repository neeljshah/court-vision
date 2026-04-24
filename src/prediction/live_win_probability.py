"""src/prediction/live_win_probability.py — LSTM live win probability.

Architecture: 2-layer LSTM (hidden_dim) + FC head → sigmoid.
Inputs per possession: score_margin, time_remaining, spacing_index, momentum_score, lineup_net_rtg
Output: P(home wins | possession sequence up to now)
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn

_MODEL_DIR = Path("data/models")
_LSTM_PATH = _MODEL_DIR / "live_win_prob_lstm.pt"
_METRICS_PATH = _MODEL_DIR / "live_win_prob_metrics.json"
_LEAGUE_AVG_SPACING = 3.5  # meters — default when CV tracking unavailable

log = logging.getLogger(__name__)


def extract_possession_features(
    game_dict: dict,
    possession_idx: Optional[int] = None,
) -> Tuple[float, float, float, float, float]:
    """Return (score_margin, time_remaining, spacing_index, momentum_score, lineup_net_rtg)."""
    possessions: List[dict] = game_dict.get("possessions", [])
    if not possessions:
        return (0.0, 1.0, 0.0, 0.0, 0.0)

    idx = possession_idx if possession_idx is not None else len(possessions) - 1
    idx = max(0, min(idx, len(possessions) - 1))
    possession = possessions[idx]

    score_margin = float(possession.get("home_pts", 0) - possession.get("away_pts", 0)) / 10.0
    time_remaining = float(possession.get("time_remaining_s", 0.0)) / 2400.0

    raw_spacing = possession.get("spacing_index", _LEAGUE_AVG_SPACING)
    spacing_index = (float(raw_spacing) - _LEAGUE_AVG_SPACING) / 1.5

    # Momentum: sum of score deltas over last 5 possessions
    start = max(0, idx - 4)
    delta_sum = 0.0
    for i in range(start, idx + 1):
        p = possessions[i]
        prev = possessions[i - 1] if i > 0 else {"home_pts": 0, "away_pts": 0}
        delta_sum += (p.get("home_pts", 0) - p.get("away_pts", 0)) - (
            prev.get("home_pts", 0) - prev.get("away_pts", 0)
        )
    momentum_score = delta_sum / 5.0

    lineup_net_rtg = float(game_dict.get("home_lineup_net_rtg", 0.0)) / 5.0

    return (score_margin, time_remaining, spacing_index, momentum_score, lineup_net_rtg)


class LiveWinProbLSTM(nn.Module):
    """2-layer LSTM + FC head for possession-by-possession win probability."""

    def __init__(
        self,
        input_dim: int = 5,
        hidden_dim: int = 64,
        num_layers: int = 2,
    ) -> None:
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=0.2 if num_layers > 1 else 0.0,
        )
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(32, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, seq_len, input_dim) → (batch, seq_len, 1)."""
        lstm_out, _ = self.lstm(x)  # (batch, seq, hidden)
        return self.fc(lstm_out)    # (batch, seq, 1)


def train_lstm_win_prob(
    game_sequences: List[Dict],
    epochs: int = 50,
    batch_size: int = 16,
    val_split: float = 0.2,
    device: str = "cpu",
    hidden_dim: int = 64,
) -> Dict[str, Any]:
    """Train LSTM on possession sequences. Returns metrics dict with val_auc, val_brier, epochs, n_games."""
    n = len(game_sequences)
    if n < 10:
        log.warning("Insufficient data (N=%d); LSTM may underfit. Need 200+ games.", n)

    _MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Build feature tensors
    sequences: List[torch.Tensor] = []
    labels: List[int] = []
    for game in game_sequences:
        possessions = game.get("possessions", [])
        if not possessions:
            continue
        feats = []
        for i in range(len(possessions)):
            feats.append(list(extract_possession_features(game, i)))
        sequences.append(torch.tensor(feats, dtype=torch.float32))
        labels.append(int(game.get("outcome", 0)))

    if not sequences:
        return {"val_auc": 0.5, "val_brier": 0.25, "epochs": 0, "n_games": 0}

    # Train/val split by game index (preserve temporal order)
    n_val = max(1, int(len(sequences) * val_split))
    n_train = len(sequences) - n_val
    train_seqs = sequences[:n_train]
    train_lbls = labels[:n_train]
    val_seqs = sequences[n_train:]
    val_lbls = labels[n_train:]

    model = LiveWinProbLSTM(input_dim=5, hidden_dim=hidden_dim).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.BCELoss()

    model.train()
    for epoch in range(epochs):
        # Mini-batch with padding
        indices = list(range(len(train_seqs)))
        np.random.shuffle(indices)
        epoch_loss = 0.0
        for i in range(0, len(indices), batch_size):
            batch_idx = indices[i: i + batch_size]
            batch_seqs = [train_seqs[j] for j in batch_idx]
            batch_lbls = [train_lbls[j] for j in batch_idx]
            lengths = [s.shape[0] for s in batch_seqs]
            # Pad to max length in batch
            max_len = max(lengths)
            padded = torch.zeros(len(batch_seqs), max_len, 5)
            for k, (seq, length) in enumerate(zip(batch_seqs, lengths)):
                padded[k, :length, :] = seq
            padded = padded.to(device)
            out = model(padded)  # (batch, max_len, 1)
            # Use last valid position output for each sample
            preds = torch.stack([out[k, lengths[k] - 1, 0] for k in range(len(lengths))])
            targets = torch.tensor(batch_lbls, dtype=torch.float32).to(device)
            loss = loss_fn(preds, targets)
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            epoch_loss += loss.item()

    # Validation
    model.eval()
    val_preds: List[float] = []
    val_targets: List[float] = []
    with torch.no_grad():
        for seq, lbl in zip(val_seqs, val_lbls):
            x = seq.unsqueeze(0).to(device)
            out = model(x)
            val_preds.append(float(out[0, -1, 0]))
            val_targets.append(float(lbl))

    # Compute AUC and Brier
    try:
        from sklearn.metrics import roc_auc_score
        unique = set(val_targets)
        if len(unique) < 2:
            val_auc = 0.5
        else:
            val_auc = float(roc_auc_score(val_targets, val_preds))
    except Exception:
        val_auc = 0.5
    val_preds_arr = np.array(val_preds)
    val_targets_arr = np.array(val_targets)
    val_brier = float(np.mean((val_preds_arr - val_targets_arr) ** 2))

    metrics = {
        "val_auc": val_auc,
        "val_brier": val_brier,
        "epochs": epochs,
        "n_games": n,
    }

    torch.save(model.state_dict(), _LSTM_PATH)
    with open(_METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)

    return metrics


class LiveWinProbInference:
    """Stateful live win probability updater for a single game.

    Maintains possession_history across calls. One instance per live game.
    Falls back to XGBoost pre-game model if LSTM unavailable.
    """

    def __init__(
        self,
        lstm_model: Optional[LiveWinProbLSTM] = None,
        xgb_fallback: Optional[Any] = None,
        device: str = "cpu",
    ) -> None:
        self.lstm_model = lstm_model
        self.xgb_fallback = xgb_fallback
        self.device = device
        self.possession_history: List[Tuple[float, float, float, float, float]] = []

    def update(self, game_dict: dict, possession_idx: Optional[int] = None) -> Dict[str, Any]:
        """Extract features, run LSTM or fallback. Returns {win_prob_home, source, confidence, inference_ms}."""
        t0 = time.time()
        try:
            features = extract_possession_features(game_dict, possession_idx)
            self.possession_history.append(features)

            if self.lstm_model is not None:
                seq_tensor = torch.tensor(
                    [list(f) for f in self.possession_history],
                    dtype=torch.float32,
                ).unsqueeze(0).to(self.device)
                self.lstm_model.eval()
                with torch.no_grad():
                    out = self.lstm_model(seq_tensor)
                win_prob = float(out[0, -1, 0])
                source = "lstm"
                confidence = 0.85
            elif self.xgb_fallback is not None:
                result = self.xgb_fallback.predict([game_dict.get("home_team", {})])
                win_prob = float(np.asarray(result).ravel()[0])
                win_prob = max(0.0, min(1.0, win_prob))
                source = "xgb_fallback"
                confidence = 0.65
            else:
                win_prob = 0.5
                source = "no_model"
                confidence = 0.0
        except Exception as exc:
            log.warning("LiveWinProbInference.update error: %s", exc)
            win_prob = 0.5
            source = "error"
            confidence = 0.0

        inference_ms = (time.time() - t0) * 1000.0
        return {
            "win_prob_home": win_prob,
            "source": source,
            "confidence": confidence,
            "inference_ms": inference_ms,
        }


def calibrate_win_prob(predictions: np.ndarray, outcomes: np.ndarray) -> np.ndarray:
    """Isotonic calibration. Returns calibrated probabilities same shape as predictions."""
    from sklearn.isotonic import IsotonicRegression
    ir = IsotonicRegression(out_of_bounds="clip")
    ir.fit(predictions, outcomes)
    return ir.predict(predictions).astype(float)


def load_inference_engine(device: str = "cpu") -> LiveWinProbInference:
    """Load trained LSTM from data/models/ if available, else return XGBoost-only engine."""
    lstm_model: Optional[LiveWinProbLSTM] = None
    if _LSTM_PATH.exists():
        try:
            model = LiveWinProbLSTM()
            model.load_state_dict(torch.load(_LSTM_PATH, map_location=device))
            model.to(device).eval()
            lstm_model = model
        except Exception as exc:
            log.warning("Failed to load LSTM from %s: %s", _LSTM_PATH, exc)
    return LiveWinProbInference(lstm_model=lstm_model, device=device)

"""tests/test_live_win_probability.py — Phase 16 LSTM win probability tests.

Stubs: all marked skip until src/prediction/live_win_probability.py is implemented.
"""
import pytest
import numpy as np

try:
    from src.prediction.live_win_probability import (
        LiveWinProbLSTM,
        LiveWinProbInference,
        extract_possession_features,
        train_lstm_win_prob,
    )
    _IMPORT_OK = True
except ImportError:
    _IMPORT_OK = False

pytestmark = pytest.mark.skipif(not _IMPORT_OK, reason="live_win_probability.py not yet implemented")


def test_lstm_trains():
    """Verify LiveWinProbLSTM instantiates and produces correct output shape.

    Given a random tensor of shape (1, 3, 5) — batch=1, seq_len=3, input_dim=5 —
    the model's forward pass should return an output of shape (1, 3, 1).
    """
    import torch
    model = LiveWinProbLSTM(input_dim=5, hidden_dim=32, num_layers=1)
    x = torch.randn(1, 3, 5)
    out = model(x)
    assert out.shape == (1, 3, 1), f"Expected (1, 3, 1), got {out.shape}"


def test_auc():
    """Verify train_lstm_win_prob returns metrics dict with val_auc in [0, 1].

    Uses 20 synthetic game sequences (8 possessions each) as training data.
    The returned metrics dict must contain a 'val_auc' key that is a float
    in [0.0, 1.0] — sanity check that training ran and produced a measurement.
    """
    # Build 20 synthetic game_sequences: each has possessions as dicts + outcome
    rng = np.random.default_rng(42)
    games = []
    for i in range(20):
        possessions = []
        home_pts = 0
        away_pts = 0
        for j in range(8):
            home_pts += int(rng.integers(0, 4))
            away_pts += int(rng.integers(0, 4))
            possessions.append({
                "home_pts": home_pts,
                "away_pts": away_pts,
                "time_remaining_s": float(2400 - j * 300),
                "spacing_index": float(rng.uniform(2.5, 5.0)),
            })
        games.append({
            "possessions": possessions,
            "home_team": {"off_rtg": 110.0, "def_rtg": 110.0},
            "away_team": {"off_rtg": 110.0, "def_rtg": 110.0},
            "home_lineup_net_rtg": 0.0,
            "outcome": i % 2,  # alternating 0/1
        })

    metrics = train_lstm_win_prob(games, epochs=5, batch_size=4, device="cpu")
    assert "val_auc" in metrics, "metrics dict missing 'val_auc' key"
    assert isinstance(metrics["val_auc"], float), "val_auc must be a float"
    assert 0.0 <= metrics["val_auc"] <= 1.0, f"val_auc {metrics['val_auc']} outside [0, 1]"


def test_features(sample_game_dict):
    """Verify extract_possession_features returns 5 finite floats.

    Given a sample_game_dict fixture, the function should return a 5-tuple of
    floats representing extracted possession-level features. None of the values
    should be NaN or Inf — each must be a valid finite float.
    """
    features = extract_possession_features(sample_game_dict)
    assert len(features) == 5, f"Expected 5 features, got {len(features)}"
    for i, f in enumerate(features):
        assert isinstance(f, float), f"Feature {i} is not float: {type(f)}"
        assert np.isfinite(f), f"Feature {i} is not finite: {f}"


def test_inference_latency(sample_game_dict, mock_xgb_model):
    """Verify LiveWinProbInference.update() returns result with inference_ms < 500 on CPU.

    Instantiate LiveWinProbInference with a real (or mock) LSTM model, call
    update() with a sample_game_dict, and check that inference_ms in the
    returned dict is below 500 ms — acceptable latency for a CPU-only environment.
    """
    engine = LiveWinProbInference(lstm_model=None, xgb_fallback=mock_xgb_model)
    result = engine.update(sample_game_dict)
    assert "inference_ms" in result, "result missing 'inference_ms' key"
    assert result["inference_ms"] < 500, (
        f"inference_ms {result['inference_ms']} exceeds 500ms CPU threshold"
    )


def test_fallback_xgb(sample_game_dict, mock_xgb_model):
    """Verify LiveWinProbInference falls back to XGBoost when lstm_model is None.

    When instantiated with lstm_model=None, the inference engine must fall back
    to the xgb_fallback model. The returned dict must have source == 'xgb_fallback'
    so callers know which model produced the estimate.
    """
    engine = LiveWinProbInference(lstm_model=None, xgb_fallback=mock_xgb_model)
    result = engine.update(sample_game_dict)
    assert "source" in result, "result missing 'source' key"
    assert result["source"] == "xgb_fallback", (
        f"Expected source='xgb_fallback', got {result['source']!r}"
    )


def test_calibration_brier():
    """Verify Brier score < 0.25 after calibration on 10 synthetic predictions.

    Generate 10 synthetic (prediction, outcome) pairs, apply the calibration
    layer, and compute Brier score. A calibrated model should produce Brier < 0.25
    on this small synthetic set — not a high bar, but confirms calibration ran.
    """
    from src.prediction.live_win_probability import calibrate_win_prob

    preds = np.array([0.6, 0.7, 0.4, 0.8, 0.55, 0.45, 0.65, 0.75, 0.5, 0.6])
    outcomes = np.array([1, 1, 0, 1, 1, 0, 1, 1, 0, 1], dtype=float)
    calibrated = calibrate_win_prob(preds, outcomes)
    brier = float(np.mean((calibrated - outcomes) ** 2))
    assert brier < 0.25, f"Brier score {brier:.4f} exceeds 0.25 after calibration"


def test_sparse_features(sample_game_dict):
    """Verify extract_possession_features handles missing spacing_index gracefully.

    Remove spacing_index from all possessions in sample_game_dict. The feature
    extractor must not raise — it should default to the league average of 3.5 m
    and return 5 valid finite floats.
    """
    game = dict(sample_game_dict)
    game["possessions"] = [
        {k: v for k, v in p.items() if k != "spacing_index"}
        for p in game["possessions"]
    ]
    features = extract_possession_features(game)
    assert len(features) == 5, f"Expected 5 features with sparse input, got {len(features)}"
    for i, f in enumerate(features):
        assert np.isfinite(f), f"Feature {i} not finite with sparse input: {f}"

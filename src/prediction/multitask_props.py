"""
multitask_props.py — D-6: Multi-task player props model stub.

TODO: Implement PyTorch multi-task model.
  Requires: pip install torch torchvision

Architecture:
  Shared 128-dim player encoder → separate task heads per stat
  Stats: pts, reb, ast, fg3m, stl, blk, tov

Training:
  python src/prediction/multitask_props.py --train

Why:
  Shared encoder forces better player representation — pts and ast are
  correlated through usage. Especially valuable for low-sample players
  (<10 games) where single-task XGBoost overfits.

This stub is intentionally minimal. Full implementation requires:
  1. PyTorch installation
  2. Phase G 20 clean games for CV feature training
  3. Feature alignment between props features and CV tracking features
"""

from __future__ import annotations

import logging


class MultiTaskPropsModel:
    """
    D-6: Stub for PyTorch multi-task player prop model.

    TODO: Implement full training loop after Phase G and PyTorch installation.
    """

    STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
    HIDDEN_DIM = 128

    def __init__(self) -> None:
        self._model = None
        self._trained = False

    def train(self, X, y_dict: dict) -> "MultiTaskPropsModel":
        """
        TODO: Train shared encoder + per-stat task heads.

        Args:
            X:      Feature matrix (n_samples, n_features).
            y_dict: {stat: y_array} for each of 7 stats.
        """
        # BLOCKED: Phase G dependent. Requires PyTorch + 50+ game dataset.
        # Do not call until Phase G complete (20 clean games ingested + features.csv populated).
        raise NotImplementedError(
            "MultiTaskPropsModel.train() not yet implemented.\n"
            "Requires: pip install torch\n"
            "Implement: shared 128-dim encoder → per-stat heads\n"
            "See: src/prediction/multitask_props.py"
        )

    def predict(self, X, game_id: str = "") -> dict:
        """
        Fallback: delegate to PlayerPropsModel and return {stat: predicted_value}.
        Full multi-task implementation pending PyTorch installation and Phase G data.
        """
        logging.warning(
            "MultiTaskPropsModel not trained; falling back to PlayerPropsModel for game=%s",
            game_id,
        )
        try:
            from src.prediction.player_props import PlayerPropsModel
            _fallback = PlayerPropsModel()
            return _fallback.predict(X)
        except Exception as _e:
            return {stat: 0.0 for stat in self.STATS}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    args = ap.parse_args()
    if args.train:
        print("MultiTaskPropsModel training not yet implemented.")
        print("Install PyTorch and implement shared encoder architecture.")

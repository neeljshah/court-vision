"""multitask_mlp_live.py -- tier3-9 (loop 5).

Two-input multitask MLP for per-game prop predictions. Extends the cycle-23
multitask MLP architecture (currently AST/STL primary in prop_pergame) to
accept BOTH pre-game features AND a live half-state vector. Shared encoder
captures cross-stat structure; per-stat heads emit independent point
predictions for all 7 stats jointly.

Why
---
The cycle-23 multitask MLP only sees pre-game form/opponent/rest features.
At endQ3 we have a snapshot (current_pts, current_pf, score_margin, ...)
that conditions the rest-of-game distribution -- adding it as a second
input pathway opens room for the model to learn live conditioning the
heuristic projector (cycle 88+) can't capture jointly across stats.

Architecture
------------
    pregame (85)  -> Linear 256 -> ReLU -> Linear 128 -> ReLU -> Linear 64
    live    (15)  -> Linear 32  -> ReLU -> Linear 16
    concat (80)   -> per-stat Linear 1 (7 heads)

Loss: per-stat MSE on a per-stat-transformed target matrix (sqrt for PTS,
log1p for the rest -- identical scheme to prop_pergame.train_pergame_models).
Targets are emitted in transformed space and the trainer inverts before
metric eval.

Back-compat
-----------
Zero live input recovers the cycle-23 baseline behavior (the live_encoder's
output collapses to a fixed bias when input is zero, leaving stat heads
driven solely by the pre-game pathway). The ship gate requires the
zero-live-input prediction to match the standalone cycle-23 multitask MLP
within 0.005 MAE -- enforced by tests/test_multitask_mlp_live.py.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(PROJECT_DIR, "data", "models", "multitask_mlp_live.pt")
META_PATH = os.path.join(PROJECT_DIR, "data", "models", "multitask_mlp_live_meta.json")

# Stat order is FIXED -- artifact persistence depends on it. Matches
# prop_pergame.STATS so the proxy can slice by index.
STATS: Tuple[str, ...] = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# Per-stat target transform (matches prop_pergame contract).
_SQRT_HUBER_STATS = {"pts"}
_LOG_TRANSFORM_STATS = {"stl", "blk", "tov", "fg3m", "reb", "ast"}

# 15 live features per cycle-95c/94d snapshot schema.
LIVE_FEATURE_NAMES: Tuple[str, ...] = (
    "period", "clock_min_remaining", "period_share_played",
    "current_pts", "current_reb", "current_ast", "current_fg3m",
    "current_stl", "current_blk", "current_tov", "current_min", "current_pf",
    "score_margin", "foul_factor", "blow_factor",
)
LIVE_DIM = len(LIVE_FEATURE_NAMES)


# ── target transforms ────────────────────────────────────────────────────────

def _apply_target_transform(y: np.ndarray, stat: str) -> np.ndarray:
    """Forward per-stat transform (same as prop_pergame training pipeline)."""
    if stat in _SQRT_HUBER_STATS:
        return np.sqrt(np.clip(y, 0.0, None))
    if stat in _LOG_TRANSFORM_STATS:
        return np.log1p(np.clip(y, 0.0, None))
    return y


def _invert_target_transform(yt: np.ndarray, stat: str) -> np.ndarray:
    """Invert per-stat transform with non-negative clipping."""
    if stat in _SQRT_HUBER_STATS:
        return np.clip(yt, 0.0, None) ** 2
    if stat in _LOG_TRANSFORM_STATS:
        return np.clip(np.expm1(yt), 0.0, None)
    return yt


def build_target_matrix(rows: Sequence[Dict[str, Any]]) -> np.ndarray:
    """Apply per-stat transform across all STATS -> (n_rows, 7)."""
    Y = np.zeros((len(rows), len(STATS)), dtype=np.float32)
    for j, s in enumerate(STATS):
        ys = np.array([float(r.get(f"target_{s}", 0.0)) for r in rows],
                      dtype=np.float64)
        Y[:, j] = _apply_target_transform(ys, s).astype(np.float32)
    return Y


def build_live_vector(snapshot: Optional[Dict[str, Any]] = None) -> np.ndarray:
    """Build a 15-dim live feature vector from a snapshot dict (or zeros).

    Missing / None keys default to 0.0 -- the back-compat path: when no
    live snapshot is available, the live encoder receives a zero vector
    and the prediction collapses to the pre-game pathway.

    Snapshot keys (all optional):
      period, clock_min_remaining, period_share_played, current_{pts,reb,
      ast,fg3m,stl,blk,tov,min,pf}, score_margin, foul_factor, blow_factor.
    """
    out = np.zeros(LIVE_DIM, dtype=np.float32)
    if not snapshot:
        return out
    for i, name in enumerate(LIVE_FEATURE_NAMES):
        v = snapshot.get(name)
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f != f:  # NaN
            continue
        out[i] = f
    return out


# ── PyTorch model ────────────────────────────────────────────────────────────

class MultitaskMLPLive:
    """Two-input MLP: pregame encoder + live encoder -> 7 stat heads.

    The class is a thin wrapper around a small torch.nn.Module so callers
    don't need to import torch at module load time (prop_pergame avoids
    a hard torch dependency for back-compat with the existing sklearn-only
    training pipeline). torch is imported lazily in fit/predict/load.
    """

    def __init__(self, pregame_dim: int, live_dim: int = LIVE_DIM,
                 hidden_pregame: Tuple[int, ...] = (256, 128, 64),
                 hidden_live: Tuple[int, ...] = (32, 16),
                 seed: int = 42) -> None:
        self.pregame_dim = int(pregame_dim)
        self.live_dim = int(live_dim)
        self.hidden_pregame = tuple(hidden_pregame)
        self.hidden_live = tuple(hidden_live)
        self.seed = int(seed)
        self.module = None
        self.scaler_mean: Optional[np.ndarray] = None
        self.scaler_std: Optional[np.ndarray] = None
        self.live_mean: Optional[np.ndarray] = None
        self.live_std: Optional[np.ndarray] = None
        self.feature_names: List[str] = []
        self.stats: List[str] = list(STATS)
        self.train_history: Dict[str, Any] = {}

    # ── module construction ──────────────────────────────────────────────────

    def _build_module(self):
        import torch
        import torch.nn as nn

        pre_layers: List[nn.Module] = []
        in_dim = self.pregame_dim
        for h in self.hidden_pregame:
            pre_layers.append(nn.Linear(in_dim, h))
            pre_layers.append(nn.ReLU())
            in_dim = h
        live_layers: List[nn.Module] = []
        in_l = self.live_dim
        for h in self.hidden_live:
            live_layers.append(nn.Linear(in_l, h))
            live_layers.append(nn.ReLU())
            in_l = h
        pre_out_dim = self.hidden_pregame[-1]
        live_out_dim = self.hidden_live[-1]
        concat_dim = pre_out_dim + live_out_dim
        heads = nn.ModuleList([
            nn.Linear(concat_dim, 1) for _ in self.stats
        ])

        class _Mod(nn.Module):
            def __init__(mod):
                super().__init__()
                mod.pre = nn.Sequential(*pre_layers)
                mod.live = nn.Sequential(*live_layers)
                mod.heads = heads

            def forward(mod, x_pre, x_live):
                e_pre = mod.pre(x_pre)
                e_live = mod.live(x_live)
                z = torch.cat([e_pre, e_live], dim=1)
                outs = [head(z) for head in mod.heads]
                return torch.cat(outs, dim=1)

        torch.manual_seed(self.seed)
        self.module = _Mod()
        return self.module

    # ── training ─────────────────────────────────────────────────────────────

    def fit(self, X_pre: np.ndarray, X_live: np.ndarray, Y: np.ndarray,
            *, X_pre_val: Optional[np.ndarray] = None,
            X_live_val: Optional[np.ndarray] = None,
            Y_val: Optional[np.ndarray] = None,
            epochs: int = 60, batch_size: int = 512,
            lr: float = 1e-3, weight_decay: float = 1e-4,
            patience: int = 8) -> "MultitaskMLPLive":
        """Train with Adam + early stopping on val MAE (transformed-space)."""
        import torch
        import torch.nn as nn

        X_pre = np.asarray(X_pre, dtype=np.float32)
        X_live = np.asarray(X_live, dtype=np.float32)
        Y = np.asarray(Y, dtype=np.float32)
        if X_pre.shape[0] != X_live.shape[0] or X_pre.shape[0] != Y.shape[0]:
            raise ValueError("X_pre / X_live / Y row counts must match")
        if X_pre.shape[1] != self.pregame_dim:
            raise ValueError(
                f"X_pre dim {X_pre.shape[1]} != pregame_dim {self.pregame_dim}")
        if X_live.shape[1] != self.live_dim:
            raise ValueError(
                f"X_live dim {X_live.shape[1]} != live_dim {self.live_dim}")
        if Y.shape[1] != len(self.stats):
            raise ValueError(
                f"Y has {Y.shape[1]} cols, expected {len(self.stats)}")

        # Fit pregame scaler (StandardScaler-equivalent).
        self.scaler_mean = X_pre.mean(axis=0).astype(np.float32)
        self.scaler_std = X_pre.std(axis=0).astype(np.float32)
        self.scaler_std[self.scaler_std < 1e-6] = 1.0
        Xp = (X_pre - self.scaler_mean) / self.scaler_std
        # Live scaler -- only on rows with non-zero live input (so the
        # zero-vector back-compat path stays at the centred origin).
        live_active_mask = (X_live.sum(axis=1) != 0.0)
        if live_active_mask.sum() > 16:
            active = X_live[live_active_mask]
            self.live_mean = active.mean(axis=0).astype(np.float32)
            self.live_std = active.std(axis=0).astype(np.float32)
            self.live_std[self.live_std < 1e-6] = 1.0
        else:
            self.live_mean = np.zeros(self.live_dim, dtype=np.float32)
            self.live_std = np.ones(self.live_dim, dtype=np.float32)
        Xl = self._scale_live(X_live)

        self._build_module()
        loss_fn = nn.MSELoss()
        opt = torch.optim.Adam(self.module.parameters(),
                               lr=lr, weight_decay=weight_decay)

        Xp_t = torch.from_numpy(Xp)
        Xl_t = torch.from_numpy(Xl)
        Y_t = torch.from_numpy(Y)

        if X_pre_val is not None and Y_val is not None:
            Xpv = (np.asarray(X_pre_val, dtype=np.float32) - self.scaler_mean) / self.scaler_std
            Xlv = self._scale_live(
                np.asarray(X_live_val, dtype=np.float32)
                if X_live_val is not None
                else np.zeros((len(X_pre_val), self.live_dim), dtype=np.float32))
            Yv_t = torch.from_numpy(np.asarray(Y_val, dtype=np.float32))
            Xpv_t = torch.from_numpy(Xpv)
            Xlv_t = torch.from_numpy(Xlv)
        else:
            Xpv_t = Xlv_t = Yv_t = None

        n = Xp_t.shape[0]
        best_val = float("inf")
        best_state = None
        patience_left = patience
        history: List[Dict[str, float]] = []
        for epoch in range(epochs):
            self.module.train()
            perm = torch.randperm(n)
            running = 0.0
            for i in range(0, n, batch_size):
                idx = perm[i:i + batch_size]
                opt.zero_grad()
                pred = self.module(Xp_t[idx], Xl_t[idx])
                loss = loss_fn(pred, Y_t[idx])
                loss.backward()
                opt.step()
                running += float(loss.item()) * idx.numel()
            train_loss = running / n
            entry = {"epoch": epoch, "train_loss": train_loss}
            if Xpv_t is not None:
                self.module.eval()
                with torch.no_grad():
                    pv = self.module(Xpv_t, Xlv_t)
                    val_mae = float(torch.mean(torch.abs(pv - Yv_t)).item())
                entry["val_mae"] = val_mae
                if val_mae < best_val - 1e-5:
                    best_val = val_mae
                    best_state = {k: v.detach().clone()
                                  for k, v in self.module.state_dict().items()}
                    patience_left = patience
                else:
                    patience_left -= 1
                    if patience_left <= 0:
                        history.append(entry)
                        break
            history.append(entry)
        if best_state is not None:
            self.module.load_state_dict(best_state)
        self.train_history = {"history": history,
                              "best_val_mae": best_val if best_val != float("inf") else None}
        return self

    # ── inference ────────────────────────────────────────────────────────────

    def _scale_pre(self, X_pre: np.ndarray) -> np.ndarray:
        if self.scaler_mean is None or self.scaler_std is None:
            return X_pre
        return (X_pre - self.scaler_mean) / self.scaler_std

    def _scale_live(self, X_live: np.ndarray) -> np.ndarray:
        if self.live_mean is None or self.live_std is None:
            return X_live
        # Zero rows stay zero post-scale (so back-compat path is preserved
        # IFF the scaler hasn't shifted the origin); otherwise the live
        # pathway sees centred inputs.
        scaled = (X_live - self.live_mean) / self.live_std
        zero_mask = (X_live.sum(axis=1) == 0.0)
        scaled[zero_mask] = 0.0
        return scaled

    def predict(self, X_pre: np.ndarray, X_live: Optional[np.ndarray] = None,
                *, invert: bool = True) -> np.ndarray:
        """Predict 7-dim output for each row.

        When invert=True (default), per-stat target transforms are
        inverted -> raw-count scale matching prop_pergame's contract.
        invert=False returns transformed-space output (useful for the
        zero-input back-compat tolerance check that compares against the
        independent cycle-23 multitask MLP's transformed-space output).
        """
        import torch
        X_pre = np.asarray(X_pre, dtype=np.float32)
        if X_pre.ndim == 1:
            X_pre = X_pre.reshape(1, -1)
        if X_live is None:
            X_live = np.zeros((X_pre.shape[0], self.live_dim), dtype=np.float32)
        else:
            X_live = np.asarray(X_live, dtype=np.float32)
            if X_live.ndim == 1:
                X_live = X_live.reshape(1, -1)
        Xp = self._scale_pre(X_pre).astype(np.float32)
        Xl = self._scale_live(X_live).astype(np.float32)
        self.module.eval()
        with torch.no_grad():
            out_t = self.module(
                torch.from_numpy(Xp), torch.from_numpy(Xl)
            ).detach().cpu().numpy()
        if not invert:
            return out_t
        # Invert per-stat transform column-wise.
        out = np.zeros_like(out_t, dtype=np.float32)
        for j, s in enumerate(self.stats):
            out[:, j] = _invert_target_transform(out_t[:, j].astype(np.float64),
                                                  s).astype(np.float32)
        return out

    def predict_one(self, pregame_row: Sequence[float],
                    snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
        """Predict a single row -> {stat: raw_count_pred} dict."""
        X_pre = np.asarray(pregame_row, dtype=np.float32).reshape(1, -1)
        X_live = build_live_vector(snapshot).reshape(1, -1)
        out = self.predict(X_pre, X_live)[0]
        return {s: float(out[j]) for j, s in enumerate(self.stats)}

    # ── persistence ──────────────────────────────────────────────────────────

    def save(self, model_path: str = MODEL_PATH,
             meta_path: str = META_PATH) -> None:
        if self.module is None:
            raise RuntimeError("save called before fit")
        import torch
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        torch.save(self.module.state_dict(), model_path)
        meta = {
            "pregame_dim": self.pregame_dim,
            "live_dim": self.live_dim,
            "hidden_pregame": list(self.hidden_pregame),
            "hidden_live": list(self.hidden_live),
            "seed": self.seed,
            "feature_names": list(self.feature_names),
            "stats": list(self.stats),
            "scaler_mean": self.scaler_mean.tolist() if self.scaler_mean is not None else None,
            "scaler_std": self.scaler_std.tolist() if self.scaler_std is not None else None,
            "live_mean": self.live_mean.tolist() if self.live_mean is not None else None,
            "live_std": self.live_std.tolist() if self.live_std is not None else None,
            "train_history": {
                "best_val_mae": self.train_history.get("best_val_mae"),
                "n_epochs_completed": len(self.train_history.get("history", []) or []),
            },
        }
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)

    @classmethod
    def load(cls, model_path: str = MODEL_PATH,
             meta_path: str = META_PATH) -> Optional["MultitaskMLPLive"]:
        if not os.path.exists(model_path) or not os.path.exists(meta_path):
            return None
        try:
            import torch
            with open(meta_path, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
            inst = cls(
                pregame_dim=int(meta["pregame_dim"]),
                live_dim=int(meta.get("live_dim", LIVE_DIM)),
                hidden_pregame=tuple(meta.get("hidden_pregame", (256, 128, 64))),
                hidden_live=tuple(meta.get("hidden_live", (32, 16))),
                seed=int(meta.get("seed", 42)),
            )
            inst.stats = list(meta.get("stats", STATS))
            inst.feature_names = list(meta.get("feature_names", []))
            inst._build_module()
            inst.module.load_state_dict(torch.load(model_path, map_location="cpu"))
            sm = meta.get("scaler_mean")
            sd = meta.get("scaler_std")
            lm = meta.get("live_mean")
            ls = meta.get("live_std")
            inst.scaler_mean = np.array(sm, dtype=np.float32) if sm is not None else None
            inst.scaler_std = np.array(sd, dtype=np.float32) if sd is not None else None
            inst.live_mean = np.array(lm, dtype=np.float32) if lm is not None else None
            inst.live_std = np.array(ls, dtype=np.float32) if ls is not None else None
            return inst
        except Exception:
            return None


# Cycle 89f T3-A opt-in flag. Default OFF -- the artifact must ship the
# back-compat test AND a probe win before flipping this. predict_pergame
# checks the flag and dispatches per-stat when True; absent flag = legacy.
_USE_MULTITASK_MLP_LIVE = False


__all__ = [
    "LIVE_DIM",
    "LIVE_FEATURE_NAMES",
    "MODEL_PATH",
    "META_PATH",
    "MultitaskMLPLive",
    "STATS",
    "build_live_vector",
    "build_target_matrix",
    "_USE_MULTITASK_MLP_LIVE",
]

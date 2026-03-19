"""Abstract base for all NBA AI sklearn models.

Every model must implement fit() and predict(). Models are persisted
with joblib to models/artifacts/{model_name}.joblib.
"""

import pathlib
from abc import ABC, abstractmethod

import joblib

ARTIFACTS_DIR = pathlib.Path(__file__).parent / "artifacts"


class BaseModel(ABC):
    """Minimal contract every Phase 3 model must satisfy.

    Subclasses are expected to wrap a sklearn estimator and expose
    a predict() method returning Python native types (float, dict, list)
    so Phase 4 API can JSON-serialize results without extra conversion.
    """

    model_name: str  # override in subclass, used as artifact filename

    @abstractmethod
    def fit(self, df) -> "BaseModel":
        """Train on a pandas DataFrame. Returns self for chaining."""

    @abstractmethod
    def predict(self, features: dict) -> object:
        """Score a single observation dict. Returns JSON-serializable value."""

    def save(self) -> pathlib.Path:
        """Serialize model to models/artifacts/{model_name}.joblib."""
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        path = ARTIFACTS_DIR / f"{self.model_name}.joblib"
        joblib.dump(self, path)
        return path

    @classmethod
    def load(cls, model_name: str) -> "BaseModel":
        """Deserialize model from models/artifacts/{model_name}.joblib."""
        path = ARTIFACTS_DIR / f"{model_name}.joblib"
        if not path.exists():
            raise FileNotFoundError(
                f"No artifact at {path}. Run training first."
            )
        return joblib.load(path)

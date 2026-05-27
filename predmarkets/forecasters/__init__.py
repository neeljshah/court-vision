"""Category-specific forecasters for the EdgeScanner."""

from .crypto_threshold import CryptoThresholdForecaster
from .llm_forecaster import LLMForecaster

__all__ = ["CryptoThresholdForecaster", "LLMForecaster"]

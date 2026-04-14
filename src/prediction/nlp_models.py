"""
nlp_models.py — Phase 9: NLP Models (M66–M69)

Four lightweight NLP models for injury and sentiment signals.
Uses sklearn TF-IDF + LogisticRegression (no GPU required).

Models
------
    InjurySeverityClassifier (M66)  — injury text → severity score 0–1
    InjuryLagModel           (M67)  — tweet→line-move timestamp delta predictor
    TeamSentimentModel       (M68)  — rolling sentiment from text inputs
    ReporterCredibilityRanker(M69)  — per-reporter accuracy score

Public API
----------
    InjurySeverityClassifier.predict(text)     -> float
    InjurySeverityClassifier.train(examples)   -> dict
    InjuryLagModel.predict(reporter, severity) -> dict
    TeamSentimentModel.score(texts)            -> float
    ReporterCredibilityRanker.rank(handle)     -> float
"""
from __future__ import annotations

import json
import os
import pickle
import sys
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models")

# ── Seed training data for injury severity ────────────────────────────────────
# Label: 0 = minor/probable, 0.5 = questionable, 1.0 = out/DNP
_SEVERITY_SEED: list[tuple[str, float]] = [
    ("out ankle", 1.0), ("ruled out knee", 1.0), ("will not play tonight", 1.0),
    ("DNP knee", 1.0), ("out indefinitely", 1.0), ("season ending surgery", 1.0),
    ("questionable hamstring", 0.5), ("game-time decision back", 0.5),
    ("day-to-day shoulder", 0.5), ("limited practice knee", 0.5),
    ("questionable ankle", 0.5), ("probable ankle", 0.3),
    ("probable back", 0.3), ("full practice", 0.0),
    ("no injury designation", 0.0), ("available to play", 0.0),
    ("cleared to return", 0.0), ("healthy", 0.0),
    ("will play tonight", 0.0), ("no restrictions", 0.0),
]

# Lag model defaults (minutes) per reporter tier
_LAG_DEFAULTS = {
    "tier1": {"min": 5,  "median": 15,  "max": 45},   # Woj/Shams
    "tier2": {"min": 15, "median": 45,  "max": 120},  # beat reporters
    "tier3": {"min": 30, "median": 90,  "max": 240},  # aggregators
}

# Credibility tiers
_TIER1_HANDLES = {"wojespn", "shamscharania", "adrianwojnarowski", "shams", "wojnba"}
_TIER2_HANDLES = {"ianbegg", "davidaldridgenba", "markstein", "cbssports"}


# ── M66: Injury Severity Classifier ──────────────────────────────────────────

class InjurySeverityClassifier:
    """
    Sklearn TF-IDF + LogisticRegression classifier for injury report severity.

    Input:  injury report text string (e.g. "questionable ankle")
    Output: severity score 0–1  (0 = healthy, 1 = out/DNP)
    """

    _MODEL_PATH = os.path.join(_MODELS_DIR, "injury_severity_clf.pkl")

    def __init__(self) -> None:
        self._pipeline = None

    def _load_or_train(self) -> None:
        if self._pipeline is not None:
            return
        if os.path.exists(self._MODEL_PATH):
            try:
                with open(self._MODEL_PATH, "rb") as f:
                    self._pipeline = pickle.load(f)
                return
            except Exception:
                pass
        self.train()

    def train(self, examples: Optional[list[tuple[str, float]]] = None) -> dict:
        """
        Train classifier on (text, severity) pairs.

        Args:
            examples: List of (text, score) tuples. Defaults to seed data.

        Returns:
            {"n_samples": int, "accuracy": float}
        """
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline

        data = examples or _SEVERITY_SEED
        texts  = [t for t, _ in data]
        # Discretize to 3 classes: low (<0.3), medium (0.3–0.7), high (>0.7)
        labels = [_severity_label(s) for _, s in data]

        pipe = Pipeline([
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=5000)),
            ("clf",   LogisticRegression(C=1.0, max_iter=500, multi_class="auto")),
        ])
        pipe.fit(texts, labels)

        # Simple accuracy on training data (small seed — no holdout split)
        preds = pipe.predict(texts)
        acc   = sum(p == l for p, l in zip(preds, labels)) / len(labels)

        self._pipeline = pipe
        os.makedirs(_MODELS_DIR, exist_ok=True)
        with open(self._MODEL_PATH, "wb") as f:
            pickle.dump(pipe, f)

        return {"n_samples": len(data), "accuracy": round(acc, 4)}

    def predict(self, text: str) -> float:
        """
        Predict injury severity score for a text string.

        Returns:
            float in [0, 1]  (0 = healthy, 1 = out/DNP)
        """
        self._load_or_train()
        if self._pipeline is None:
            return 0.5

        label = self._pipeline.predict([text])[0]
        proba = self._pipeline.predict_proba([text])[0]
        classes = list(self._pipeline.classes_)

        # Map class probabilities to 0–1 severity score
        score = 0.0
        for cls, p in zip(classes, proba):
            if cls == "low":
                score += 0.1 * p
            elif cls == "medium":
                score += 0.5 * p
            elif cls == "high":
                score += 1.0 * p
        return round(score, 4)


def _severity_label(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.3:
        return "medium"
    return "low"


# ── M67: Injury Lag Model ─────────────────────────────────────────────────────

class InjuryLagModel:
    """
    Timestamp delta predictor: beat reporter tweet → Pinnacle line move.

    Quantifies the reaction window available before books adjust.
    """

    def predict(self, reporter_handle: str, severity: float) -> dict:
        """
        Predict the lag window (minutes) between a reporter's tweet and line move.

        Args:
            reporter_handle: Twitter/X handle (e.g. "wojespn")
            severity:        Severity score from InjurySeverityClassifier (0–1)

        Returns:
            {"tier": str, "lag_min": int, "lag_median": int, "lag_max": int,
             "window_minutes": int}
        """
        handle = reporter_handle.lower().strip("@").strip()
        if handle in _TIER1_HANDLES:
            tier = "tier1"
        elif handle in _TIER2_HANDLES:
            tier = "tier2"
        else:
            tier = "tier3"

        defaults = _LAG_DEFAULTS[tier].copy()

        # High severity → faster market reaction → smaller window
        severity_factor = max(0.5, 1.0 - 0.4 * severity)
        window = int(defaults["median"] * severity_factor)

        return {
            "tier":           tier,
            "lag_min":        defaults["min"],
            "lag_median":     defaults["median"],
            "lag_max":        defaults["max"],
            "window_minutes": window,
        }


# ── M68: Team Sentiment Model ─────────────────────────────────────────────────

class TeamSentimentModel:
    """
    Rolling sentiment scorer from post-game interview text or Reddit threads.

    Uses VADER-style lexicon scoring (no external dependency).
    Positive words increase score; negative words decrease it.
    """

    # Minimal sentiment lexicon (expandable)
    _POS = {"great", "excellent", "win", "strong", "confident", "motivated",
            "impressive", "dominant", "healthy", "focused", "chemistry", "energy"}
    _NEG = {"lose", "frustrated", "bad", "tired", "injured", "struggle",
            "conflict", "tension", "benched", "trade", "rumor", "disappointed"}

    def __init__(self) -> None:
        self._history: list[float] = []

    def score(self, texts: list[str]) -> float:
        """
        Compute aggregate sentiment score for a list of text inputs.

        Returns:
            float in [-1, 1] where 1 = very positive, -1 = very negative
        """
        if not texts:
            return 0.0
        scores = [self._score_single(t) for t in texts]
        result = sum(scores) / len(scores)
        self._history.append(result)
        return round(result, 4)

    def rolling_sentiment(self, window: int = 5) -> float:
        """Return rolling average sentiment over last N games."""
        recent = self._history[-window:] if self._history else [0.0]
        return round(sum(recent) / len(recent), 4)

    def _score_single(self, text: str) -> float:
        words = set(text.lower().split())
        pos   = len(words & self._POS)
        neg   = len(words & self._NEG)
        total = pos + neg
        if total == 0:
            return 0.0
        return (pos - neg) / total


# ── M69: Reporter Credibility Ranker ─────────────────────────────────────────

class ReporterCredibilityRanker:
    """
    Accuracy score per reporter_id from historical data.

    Wraps beat_reporter_credibility.py with a ranking interface.
    """

    def rank(self, handle: str) -> float:
        """
        Return credibility score (0–1) for a reporter handle.

        Higher = more reliable injury alerts.
        """
        try:
            from src.prediction.beat_reporter_credibility import get_reporter_credibility
            return get_reporter_credibility(handle)
        except Exception:
            pass
        # Fallback tier lookup
        h = handle.lower().strip("@").strip()
        if h in _TIER1_HANDLES:
            return 0.91
        if h in _TIER2_HANDLES:
            return 0.78
        return 0.65

    def rank_batch(self, handles: list[str]) -> dict[str, float]:
        """Return {handle: credibility} for a list of reporters, sorted descending."""
        scores = {h: self.rank(h) for h in handles}
        return dict(sorted(scores.items(), key=lambda x: x[1], reverse=True))

    def top_n(self, handles: list[str], n: int = 3) -> list[tuple[str, float]]:
        """Return top-N most credible reporters from a list."""
        ranked = self.rank_batch(handles)
        return list(ranked.items())[:n]


if __name__ == "__main__":
    clf    = InjurySeverityClassifier()
    lag    = InjuryLagModel()
    sent   = TeamSentimentModel()
    ranker = ReporterCredibilityRanker()

    clf.train()
    texts = ["out ankle", "questionable hamstring", "cleared to return"]
    for t in texts:
        print(f"  severity({t!r}) = {clf.predict(t):.3f}")

    print(lag.predict("wojespn", severity=0.9))
    print(sent.score(["great win, team is healthy and focused",
                       "struggled tonight, injuries hurt us"]))
    print(ranker.top_n(["wojespn", "ianbegg", "randomguy123"], n=3))

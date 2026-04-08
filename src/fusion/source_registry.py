"""
Fusion layer: source registry, priority tiers, and SourceValue container.

Confidence scale (0-1):
  1.0  CV-derived with high OCR + color match
  0.85 NBA official box score API
  0.70 CV-derived with low OCR conf
  0.55 Scraped / third-party (SBR, injury PDF)
  0.40 Synergy / estimated / prior-only
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Any, Optional


class SourceTier(IntEnum):
    """Priority tier — higher wins when reconciling conflicts."""
    CV_HIGH       = 5   # CV track + high OCR confidence
    NBA_OFFICIAL  = 4   # NBA Stats API box score
    CV_LOW        = 3   # CV track + low OCR confidence
    SCRAPED       = 2   # Third-party scrape (SBR, injury PDF)
    PRIOR         = 1   # Statistical prior / estimate only


# Map source string labels -> tier (used in stat_reconciler)
SOURCE_PRIORITY: dict[str, SourceTier] = {
    "cv_high":      SourceTier.CV_HIGH,
    "nba_api":      SourceTier.NBA_OFFICIAL,
    "cv_low":       SourceTier.CV_LOW,
    "scraped":      SourceTier.SCRAPED,
    "prior":        SourceTier.PRIOR,
    # Aliases
    "boxscore":     SourceTier.NBA_OFFICIAL,
    "gamelog":      SourceTier.NBA_OFFICIAL,
    "synergy":      SourceTier.SCRAPED,
    "injury_pdf":   SourceTier.SCRAPED,
    "vegas":        SourceTier.SCRAPED,
    "rest_travel":  SourceTier.NBA_OFFICIAL,   # derived from official schedule
    "refs":         SourceTier.NBA_OFFICIAL,
    "spatial_prior": SourceTier.PRIOR,
}

# Default confidence per source (used when caller doesn't supply one)
SOURCE_DEFAULT_CONFIDENCE: dict[str, float] = {
    "cv_high":      1.00,
    "nba_api":      0.85,
    "boxscore":     0.85,
    "gamelog":      0.85,
    "rest_travel":  0.85,
    "refs":         0.85,
    "cv_low":       0.70,
    "synergy":      0.55,
    "scraped":      0.55,
    "vegas":        0.55,
    "injury_pdf":   0.55,
    "prior":        0.40,
    "spatial_prior": 0.40,
}


@dataclass
class SourceValue:
    """Single observation of a stat/feature from one data source."""

    value: Any
    source: str                          # key into SOURCE_PRIORITY
    confidence: float                    # 0-1; see scale above
    ts: Optional[datetime] = field(default=None)  # when observation was made
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0,1], got {self.confidence}")
        if self.source not in SOURCE_PRIORITY:
            raise ValueError(
                f"Unknown source '{self.source}'. Add to SOURCE_PRIORITY first."
            )
        if self.ts is None:
            self.ts = datetime.utcnow()

    @property
    def tier(self) -> SourceTier:
        return SOURCE_PRIORITY[self.source]

    def __lt__(self, other: "SourceValue") -> bool:
        """Lower confidence = lower priority (useful for sorted/heapq)."""
        return (self.tier, self.confidence) < (other.tier, other.confidence)

    @classmethod
    def from_nba_api(cls, value: Any, **meta: Any) -> "SourceValue":
        return cls(
            value=value,
            source="nba_api",
            confidence=SOURCE_DEFAULT_CONFIDENCE["nba_api"],
            meta=meta,
        )

    @classmethod
    def from_cv(cls, value: Any, ocr_conf: float, **meta: Any) -> "SourceValue":
        source = "cv_high" if ocr_conf >= 0.75 else "cv_low"
        conf = SOURCE_DEFAULT_CONFIDENCE[source] * ocr_conf
        conf = round(max(0.05, min(1.0, conf)), 4)
        return cls(value=value, source=source, confidence=conf, meta=meta)

    @classmethod
    def as_prior(cls, value: Any, **meta: Any) -> "SourceValue":
        return cls(
            value=value,
            source="prior",
            confidence=SOURCE_DEFAULT_CONFIDENCE["prior"],
            meta=meta,
        )

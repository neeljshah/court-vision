"""Fail-closed contract for features used by shipped live models.

Live inference may use only inputs obtainable from an API or live feed.  Video
and tracking-derived features can train or evaluate a model, but cannot be
part of its shipped inference manifest.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable


RUNTIME = "RUNTIME"
TRAINING_ONLY = "TRAINING_ONLY"
UNKNOWN = "UNKNOWN"

# This is deliberately an explicit, small allowlist. Add a pattern only after
# documenting how the live service obtains that class of input.
RUNTIME_AVAILABLE = (
    r"(?:market|odds|price|line|book|implied|vig)_[a-z0-9_]+",
    r"(?:home|away)_(?:moneyline|spread|total|score|team_id)",
    r"(?:score|period|quarter|clock|time_remaining|possession|game_state|"
    r"fouls?|timeouts?|seconds_remaining)",
    r"(?:schedule|game_date|tipoff|rest|days_rest|back_to_back|travel)"
    r"(?:_[a-z0-9_]+)?",
    r"(?:player|team|roster|lineup|starter|active|inactive)_[a-z0-9_]*id",
    r"(?:roster|lineup|starter|active|inactive)_[a-z0-9_]*",
    r"(?:injury|news|status|scratch|questionable|available)_[a-z0-9_]+",
    r"prior_[a-z0-9_]+",
    r"[a-z0-9_]+_prior",
)

# These take precedence over the runtime allowlist to prevent an accidental
# overlap from admitting a tracking feature.
TRAINING_ONLY_PATTERNS = (
    r"per36_[a-z0-9_]+",
    r"screen_[a-z0-9_]+",
    r"hull_[a-z0-9_]+",
    r"pressing_[a-z0-9_]+",
    r"command_[a-z0-9_]+",
    r"presnap_[a-z0-9_]+",
    r"rally_[a-z0-9_]+",
    r"coverage_[a-z0-9_]+",
    r"(?:tracking|track|data)_[a-z0-9_]+",
    r"[a-z0-9_]+_(?:tracking|track|data)",
)


def _matches(name: str, patterns: tuple[str, ...]) -> bool:
    return any(re.fullmatch(pattern, name) is not None for pattern in patterns)


def classify_feature(name: str) -> str:
    """Classify a feature name under the live-inference availability contract."""
    normalized = name.strip().lower() if isinstance(name, str) else ""
    if _matches(normalized, TRAINING_ONLY_PATTERNS):
        return TRAINING_ONLY
    if _matches(normalized, RUNTIME_AVAILABLE):
        return RUNTIME
    return UNKNOWN


def validate_manifest(feature_names: Iterable[str]) -> dict[str, object]:
    """Validate a feature manifest, treating every unclassified name as unsafe."""
    violations: list[str] = []
    unknowns: list[str] = []
    for name in feature_names:
        classification = classify_feature(name)
        if classification == RUNTIME:
            continue
        display_name = name if isinstance(name, str) else repr(name)
        violations.append(display_name)
        if classification == UNKNOWN:
            unknowns.append(display_name)
    return {"ok": not violations, "violations": violations, "unknowns": unknowns}


def assert_runtime_safe(feature_names: Iterable[str]) -> None:
    """Raise ValueError if a manifest needs non-live or unclassified inputs."""
    result = validate_manifest(feature_names)
    if not result["ok"]:
        violations = ", ".join(result["violations"])
        unknowns = result["unknowns"]
        message = "Live runtime contract violation: " + violations
        if unknowns:
            message += ". Unclassified features fail closed: " + ", ".join(unknowns)
        raise ValueError(message)


def describe_contract() -> None:
    """Print the machine-checked live-model feature rule for documentation."""
    print(
        "Live models may use only allowlisted API/live-feed fields: market prices, "
        "score/state, schedule/rest, roster/lineup IDs, news flags, and offline "
        "static priors (prior_* or *_prior). Tracking-derived and unclassified "
        "features are rejected."
    )


def _read_manifest(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list) and all(isinstance(item, str) for item in payload):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("feature_names"), list):
        names = payload["feature_names"]
        if all(isinstance(item, str) for item in names):
            return names
    raise ValueError("manifest JSON must be a string list or contain feature_names")


def main(argv: list[str] | None = None) -> int:
    """Check a JSON feature manifest and print its contract result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", type=Path, metavar="MANIFEST")
    args = parser.parse_args(argv)
    if args.check is None:
        parser.error("--check MANIFEST is required")
    try:
        result = validate_manifest(_read_manifest(args.check))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Could not read manifest: {exc}")
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Sport -> concept-registry module dispatch for the answer engine.
Each domain's concept_registry.py is self-contained (same schema, own
concepts/floors/orientation rules) -- contracts.py calls get_registry(sport)
and never imports a domain registry directly."""
from __future__ import annotations

import importlib
from functools import lru_cache

CONCEPT_REGISTRY_MODULE = {
    "nba": "domains.basketball_nba.concepts.concept_registry",
    "mlb": "domains.mlb.concepts.concept_registry",
    "tennis": "domains.tennis.concepts.concept_registry",
    "soccer": "domains.soccer.concepts.concept_registry",
    "wnba": "domains.basketball_wnba.concepts.concept_registry",
}


@lru_cache(maxsize=None)
def get_registry(sport: str):
    path = CONCEPT_REGISTRY_MODULE.get(sport)
    if path is None:
        raise ValueError(f"no concept registry wired for sport '{sport}'. "
                          f"Available: {sorted(CONCEPT_REGISTRY_MODULE)}")
    return importlib.import_module(path)

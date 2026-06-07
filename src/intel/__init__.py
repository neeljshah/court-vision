"""Intel dossier assemblers.

Synthesize the already-shipped atlas_*.parquet sections (+ persistent profile
factory) into ONE coherent, human-readable intelligence dossier per entity.

Deterministic only — rule/threshold playstyle classification + percentile-ranked
strengths/weaknesses + key-stat extraction. No LLM-per-entity, no external feeds.
Scales to all 30 teams / ~1200 players at $0/entity.
"""

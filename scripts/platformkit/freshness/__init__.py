"""scripts.platformkit.freshness -- freshness measurement and sidecar writing.

Submodules:
  as_of_reader            -- vintage leak guard (as-of injury delta reader)
  schema                  -- InjuryDelta dataclass + validate_delta
  extract_stub            -- stub extraction helpers
  proxy_quarantine        -- fallback proxy labeling
  freshness_sidecar_runner -- per-sport _freshness.json measurement writer (W-FRESHNESS-SIDECAR)
"""

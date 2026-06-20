"""predict_service -- canonical snapshot contracts + atomic store.

Public surface:
  * contracts: MarketRow, EdgeRow, PredictionRecord, SnapshotEnvelope (+ SCHEMA_VERSION)
  * store: save/write, read_latest, append_history, read_history, path helpers
"""

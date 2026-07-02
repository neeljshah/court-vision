"""data_registry -- generated per-sport data census + drift / fail-closed health.

A leak-free, offline inventory of the per-sport corpora under data/domains/<sport>.
It exists to kill the silent 0-row landmine (a builder that "succeeds" on an empty
corpus) and to flag schema/row drift against a stored baseline.

NOTE: this package writes ONLY to data_registry/_INVENTORY.json. It NEVER writes
data/registry/ (a distinct, forbidden path). Metadata-only: it reads parquet
footers, not the row data, so it is cheap and side-effect free.
"""

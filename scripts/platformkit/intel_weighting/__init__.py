"""intel_weighting -- claim-relevance weighting engine.

For each verified claim family, measure whether conditioning a leak-free
baseline prediction on the claim improves out-of-sample calibration (Brier).
Produces a weight ledger of MATTERS / NULL / UNTESTABLE verdicts. Most families
are expected NULL -- the ledger of honest nulls IS the product. No dollar/edge
language anywhere; calibration deltas only.
"""

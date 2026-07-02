"""Milestone-8 self-improvement ratchet (sport-blind).

A recalibration candidate may SHIP only if it improves OUT-OF-SAMPLE on EVERY
proper score that applies -- a win on one and a loss on another is a REJECT.
This package holds the pure gates that enforce that honesty discipline. No
dollar edge is computed anywhere; the bar is proper-score calibration only.
"""

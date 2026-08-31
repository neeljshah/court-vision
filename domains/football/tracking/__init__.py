"""Pre-snap American-football broadcast tracking."""

# Harness usage (do not edit tracking_harness.py): add "football": ((0, 360), (0, 160)).
from .adapter import FootballAdapter, write_csv

__all__ = ["FootballAdapter", "write_csv"]

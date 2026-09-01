"""Pre-snap American-football broadcast tracking."""

# The shared harness carries the football adapter's offset-relative 360-by-160
# pre-snap contract; this adapter does not provide ball telemetry.
from .adapter import FootballAdapter, write_csv

__all__ = ["FootballAdapter", "write_csv"]

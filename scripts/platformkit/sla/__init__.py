"""scripts.platformkit.sla -- freshness-SLA scoreboard (IOX-1).

One file answers 'is anything stale': given a list of (artifact_path, sla_sec)
pairs and a clock epoch, produces a per-row SLA verdict table and atomically
writes it to data/frontend/ops/sla_scoreboard.json.

Public re-exports: sla_scoreboard.build, sla_scoreboard.write_scoreboard
"""
from scripts.platformkit.sla.sla_scoreboard import build, write_scoreboard  # noqa: F401

__all__ = ["build", "write_scoreboard"]

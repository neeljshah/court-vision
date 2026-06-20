# supervisor -- cross-platform process control for Milestone-9 always-on boot.
# Import from supervisor.proc (auto-selects backend by os.name).
#
# Inventory + readiness layer (sport-blind, no spawning):
#   manifest(profile)  -> ordered, DAG-validated ProcSpec list
#   load_profile(name) -> safe BootProfile from config/boot/*.json
#   probe(spec, ...)   -> resolve one readiness probe (injectable fetcher/clock)
#   probe(spec, ...)   -> resolve one readiness probe (injectable fetcher/clock)
#
# Orchestration layer (Milestone-9):
#   Supervisor / boot_stack -> dependency-ordered, readiness-gated, auto-restart
#   supervisor_status / write_status / status_path -> the one status JSON
from supervisor.config import BootProfile, load_profile
from supervisor.health import probe, real_fetcher
from supervisor.manifest import (
    CycleError,
    ProcSpec,
    ReadinessSpec,
    RestartPolicy,
    manifest,
    topo_order,
)
from supervisor.status import status_path, supervisor_status, write_status
from supervisor.supervisor import Supervisor
from supervisor.supervisor import boot as boot_stack

__all__ = [
    "ProcSpec",
    "ReadinessSpec",
    "RestartPolicy",
    "CycleError",
    "manifest",
    "topo_order",
    "probe",
    "real_fetcher",
    "BootProfile",
    "load_profile",
    "Supervisor",
    "boot_stack",
    "supervisor_status",
    "write_status",
    "status_path",
]

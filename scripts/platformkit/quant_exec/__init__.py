"""scripts.platformkit.quant_exec -- quant Execution API support (transparency only).

build_validation produces ONE auditable bet-validation verdict by reusing the
vetted exec_decision tiering/units + odds_shop devig/EV + clv_core yardstick. No
new math; no $ field; gate_proven defaults FALSE.
"""
from scripts.platformkit.quant_exec.validate import (  # noqa: F401
    BetValidation,
    build_validation,
    is_verified_gate_token,
)

__all__ = ["BetValidation", "build_validation", "is_verified_gate_token"]

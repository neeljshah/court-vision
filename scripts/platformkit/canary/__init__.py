"""scripts.platformkit.canary -- stack canary probe daemon (IOX-2).

Measurement-only synthetic end-to-end check: 'can the stack serve a calibrated
prediction right now?' -- no live game required.

Public surface:
    stack_canary.run_canary()  -> CanaryResult (READY / DEGRADED / DOWN)
    canary_runner.run()        -> loop; writes canary_status.json + heartbeat
"""

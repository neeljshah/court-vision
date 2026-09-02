"""scripts.platformkit.improve.fusion -- WAVE 2 model-level fusion lane.

A DIFFERENT mechanism than the feature-combination lane (scripts/platformkit/combo):
here we combine ALREADY-VALIDATED signals INSIDE the predictor via leak-free OOF
stacking (STACK_OOF), regime-switching mixtures-of-experts (REGIME_MOE), residual-
boosting of the proven base (RESID_BOOST), and isotonic/Platt re-fusion (REFUSE_CAL).

Every fusion is just another candidate that produces the gate's standard verdict and
clears the SAME L0..L6 stricter-at-scale ladder (scripts.platformkit.combo.combo_gate)
vs the PROVEN base -- NOT a strawman. Its meta-flexibility (regime splits x meta
families x base subsets x re-fusion maps) is COUNTED into K so the bar TIGHTENS as the
search widens. Most fusions WILL reject; an honest REJECT is a SUCCESS.

INVARIANTS (the whole lane): never pushes origin, never writes data/registry/ or
MEMORY.md, never flips a flag, never creates the PIPELINE_ENABLED sentinel, never
auto-serves. Builders' FIRST line is the MF1 kill-switch (inert when the sentinel is
absent). Calibration, NOT edge: vs_close = UNPROVEN; no $/ROI/edge field anywhere.
"""

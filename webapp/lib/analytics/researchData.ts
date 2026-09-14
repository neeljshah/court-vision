import { basketballResearch } from "./researchBasketball";
import { multisportResearch } from "./researchMultisport";
import { validationResearch } from "./researchValidation";
import { getBasketballDepthResearch } from "./researchBasketballDepth";
import { getMultisportDepthResearch } from "./researchMultisportDepth";
import type { ResearchAnalysis } from "./researchTypes";
export function getResearchAnalyses(): ResearchAnalysis[] {
  const preferred: Record<string, string> = { "mlb-shrinkage-displacement": "absolute_regression", "soccer-minute-calibration-support": "signed_gap", "tennis-surface-prior-brier-delta": "delta", "mlb-velocity-shape": "spread", "mlb-pitch-mix-concentration": "squared_share", "brier-relative-gap": "relative_gap", "observed-cohort-shift": "model_shift", "signed-calibration-direction": "signed_gap" };
  return [...getBasketballDepthResearch(), ...getMultisportDepthResearch(), ...basketballResearch(), ...multisportResearch(), ...validationResearch()].map(a => ({
    ...a, fields: [...a.fields].sort((left, right) => Number(right.key === preferred[a.id]) - Number(left.key === preferred[a.id])),
  }));
}

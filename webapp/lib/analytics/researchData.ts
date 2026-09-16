import { basketballResearch } from "./researchBasketball";
import { multisportResearch } from "./researchMultisport";
import { validationResearch } from "./researchValidation";
import { getBasketballDepthResearch } from "./researchBasketballDepth";
import { getMultisportDepthResearch } from "./researchMultisportDepth";
import { getTennisWindowResearch } from "./researchTennisWindows";
import { getBasketballMatchupRangeResearch } from "./researchBasketballMatchupRange";
import { getPaceVarianceResearch } from "./researchPaceVariance";
import { getStarRemovalResearch } from "./researchStarRemoval";
import { getLineupProxyResearch } from "./researchLineupProxy";
import { getComebackAtlasResearch } from "./researchComebackAtlas";
import { getMlbBatterContactResearch } from "./researchMlbBatterContact";
import { getMarketDisagreementResearch } from "./researchMarketDisagreement";
import { getInformationArrivalResearch } from "./researchInformationArrival";
import { getMarketConvergenceResearch } from "./researchMarketConvergence";
import { getBrierSkillScoresResearch } from "./researchBrierSkillScores";
import { getOnOffResearch } from "./researchOnOff";
import { getMechanismSurvivalResearch } from "./researchMechanismSurvival";
import { getMicroAbsorptionResearch } from "./researchMicroAbsorption";
import { getMlbCatcherOozResearch } from "./researchMlbCatcherOoz";
import { getSoccerFormGapResearch } from "./researchSoccerFormGap";
import { getNbaTeamProfileResearch } from "./researchNbaTeamProfile";
import { getNbaPlayerContextResearch } from "./researchNbaPlayerContext";
import { getAtlasPackResearch } from "./researchAtlasPacks";
import { getCalibrationCheckpointResearch } from "./researchCalibrationCheckpoints";
import type { ResearchAnalysis } from "./researchTypes";
export function getResearchAnalyses(): ResearchAnalysis[] {
  const preferred: Record<string, string> = { "mlb-shrinkage-displacement": "absolute_regression", "soccer-minute-calibration-support": "signed_gap", "tennis-surface-prior-brier-delta": "delta", "mlb-velocity-shape": "spread", "mlb-pitch-mix-concentration": "squared_share", "brier-relative-gap": "relative_gap", "observed-cohort-shift": "model_shift", "signed-calibration-direction": "signed_gap" };
  return [...getAtlasPackResearch(), ...getCalibrationCheckpointResearch(), ...getSoccerFormGapResearch(), ...getMlbBatterContactResearch(), ...getBasketballMatchupRangeResearch(), ...getTennisWindowResearch(), ...getPaceVarianceResearch(), ...getStarRemovalResearch(), ...getLineupProxyResearch(), ...getComebackAtlasResearch(), ...getMarketDisagreementResearch(), ...getInformationArrivalResearch(), ...getMarketConvergenceResearch(), ...getBrierSkillScoresResearch(), ...getBasketballDepthResearch(), ...getMultisportDepthResearch(), ...getOnOffResearch(), ...getMechanismSurvivalResearch(), ...getMicroAbsorptionResearch(), ...getMlbCatcherOozResearch(), ...getNbaTeamProfileResearch(), ...getNbaPlayerContextResearch(), ...basketballResearch(), ...multisportResearch(), ...validationResearch()].map(a => ({
    ...a, fields: [...a.fields].sort((left, right) => Number(right.key === preferred[a.id]) - Number(left.key === preferred[a.id])),
  }));
}

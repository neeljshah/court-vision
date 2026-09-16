import { snapshot } from "./labHelpers";
import { buildResidualAnatomy, type ResidualAnatomyData } from "./residualAnatomy";

/** Reads the build-time residual anatomy snapshot; this module is server-only. */
export function loadResidualAnatomy(): ResidualAnatomyData {
  return buildResidualAnatomy(snapshot<unknown>("residual_anatomy"));
}

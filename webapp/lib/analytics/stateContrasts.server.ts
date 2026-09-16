import { snapshot } from "./labHelpers";
import { buildStateContrasts, type StateContrastSport } from "./stateContrasts";

/** Reads the committed build-time state contrast snapshot; the browser never fetches it. */
export function loadStateContrasts(): StateContrastSport[] {
  return buildStateContrasts(snapshot<unknown>("why_attribution"));
}

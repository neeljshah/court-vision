import { snapshot } from "./labHelpers";
import { buildBlowoutTiming, type BlowoutTimingSport } from "./blowoutTiming";

/** Reads the committed build-time snapshot; the browser never fetches this artifact. */
export function loadBlowoutTiming(): BlowoutTimingSport[] {
  return buildBlowoutTiming(snapshot<unknown>("blowout_dynamics"));
}

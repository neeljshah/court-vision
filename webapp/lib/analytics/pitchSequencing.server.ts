import { snapshot } from "./labHelpers";
import { buildPitchSequencing, type PitchSequencingData } from "./pitchSequencing";

/** Reads the build-time JSON snapshot on the server; no browser fetch is used. */
export function loadPitchSequencing(): PitchSequencingData {
  return buildPitchSequencing(snapshot<unknown>("pitch_sequencing"));
}

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { buildStateReliability, type StateReliabilitySport } from "./stateReliability";

/** Reads the committed build-time state calibration snapshot; the client receives parsed data only. */
export function loadStateReliability(): StateReliabilitySport[] {
  const path = join(process.cwd(), "public", "data", "showcase", "state_conditioned_calibration.json");
  return buildStateReliability(JSON.parse(readFileSync(path, "utf-8")) as unknown);
}

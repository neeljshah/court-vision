import { readFileSync } from "node:fs";
import { join } from "node:path";
import { buildHomeCalibrationExample, type HomeCalibrationExample } from "./homeCalibrationExample";

/** Loads the committed calibration artifact at build time for the static home page. */
export function loadHomeCalibrationExample(): HomeCalibrationExample | null {
  try {
    const path = join(process.cwd(), "public", "data", "showcase", "calibration_stability.json");
    return buildHomeCalibrationExample(JSON.parse(readFileSync(path, "utf8")) as unknown);
  } catch {
    return null;
  }
}

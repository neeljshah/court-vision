import { readFileSync } from "node:fs";
import { join } from "node:path";

export type ForecasterArm = {
  sport: string;
  n: number | null;
  observed_on: string | null;
  static_brier: number | null;
  score_only_brier: number | null;
  combined_brier: number | null;
  mechanical_share: string | null;
  model_prior_share: string | null;
};

export type ForecasterArms = {
  as_of: string | null;
  measurement: { identity: string } | null;
  arms: ForecasterArm[];
  sources: Array<{ path: string; role: string }>;
};

const EMPTY: ForecasterArms = {
  as_of: null,
  measurement: null,
  arms: [],
  sources: [],
};

/** Reads the public artifact used by the static Forecaster export. */
export function loadForecasterArms(): ForecasterArms {
  try {
    const artifact = join(process.cwd(), "public", "data", "forecaster", "forecaster-arms.json");
    return JSON.parse(readFileSync(artifact, "utf8")) as ForecasterArms;
  } catch {
    return EMPTY;
  }
}

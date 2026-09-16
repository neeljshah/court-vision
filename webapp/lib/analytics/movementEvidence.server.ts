import { readFileSync } from "node:fs";
import { join } from "node:path";
import { buildMovementEvidence, type MovementEvidence } from "./movementEvidence";

/** Reads movement artifacts at build time; client components receive values only. */
export function loadMovementEvidence(): MovementEvidence {
  const root = join(process.cwd(), "public", "data", "showcase");
  const overreaction = JSON.parse(readFileSync(join(root, "market_overreaction.json"), "utf8")) as unknown;
  const absorption = JSON.parse(readFileSync(join(root, "micro_absorption.json"), "utf8")) as unknown;
  return buildMovementEvidence(overreaction, absorption);
}

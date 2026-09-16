import { readFileSync } from "node:fs";
import { join } from "node:path";
import { buildReliabilityFinding, type ReliabilityFindingSport } from "./reliabilityFinding";

/** Reads the committed build-time Murphy decomposition snapshot. */
export function loadReliabilityFinding(): ReliabilityFindingSport[] {
  const path = join(process.cwd(), "public", "data", "showcase", "murphy_decomposition.json");
  return buildReliabilityFinding(JSON.parse(readFileSync(path, "utf-8")) as unknown);
}

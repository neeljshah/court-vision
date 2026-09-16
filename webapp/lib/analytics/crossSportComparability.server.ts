import { readFileSync } from "node:fs";
import { join } from "node:path";
import { destinationForSourceModule } from "./analysisDestinations";
import {
  buildCrossSportComparability,
  type CrossSportComparability,
  type CrossSportEvidence,
  type CrossSportSourceRow,
  type CrossSportSnapshot,
} from "./crossSportComparability";
import { resolveResearchSourceDestination } from "./researchSourceDestinations";

function sourceId(path: string): string {
  return path.split("/").at(-1)?.replace(/\.json$/, "") || "kernel_transfer";
}

function evidenceFor(row: CrossSportSourceRow): CrossSportEvidence {
  const destination = destinationForSourceModule(sourceId(row.sources[0] || ""));
  if (destination) return { href: destination.route, title: destination.title };
  const fallback = resolveResearchSourceDestination("kernel_transfer");
  return { href: fallback.href, title: "Kernel Transfer evidence" };
}

export function loadCrossSportComparability(): CrossSportComparability {
  const raw = readFileSync(join(process.cwd(), "public", "data", "showcase", "kernel_transfer.json"), "utf8");
  return buildCrossSportComparability(JSON.parse(raw) as CrossSportSnapshot, evidenceFor);
}

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { buildReliabilityFinding } from "./reliabilityFinding";
import { loadReliabilityFinding } from "./reliabilityFinding.server";

describe("reliability finding data", () => {
  it("keeps published denominators and rounds the derived direct-minus-reconstruction remainder", () => {
    const soccer = loadReliabilityFinding().find(item => item.sport === "soccer_intl")!;
    const model = soccer.measurements.find(item => item.source === "model")!;
    expect(soccer.nRows).toBe(9003);
    expect(model.n).toBe(9003);
    expect(model.remainder).toBe(-0.065642);
    expect(model.reliabilityComparison).toBe("larger");
  });

  it("rejects an incomplete published source population", () => {
    const path = join(process.cwd(), "public", "data", "showcase", "murphy_decomposition.json");
    const artifact = JSON.parse(readFileSync(path, "utf-8")) as { sports: Record<string, { model_prob: Record<string, unknown> }> };
    delete artifact.sports.soccer_intl.model_prob.reconstructed_brier;
    expect(buildReliabilityFinding(artifact).map(item => item.sport)).toEqual(["mlb"]);
  });
});

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import siteManifest from "@/public/data/showcase/site_manifest.json";
import { PACKET_VERDICTS, isPacketVerdict } from "@/components/evidence/VerdictLabel";
import { isRepoPath, normalizeRepoPath } from "@/components/evidence/kit";
import { generateFromFile } from "../scripts/gen-figures.mjs";
import { COMPARISON_FIGURES, COUNT_FIGURES, FIGURES, FIGURES_AS_OF, FIGURES_SOURCE, FIGURE_KEYS, RETRACTED_TOKENS } from "./figures";

// The committed lib/figures.ts is a build artifact of docs/evidence/CANONICAL_FIGURES.json.
// These tests are the drift guard: the module must match a fresh generation, and the
// figures the site derives for itself must agree with the canonical set.
const REPO = resolve(__dirname, "../..");
const canonical = JSON.parse(readFileSync(join(REPO, FIGURES_SOURCE), "utf8"));

describe("lib/figures.ts (generated)", () => {
  it("matches a fresh generation from the canonical JSON", () => {
    expect(readFileSync(join(__dirname, "figures.ts"), "utf8")).toBe(generateFromFile());
  });

  it("carries every canonical figure, once, with the JSON's as-of and retractions", () => {
    const keys = [...canonical.canonical_counts.figures, ...canonical.figures].map((f: { key: string }) => f.key);
    expect(FIGURE_KEYS).toEqual(keys);
    expect(FIGURES_AS_OF).toBe(canonical.as_of);
    expect(RETRACTED_TOKENS).toEqual(canonical.retracted_tokens);
    expect(Object.keys(COUNT_FIGURES)).toHaveLength(canonical.canonical_counts.figures.length);
    expect(Object.keys(COMPARISON_FIGURES)).toHaveLength(canonical.figures.length);
  });

  it("agrees with the figures the site derives for itself (module count, findings count)", () => {
    expect(siteManifest.module_count).toBe(COUNT_FIGURES.published_module_count.value);
    const findingsDir = join(__dirname, "../app/(analytics)/analytics/findings");
    const findingPages = readdirSync(findingsDir, { withFileTypes: true }).filter((entry) => entry.isDirectory()).length;
    expect(findingPages).toBe(COUNT_FIGURES.titled_findings_count.value);
  });

  it("agrees with the packet's forward window and G6 wording", () => {
    const packet = readFileSync(join(REPO, "docs/JOB_EVIDENCE_PACKET.md"), "utf8");
    expect(packet).toMatch(new RegExp(`^## 5\\. Forward paper record 2026-10-06 \\.\\. ${COUNT_FIGURES.forward_window_end.value}`, "m"));
    expect(COUNT_FIGURES.g6_status.value).not.toMatch(/zero qualifying weeks/i);
    expect(COUNT_FIGURES.g6_status.value).toContain("has not started as of");
  });

  it("uses only the packet's verdict labels", () => {
    for (const fig of Object.values(COMPARISON_FIGURES)) {
      expect(isPacketVerdict(fig.verdict), `${fig.key} verdict ${fig.verdict} not in ${PACKET_VERDICTS.join(", ")}`).toBe(true);
    }
  });

  it("names source artifacts that exist in the public repository (no dead receipt links)", () => {
    for (const fig of Object.values(FIGURES)) {
      if (!isRepoPath(fig.source)) continue;
      expect(existsSync(join(REPO, normalizeRepoPath(fig.source))), `${fig.key}: ${fig.source}`).toBe(true);
    }
  });

  it("never carries a retracted token as a current value", () => {
    const text = JSON.stringify(FIGURES);
    for (const token of RETRACTED_TOKENS) expect(text).not.toContain(`"${token}"`);
  });
});

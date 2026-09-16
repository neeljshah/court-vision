// Guards the claim-ledger paper against fwd_claim_scoreboard.json and verdict_flip_anatomy.json:
// the 134 nulls-or-worse and the 138 not-verified families are different counts, the combined
// reliever family never recorded a confirmed step, and the paper claims a dated snapshot rather
// than completeness.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
// @ts-expect-error -- the executable scanner is deliberately dependency-free ESM.
import { scanRenderedText } from "../../scripts/check-analytics-copy.mjs";
import { publishedArtifacts } from "./papers.server";
import { paperStrings, validatePaper, type Paper } from "./papers";

/* eslint-disable @typescript-eslint/no-explicit-any */
function readJson(folder: string, name: string): any {
  const raw = readFileSync(join(process.cwd(), "public", "data", folder, `${name}.json`), "utf8");
  // Python exports carry bare NaN; the site's own loaders null it out the same way.
  return JSON.parse(raw.replace(/"(?:\\.|[^"\\])*"|\bNaN\b/g, token => (token === "NaN" ? "null" : token)));
}

const LEDGER_PAPER = readJson("papers", "how-proposed-signals-survive-testing") as Paper;
const text = paperStrings(LEDGER_PAPER).join(" ");
const scoreboard = readJson("showcase", "fwd_claim_scoreboard");
const flips = readJson("showcase", "verdict_flip_anatomy");

describe("how-proposed-signals-survive-testing", () => {
  it("separates the 134 nulls-or-worse from the 138 families that are not verified", () => {
    const byStatus = scoreboard.summary.by_status;
    const nullsOrWorse = byStatus.null + byStatus.not_testable + byStatus.retracted;
    expect(nullsOrWorse).toBe(134);
    expect(scoreboard.summary.nulls_or_worse).toBe(nullsOrWorse);
    expect(byStatus.provisional).toBe(4);
    expect(scoreboard.summary.n_families - byStatus.verified).toBe(138);
    expect(nullsOrWorse + byStatus.provisional).toBe(138);

    expect(text).toContain("134 families are null, not testable or retracted");
    expect(text).toContain("four more are provisional");
    expect(text).toContain("138 of the 259");
    expect(text).not.toMatch(/134 families whose current status is anything other than verified/i);
  });

  it("scopes itself to the dated snapshot instead of claiming completeness", () => {
    expect(scoreboard.as_of).toBe("2026-07-11T16:48:14Z");
    expect(scoreboard.n_ledger_rows).toBe(287);
    expect(scoreboard.summary.n_families).toBe(259);

    expect(text).toContain("fwd_claim_scoreboard.json as of 2026-07-11");
    expect(text).toContain("287 recorded test-run rows grouped into 259 claim families");
    expect(text).not.toMatch(/every candidate/i);
    expect(text).not.toMatch(/whether the record of testing is complete/i);
  });

  it("records the combined reliever family as never confirmed", () => {
    const combined = flips.flips.find((entry: any) => entry.hypothesis === "reliever_3in3d_fatigue__combined");
    expect(combined.steps.map((step: any) => step.verdict)).toEqual(["PROVISIONAL", "NULL_LOCAL"]);
    expect(combined.steps.some((step: any) => step.status === "verified")).toBe(false);
    expect(combined.current_status).toBe("null");

    expect(text).toContain("reliever_3in3d_fatigue__combined never recorded a confirmed step at all");
    expect(text).not.toMatch(/reliever_3in3d_fatigue__combined and staff_dayafter_fatigue_chain\) ended on null despite an intermediate confirmed step/);
  });

  it("keeps the 129-versus-130 taxonomy reconciliation", () => {
    const survival = readJson("showcase", "mechanism_survival");
    const exported = readJson("showcase", "mechanism_ledger_export");
    expect(survival.overall.n_confirmed).toBe(129);
    expect(exported.overall_counts.confirmed).toBe(130);
    expect(exported.overall_counts.confirmed - survival.overall.n_confirmed).toBe(1);

    expect(text).toContain("129");
    expect(text).toContain("130");
    expect(text).toContain("ARTIFACT_CONFIRMED");
  });

  it("stays valid, ASCII and free of prohibited vocabulary", () => {
    expect(validatePaper(LEDGER_PAPER, publishedArtifacts())).toBeNull();
    expect(scanRenderedText(text)).toEqual([]);
  });
});

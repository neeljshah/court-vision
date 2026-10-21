// verifyPublicRules.test.ts -- the build validator's constants stay equal to the readers'.
import { describe, expect, it } from "vitest";
import { HEADLINE_KEYS } from "../canonicalFigures.server";
import { UPTIME_RE as DESK_UPTIME_RE } from "@/components/desk/deskExtras.server";
import { ARTIFACT_RULES, CANONICAL_HEADLINE_KEYS, CHECK_STATUSES, UPTIME_RE } from "../../scripts/verify-public-rules.mjs";

describe("verify-public-rules", () => {
  it("checks the same headline keys the home page renders", () => {
    expect([...CANONICAL_HEADLINE_KEYS]).toEqual([...HEADLINE_KEYS]);
  });

  it("accepts exactly the check statuses the desk loader counts, and the same uptime file name", () => {
    expect(CHECK_STATUSES).toEqual(["PASS", "NO_CHECK", "FAIL"]);
    expect(UPTIME_RE.source).toBe(DESK_UPTIME_RE.source);
  });

  it("covers every baked artifact the pages read at build time", () => {
    const files = ARTIFACT_RULES.map((r) => (typeof r.file === "string" ? r.file : r.label));
    for (const f of ["public/demo-data/manifest.json", "public/demo-data/api_paper_trail_limit_400.json", "public/receipts.json",
      "public/data/explainers/explainers.json", "scripts/platformkit/analytics_showcase/out/check_all_report.json",
      "docs/evidence/CANONICAL_FIGURES.json", "docs/evidence/DESK_UPTIME_<date>.json"]) {
      expect(files).toContain(f);
    }
  });
});

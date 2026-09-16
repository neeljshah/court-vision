import { expect, it } from "vitest";
// @ts-expect-error -- the executable scanner is deliberately dependency-free ESM.
import { scanAnalyticsCopy, scanAnalyticsData } from "../../scripts/check-analytics-copy.mjs";

const TEMPORARY_OWNED_PATHS = new Set([
  // TODO: remove after the lanes owning these two detail pages land their copy sweep.
  "app/(analytics)/analytics/m/[id]/page.tsx",
  "app/(analytics)/analytics/players/[pack]/[slug]/page.tsx",
]);

it("finds no prohibited calibration-product language in public copy", () => {
  const findings = scanAnalyticsCopy().filter((finding: { file: string }) => !TEMPORARY_OWNED_PATHS.has(finding.file));
  expect(findings).toEqual([]);
});

it("finds no prohibited calibration-product language in published data prose", () => {
  expect(scanAnalyticsData()).toEqual([]);
});

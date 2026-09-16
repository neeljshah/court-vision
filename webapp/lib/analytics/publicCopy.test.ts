import { expect, it } from "vitest";
// @ts-expect-error -- the executable scanner is deliberately dependency-free ESM.
import { scanAnalyticsCopy, scanAnalyticsData, scanSourceText } from "../../scripts/check-analytics-copy.mjs";

it("finds no prohibited calibration-product language in public copy", () => {
  expect(scanAnalyticsCopy()).toEqual([]);
});

it("finds no prohibited calibration-product language in published data prose", () => {
  expect(scanAnalyticsData()).toEqual([]);
});

it("flags inflections in JSX, literals, template literals, and metadata", () => {
  const findings = scanSourceText("app/(analytics)/fixture/page.tsx", `
    export const metadata = { description: "A profitable process." };
    const summary = \`A bookmaker published this.\`;
    export default function Fixture() { return <p>Bettors recorded payouts.</p>; }
  `);
  expect(findings).toHaveLength(3);
});

it("flags prohibited language even when it appears in a retraction record", () => {
  const path = "app/(analytics)/analytics/findings/retraction/page.tsx";
  expect(scanSourceText(path, `const figures = [{ retracted: "ROI result" }];`)).toHaveLength(1);
  expect(scanSourceText(path, `const explanation = "The betting method was invalid.";`)).toHaveLength(1);
});

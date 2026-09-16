import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, it } from "vitest";
// @ts-expect-error -- the executable scanner is deliberately dependency-free ESM.
import { DATA_TARGETS, PROHIBITED_TOKEN_RE, scanAnalyticsCopy, scanAnalyticsData, scanSourceText } from "../../scripts/check-analytics-copy.mjs";

it("finds no prohibited calibration-product language in public copy", () => {
  expect(scanAnalyticsCopy()).toEqual([]);
});

it("finds no prohibited calibration-product language in published data prose", () => {
  expect(scanAnalyticsData()).toEqual([]);
});

it("scans published showcase artifacts", () => {
  expect(DATA_TARGETS).toContain("public/data/showcase");
});

it("flags inflections in JSX, literals, template literals, and metadata", () => {
  const findings = scanSourceText("app/(analytics)/fixture/page.tsx", `
    export const metadata = { description: "A profitable process." };
    const summary = \`A wagering guide published this.\`;
    export default function Fixture() { return <p>Bettors recorded payouts.</p>; }
  `);
  expect(findings).toHaveLength(3);
});

it("flags prohibited language even when it appears in a retraction record", () => {
  const path = "app/(analytics)/analytics/findings/retraction/page.tsx";
  expect(scanSourceText(path, `const figures = [{ retracted: "ROI result" }];`)).toHaveLength(1);
  expect(scanSourceText(path, `const explanation = "The betting method was invalid.";`)).toHaveLength(1);
});

it("scans every string in a fixture JSON, including questions", () => {
  expect(PROHIBITED_TOKEN_RE.test("betting")).toBe(true);
  const root = mkdtempSync(join(tmpdir(), "analytics-copy-"));
  mkdirSync(join(root, "public", "data", "ask"), { recursive: true });
  writeFileSync(join(root, "public", "data", "ask", "fixture.json"), JSON.stringify({ question: "Does this describe betting?" }));
  try {
    expect(scanAnalyticsData(root)).toMatchObject([{ jsonPath: "$.question" }]);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

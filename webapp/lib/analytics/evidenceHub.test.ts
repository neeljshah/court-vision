import { expect, it } from "vitest";
import manifest from "../../public/data/showcase/site_manifest.json";
import { getEvidenceCharts } from "./evidenceHub";

it("preserves the published fatigue artifact's explicit review status and provenance", () => {
  const entry = manifest.modules.find((item) => item.id === "novel_schedule_fatigue_tax")!;
  const chart = getEvidenceCharts().find((item) => item.id === entry.id);
  expect(entry.status).toBe("under-review");
  expect(chart).toMatchObject({
    status: "under-review", title: entry.title, description: entry.one_line,
    asOf: entry.as_of || null,
  });
  expect(chart?.sourceUrl).toBe(`https://github.com/neeljshah/court-vision/blob/master/${entry.out_path}`);
  expect(chart?.imageSrc).toMatch(/\/img\/showcase\/novel_schedule_fatigue_tax\.png$/);
});

it("keeps every staged gallery record aligned with a supported declared manifest status", () => {
  const expected = { ok: "published", partial: "partial", "under-review": "under-review" } as const;
  const charts = getEvidenceCharts();
  expect(charts.length).toBeGreaterThan(0);
  for (const chart of charts) {
    const entry = manifest.modules.find((item) => item.id === chart.id)!;
    // A new source status must receive an explicit mapping before publication.
    expect(Object.keys(expected), chart.id).toContain(entry.status);
    expect(chart.status, chart.id).toBe(expected[entry.status as keyof typeof expected]);
  }
  expect(charts.some((chart) => chart.status === "published")).toBe(true);
  expect(charts.some((chart) => chart.status === "partial")).toBe(true);
});

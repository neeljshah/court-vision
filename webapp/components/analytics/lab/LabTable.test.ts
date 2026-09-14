import { expect, it } from "vitest";
import { buildLabCSV } from "./LabTable";
import type { LabDataset } from "@/lib/analytics/labTypes";
it("exports source context, censoring notes, missing values, and unscaled numeric data safely", () => {
  const dataset: LabDataset = { id: "example", title: "Example", sport: "all", category: "Example", source: "snapshot", description: "", scope: "Historical cohort", caveat: "Subset only", status: "Descriptive", fields: [{ key: "half", label: "Half life", unit: "hours" }, { key: "rate", label: "Rate", unit: "percent" }], rows: [] };
  const csv = buildLabCSV(dataset, [{ id: "t", label: '=HYPERLINK("bad")', group: "Tennis", values: { half: null, rate: 0.107 }, note: "Censored: >6 hours" }, { id: "zero", label: "True zero", group: "Other", values: { half: 0, rate: -0.02 } }]);
  expect(csv).toContain('"Rate (percent; raw value)"');
  expect(csv).toContain('"\'=HYPERLINK(""bad"")","Tennis",,0.107,"Censored: >6 hours"');
  expect(csv).toContain('"True zero","Other",0,-0.02,');
  expect(csv).toContain('"snapshot","Historical cohort","Subset only"');
  expect(csv).not.toContain("undefined");
});

import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { buildLabCSV, LabTable } from "./LabTable";
import { createElement } from "react";
import type { LabDataset } from "@/lib/analytics/labTypes";
it("exports source context, censoring notes, missing values, and unscaled numeric data safely", () => {
  const dataset: LabDataset = { id: "example", title: "Example", sport: "all", category: "Example", source: "snapshot", description: "", scope: "Historical cohort", caveat: "Subset only", status: "Descriptive", fields: [{ key: "half", label: "Half life", unit: "hours" }, { key: "rate", label: "Rate", unit: "percent" }], rows: [] };
  const csv = buildLabCSV(dataset, [{ id: "t", label: '=HYPERLINK("bad")', group: "Tennis", values: { half: null, rate: 0.107 }, note: "Censored: >6 hours" }, { id: "zero", label: "True zero", group: "Other", values: { half: 0, rate: -0.02 } }]);
  expect(csv).toContain('"Rate (percent; raw value)"');
  expect(csv).toContain('"\'=HYPERLINK(""bad"")","Tennis",,0.107,"Censored: >6 hours"');
  expect(csv).toContain('"True zero","Other",0,-0.02,');
  expect(csv).toContain('"snapshot","Historical cohort","Subset only"');
  expect(csv).not.toContain("undefined");
  const derived = buildLabCSV({ ...dataset, ...{ formula: "rate = numerator / denominator" } }, [{ id: "x", label: "Sample", group: "Test", values: { half: null, rate: .25 } }]);
  expect(derived).toContain('"Formula"');
  expect(derived).toContain('"rate = numerator / denominator"');
});

it("links entity labels when a published entity route is available and retains inspection", () => {
  const dataset: LabDataset = { id: "example", title: "Example", sport: "all", category: "Example", source: "snapshot", description: "", scope: "Historical cohort", caveat: "Subset only", status: "Descriptive", fields: [{ key: "half", label: "Half life", unit: "hours" }], rows: [] };
  const onSelect = vi.fn();
  render(createElement(LabTable, { dataset, rows: [{ id: "entity", label: "Entity One", group: "Test", values: { half: 1 }, href: "/analytics/players/nba_players/entity_one" }], onSelect }));
  expect(screen.getByRole("link", { name: "Entity One" })).toHaveAttribute("href", "/analytics/players/nba_players/entity_one");
  screen.getByRole("button", { name: "Inspect Entity One" }).click();
  expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: "entity" }));
});

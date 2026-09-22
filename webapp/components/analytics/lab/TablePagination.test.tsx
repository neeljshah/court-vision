import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import MeasurementLab from "./MeasurementLab";
import ResearchDetail from "../library/ResearchDetail";
import type { LabData, LabDataset } from "@/lib/analytics/labTypes";
import type { ResearchAnalysis } from "@/lib/analytics/researchTypes";

const dataset: LabDataset = {
  id: "first", title: "First dataset", sport: "all", category: "Fixture", source: "fixture",
  description: "Published fixture", scope: "Fixture rows", caveat: "Descriptive", status: "Published",
  fields: [{ key: "value", label: "Value", unit: "number" }, { key: "alternate", label: "Alternate", unit: "number" }],
  rows: Array.from({ length: 32 }, (_, index) => ({
    id: String(index), label: `Team ${String(index).padStart(2, "0")}`,
    group: index < 16 ? "NBA" : "MLB", definition: { population: "Fixture rows" },
    values: { value: 32 - index, alternate: index },
  })),
};
const data: LabData = { datasets: [dataset, { ...dataset, id: "second", title: "Second dataset" }], novel: [] };
const analysis: ResearchAnalysis = {
  ...dataset, sport: "nba", formula: "Published fixture value", interpretation: "Fixture",
  references: [], novelty: "Derived analysis",
};
beforeEach(() => window.history.replaceState(null, "", "/analytics/lab/"));

function nextPage() {
  fireEvent.click(screen.getByRole("button", { name: "Next", exact: true }));
  expect(screen.getByText("Page 2 / 3")).toBeInTheDocument();
}
function expectFirstPage() {
  expect(screen.getByRole("button", { name: "Previous", exact: true })).toBeDisabled();
  expect(screen.getByText(/^Page 1 \/ /)).toBeInTheDocument();
}

describe("measurement lab pagination context", () => {
  it.each([
    ["Choose dataset", "second"], ["Filter lab by sport", "nba"],
    ["Published group", "NBA"], ["Primary measurement", "alternate"], ["Rank order", "asc"],
  ])("returns to the beginning when %s changes", (control, value) => {
    render(<MeasurementLab data={data} />);
    fireEvent.click(screen.getByRole("button", { name: "Data table", exact: true }));
    nextPage();
    fireEvent.change(screen.getByRole("combobox", { name: control, exact: true }), { target: { value } });
    expectFirstPage();
    const firstRow = within(screen.getByRole("table")).getAllByRole("row")[1];
    expect(firstRow).toHaveTextContent(control === "Rank order" || control === "Primary measurement" ? "Team 31" : "Team 00");
  });

  it("starts filtered and cleared searches on the first page", () => {
    render(<MeasurementLab data={data} />);
    fireEvent.click(screen.getByRole("button", { name: "Data table", exact: true }));
    nextPage();
    fireEvent.change(screen.getByRole("textbox", { name: "Search measurement rows" }), { target: { value: "NBA" } });
    expectFirstPage();
    expect(screen.getByText("Page 1 / 2")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next", exact: true }));
    fireEvent.change(screen.getByRole("textbox", { name: "Search measurement rows" }), { target: { value: "" } });
    expectFirstPage();
    expect(screen.getByText("Page 1 / 3")).toBeInTheDocument();
  });
});

describe("research ranking pagination context", () => {
  it.each([["Measurement", "alternate"], ["Order", "asc"]])(
    "shows the start of the new ranking when %s changes", (control, value) => {
      render(<ResearchDetail analysis={analysis} related={[]} />);
      fireEvent.click(screen.getByRole("button", { name: "Data table", exact: true }));
      nextPage();
      fireEvent.change(screen.getByRole("combobox", { name: control, exact: true }), { target: { value } });
      expectFirstPage();
      expect(within(screen.getByRole("table")).getAllByRole("row")[1]).toHaveTextContent("Team 31");
    },
  );
});

it.each(["lab", "research"])("preserves the current page while inspecting a %s row", (surface) => {
  render(surface === "lab" ? <MeasurementLab data={data} /> : <ResearchDetail analysis={analysis} related={[]} />);
  fireEvent.click(screen.getByRole("button", { name: "Data table", exact: true }));
  nextPage();
  screen.getByRole("button", { name: "Inspect Team 12", exact: true }).focus();
  fireEvent.click(screen.getByRole("button", { name: "Inspect Team 12", exact: true }));
  expect(screen.getByRole("region", { name: "Selected measurement", exact: true })).toHaveTextContent("Team 12");
  fireEvent.click(screen.getByRole("button", { name: surface === "lab" ? "Close measurement details" : "Close measurement", exact: true }));
  expect(screen.getByText("Page 2 / 3")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Inspect Team 12", exact: true })).toHaveFocus();
});

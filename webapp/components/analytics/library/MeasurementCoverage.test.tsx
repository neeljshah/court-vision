import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { MeasurementCoverage } from "./MeasurementCoverage";
import type { LabField, LabRow } from "@/lib/analytics/labTypes";

const fields: LabField[] = [
  { key: "shooting", label: "Shooting rate", unit: "percent" },
  { key: "defense", label: "Defense rate", unit: "percent" },
];
const rows: LabRow[] = [
  { id: "one", label: "One", group: "Fixture", values: { shooting: 0, defense: null } },
  { id: "two", label: "Two", group: "Fixture", values: { shooting: .2, defense: null } },
  { id: "three", label: "Three", group: "Fixture", values: { shooting: null, defense: null } },
];

function openCoverage() {
  fireEvent.click(screen.getByText("Measurement availability"));
  return screen.getByRole("region", { name: "Measurement availability" });
}

it("reports measured and missing coverage in field order, preserving numeric zero", () => {
  render(<MeasurementCoverage rows={rows} fields={fields} selectedKey="shooting" populationLabel="All published fixtures" onSelect={() => undefined} />);
  expect(screen.getByText("1 / 2 fields have values")).toBeInTheDocument();
  const coverage = openCoverage();
  expect(coverage).toHaveTextContent("All published fixtures");
  expect(coverage).toHaveTextContent("3 rows published");
  const buttons = within(coverage).getAllByRole("button");
  expect(buttons.map(button => button.getAttribute("aria-label"))).toEqual(["Use Shooting rate", "Use Defense rate"]);
  expect(buttons[0]).toHaveTextContent("2 / 3 measured");
  expect(buttons[0]).toHaveTextContent("1 missing");
  const description = buttons[0].getAttribute("aria-describedby");
  expect(description).not.toBeNull();
  expect(document.getElementById(description!)).toHaveTextContent("2 / 3 measured; 1 missing");
  expect(buttons[1]).toHaveTextContent("0 / 3 measured");
  expect(buttons[1]).toHaveTextContent("3 missing");
  expect(within(coverage).getByText("Text search does not change this reference population.")).toBeInTheDocument();
});

it("marks the selected field and sends a selected field change", () => {
  const onSelect = vi.fn();
  render(<MeasurementCoverage rows={rows} fields={fields} selectedKey="defense" populationLabel="All published fixtures" onSelect={onSelect} />);
  const coverage = openCoverage();
  const shooting = within(coverage).getByRole("button", { name: "Use Shooting rate" });
  expect(shooting).toHaveAttribute("aria-pressed", "false");
  expect(within(coverage).getByRole("button", { name: "Use Defense rate" })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(shooting);
  expect(onSelect).toHaveBeenCalledWith("shooting");
});

it("describes an empty population without inventing a percentage and retains field controls", () => {
  const onSelect = vi.fn();
  render(<MeasurementCoverage rows={[]} fields={fields} selectedKey="shooting" populationLabel="East group" onSelect={onSelect} />);
  expect(screen.getByText("No published rows")).toBeInTheDocument();
  expect(screen.getByText("0 / 2 fields have values")).toBeInTheDocument();
  const coverage = openCoverage();
  expect(coverage).toHaveTextContent("No published rows are available in this reference population.");
  expect(coverage).not.toHaveTextContent("0%");
  expect(coverage.querySelector(".measurement-coverage-band")).toBeNull();
  fireEvent.click(within(coverage).getByRole("button", { name: "Use Defense rate" }));
  expect(onSelect).toHaveBeenCalledWith("defense");
});

import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import type { LabData, LabDataset } from "@/lib/analytics/labTypes";
import MeasurementLab from "./MeasurementLab";

const fields: LabDataset["fields"] = [{ key: "share", label: "Neutral-site share", unit: "percent" }];
const eras: LabDataset = {
  id: "eras", title: "Soccer eras", sport: "soccer", category: "Game context", source: "soccer_home_advantage",
  description: "Published eras", scope: "Disjoint eras", caveat: "Do not pool eras", status: "Descriptive", fields,
  rows: [
    { id: "early", label: "pre-2000", group: "International soccer", values: { share: 0.24 }, definition: { sport: "International soccer", observationWindow: "pre-2000" } },
    { id: "late", label: "2000+", group: "International soccer", values: { share: 0.29 }, definition: { sport: "International soccer", observationWindow: "2000+" } },
  ],
};
const unknown: LabDataset = {
  ...eras, id: "unknown", title: "Undefined population", rows: [
    { id: "first", label: "First", group: "International soccer", values: { share: 0.2 } },
    { id: "second", label: "Second", group: "International soccer", values: { share: 0.3 } },
  ],
};
const mixed: LabDataset = {
  ...eras, id: "mixed", title: "Mixed definitions", rows: [eras.rows[0], unknown.rows[0]],
};
const crossSport: LabDataset = {
  ...eras, id: "cross-sport", title: "Cross-sport rows", sport: "all", rows: [
    { id: "mlb", label: "MLB", group: "MLB", values: { share: 0.2 }, definition: { sport: "MLB" } },
    { id: "soccer", label: "Soccer", group: "INTERNATIONAL SOCCER", values: { share: 0.3 } },
  ],
};
const data: LabData = { datasets: [eras, unknown, mixed, crossSport], novel: [] };

beforeEach(() => window.history.replaceState(null, "", "/analytics/lab/"));

describe("MeasurementLab population view defaults", () => {
  it("opens unknown rows in the table and labels their order as published source order", () => {
    window.history.replaceState(null, "", "?dataset=unknown");
    render(<MeasurementLab data={data} />);
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Inspect First" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Inspect Second" })).toBeInTheDocument();
    expect(screen.getByLabelText("Rank order")).toBeDisabled();
    expect(screen.getByLabelText("Rank order")).toHaveValue("source");
  });

  it("keeps the first complete era ranked but opens all disjoint eras in a source-order table", () => {
    window.history.replaceState(null, "", "?dataset=eras");
    render(<MeasurementLab data={data} />);
    expect(screen.getByRole("button", { name: "Ranked bars" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("status")).toHaveTextContent("1 row");
    fireEvent.change(screen.getByLabelText("Published group"), { target: { value: "all" } });
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Inspect pre-2000" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Inspect 2000+" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Rank order")).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Published group"), { target: { value: (screen.getByRole("option", { name: /pre-2000/ }) as HTMLOptionElement).value } });
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("Rank order")).not.toBeDisabled();
  });

  it("restores all disjoint eras in the table unless a chart view is explicit", () => {
    window.history.replaceState(null, "", "?dataset=eras&allCohorts=true");
    render(<MeasurementLab data={data} />);
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    act(() => {
      window.history.pushState(null, "", "?dataset=eras&allCohorts=true&view=rank");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(screen.getByRole("button", { name: "Ranked bars" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/Rankings, distributions, and relative positions require/)).toBeInTheDocument();
  });

  it("clears a selected row when moving to all eras and restores the table on history navigation", () => {
    window.history.replaceState(null, "", "?dataset=eras");
    render(<MeasurementLab data={data} />);
    fireEvent.click(screen.getByRole("button", { name: /Inspect pre-2000:/ }));
    expect(screen.getByRole("region", { name: "Selected measurement" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Published group"), { target: { value: "all" } });
    expect(screen.queryByRole("region", { name: "Selected measurement" })).not.toBeInTheDocument();
    expect(window.location.search).not.toContain("row=early");
    expect(window.location.search).toContain("allCohorts=true");
    act(() => {
      window.history.pushState(null, "", "?dataset=eras&allCohorts=true");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
  });

  it("switches dataset, sport, and an unknown cohort to the table when ranking is unavailable", () => {
    render(<MeasurementLab data={data} />);
    fireEvent.change(screen.getByLabelText("Choose dataset"), { target: { value: "unknown" } });
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.change(screen.getByLabelText("Choose dataset"), { target: { value: "mixed" } });
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    const cohort = screen.getByRole("option", { name: "Definition not published" }) as HTMLOptionElement;
    fireEvent.change(screen.getByLabelText("Published group"), { target: { value: cohort.value } });
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.change(screen.getByLabelText("Choose dataset"), { target: { value: "cross-sport" } });
    fireEvent.change(screen.getByLabelText("Filter lab by sport"), { target: { value: "soccer" } });
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Inspect Soccer" })).toBeInTheDocument();
  });
});

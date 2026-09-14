import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import MeasurementLab from "./MeasurementLab";
import type { LabData } from "@/lib/analytics/labTypes";

const fixture: LabData = {
  datasets: [
    {
      id: "cross-sport", title: "Cross-sport metric", sport: "all", category: "Experimental metrics",
      source: "novel_line_half_life", description: "A cross-sport fixture.", scope: "Fixture scope.", caveat: "Fixture caveat.", status: "Descriptive",
      fields: [{ key: "value", label: "Value", unit: "number" }],
      rows: [
        { id: "mlb", label: "MLB", group: "MLB", values: { value: 2 } },
        { id: "tennis", label: "TENNIS", group: "TENNIS", values: { value: 1 } },
      ],
    },
    {
      id: "nba-profile", title: "NBA profile", sport: "nba", category: "Player & team",
      source: "nba_consistency_profiles", description: "An NBA fixture.", scope: "Fixture scope.", caveat: "Fixture caveat.", status: "Descriptive",
      fields: [{ key: "value", label: "Value", unit: "number" }],
      rows: [{ id: "jokic", label: "Nikola Jokic", group: "Published rows", values: { value: 7 }, note: "Fixture detail." }],
    },
  ],
  novel: [],
};

beforeEach(() => window.history.replaceState(null, "", "/analytics/lab"));

describe("MeasurementLab sport filtering and inspection", () => {
  it("filters cross-sport rows and preserves an honest empty state", () => {
    render(<MeasurementLab data={fixture} />);
    fireEvent.change(screen.getByLabelText("Filter lab by sport"), { target: { value: "tennis" } });

    expect(screen.getByRole("status")).toHaveTextContent("1 published row matches");
    expect(screen.getByRole("button", { name: /Inspect TENNIS/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Inspect MLB/ })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Filter lab by sport"), { target: { value: "nba" } });
    expect(screen.getByText(/No published measurements for Basketball in this metric/)).toBeInTheDocument();
  });

  it("selects a metric category dataset and opens row details", () => {
    render(<MeasurementLab data={fixture} />);
    fireEvent.click(screen.getByRole("button", { name: /NBA profile/ }));
    fireEvent.click(screen.getByRole("button", { name: /Inspect Nikola Jokic/ }));

    expect(screen.getByRole("region", { name: "Selected measurement" })).toHaveTextContent("Nikola Jokic");
    expect(screen.getByRole("region", { name: "Selected measurement" })).toHaveTextContent("Fixture detail.");
    expect(screen.getByRole("region", { name: "Selected measurement" })).toHaveTextContent("7");
  });
});

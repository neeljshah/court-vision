import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import MeasurementLab from "./MeasurementLab";
import { getLabData } from "@/lib/analytics/labData";
import type { LabData, LabDataset } from "@/lib/analytics/labTypes";

const base: Omit<LabDataset, "id" | "title" | "publishedAsOf"> = {
  sport: "nba", category: "Fixture", source: "fixture", description: "Fixture.", scope: "Fixture scope.", caveat: "Fixture caveat.", status: "Descriptive",
  fields: [{ key: "value", label: "Value", unit: "number" }], rows: [{ id: "row", label: "Row", group: "Published rows", values: { value: 1 } }],
};
const data: LabData = { datasets: [
  { ...base, id: "stamped", title: "Stamped dataset", publishedAsOf: { date: "2026-07-25", field: "generated_at" } },
  { ...base, id: "unstamped", title: "Unstamped dataset" },
], novel: [] };

beforeEach(() => window.history.replaceState(null, "", "/analytics/lab"));

describe("MeasurementLab dataset as-of", () => {
  it("shows the build-time stamp and the source field that carried it", () => {
    render(<MeasurementLab data={data} />);
    const head = screen.getByRole("heading", { name: "Stamped dataset" }).parentElement as HTMLElement;
    const stamp = within(head).getByText("as of 2026-07-25");
    expect(stamp.tagName).toBe("TIME");
    expect(stamp).toHaveAttribute("dateTime", "2026-07-25");
    expect(head).toHaveTextContent("source field generated_at");
    expect(head).not.toHaveTextContent("as-of not published");
  });

  it("says so when the source publishes no stamp instead of omitting the line", () => {
    render(<MeasurementLab data={data} />);
    fireEvent.click(screen.getByRole("button", { name: /Unstamped dataset/ }));
    const head = screen.getByRole("heading", { name: "Unstamped dataset" }).parentElement as HTMLElement;
    expect(head).toHaveTextContent("as-of not published");
    expect(within(head).queryByText(/^as of /)).not.toBeInTheDocument();
  });

  it("reads the published datasets' stamps at build time", () => {
    window.history.replaceState(null, "", "/analytics/lab?dataset=rim-deterrence");
    render(<MeasurementLab data={getLabData()} />);
    expect(screen.getByText("as of 2026-07-25")).toHaveAttribute("dateTime", "2026-07-25");
    expect(screen.getByText("source field generated_at")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Pitch mix and velocity profiles/ }));
    expect(screen.getByText("as-of not published")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Player consistency/ }));
    expect(screen.getByText("as of 2026-04-12")).toHaveAttribute("dateTime", "2026-04-12");
    expect(screen.getByText("source field as_of")).toBeInTheDocument();
  });
});

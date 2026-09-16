import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LabComparisonContext } from "./LabComparisonContext";
import type { LabRow } from "@/lib/analytics/labTypes";

const rows: LabRow[] = [{ id: "mlb", label: "MLB", group: "MLB", values: { value: 1 }, definition: { sport: "MLB", threshold: 3, unit: "runs", clockField: "inning", season: "2025-26", population: "178 games", observationWindow: "2026-06-18 to 2026-07-17 (30 days)" } }];

describe("LabComparisonContext", () => {
  it("renders only published definition fields", () => {
    render(<LabComparisonContext rows={rows} />);
    const context = screen.getByRole("region", { name: "Published definition" });
    expect(context).toHaveTextContent("MLB");
    expect(context).toHaveTextContent("3 runs");
    expect(context).toHaveTextContent("Unit");
    expect(context).toHaveTextContent("inning");
    expect(context).toHaveTextContent("2025-26");
    expect(context).toHaveTextContent("178 games");
    expect(context).toHaveTextContent("2026-06-18 to 2026-07-17 (30 days)");
  });
  it("marks unavailable core definition fields as not published", () => {
    render(<LabComparisonContext rows={[{ id: "a", label: "A", group: "A", values: { value: 1 } }]} />);
    const context = screen.getByRole("region", { name: "Published definition" });
    expect(context).toHaveTextContent("Sport");
    expect(context).toHaveTextContent("Population");
    expect(context).toHaveTextContent("Observation window");
    expect(context).toHaveTextContent("Not published");
  });
});

import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { basketballResearch } from "@/lib/analytics/researchBasketball";
import { buildLabCSV } from "../lab/LabTable";
import ResearchDetail from "./ResearchDetail";

const analysis = basketballResearch().find(item => item.id === "nba-form-endpoint-elasticity")!;
beforeEach(() => window.history.replaceState(null, "", "/analytics/research/nba-form-endpoint-elasticity/"));

describe("NBA form endpoint context", () => {
  it("lets a reader inspect a short calendar separation without shrinking source support", () => {
    render(<ResearchDetail analysis={analysis} related={[]} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Measurement" }), { target: { value: "endpoint_days" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Eugene Omoruyi" } });
    expect(screen.getByRole("status")).toHaveTextContent("1 matching row");
    fireEvent.click(screen.getByRole("button", { name: "Inspect Eugene Omoruyi: 52" }));
    const inspector = screen.getByRole("region", { name: "Selected measurement" });
    expect(within(inspector).getByText(/2024-02-22/)).toBeInTheDocument();
    expect(within(inspector).getByText(/2024-04-14/)).toBeInTheDocument();
    expect(within(inspector).getByRole("region", { name: "Calculation inputs" })).toHaveTextContent("first_date");
    expect(screen.getByRole("region", { name: "NBA form cohort support" })).toHaveTextContent("807");
    expect(screen.getByRole("region", { name: "NBA form cohort support" })).toHaveTextContent("562");
  });

  it("keeps the published and recomputed three-decimal changes distinct in the inspector", () => {
    render(<ResearchDetail analysis={analysis} related={[]} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Measurement" }), { target: { value: "source_delta" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Myles Turner" } });
    fireEvent.click(screen.getByRole("button", { name: "Inspect Myles Turner: -11.043" }));
    const inspector = screen.getByRole("region", { name: "Selected measurement" });
    expect(within(inspector).getByText("Published endpoint change", { exact: true }).nextElementSibling).toHaveTextContent("-11.043");
    expect(within(inspector).getByText("Recomputed endpoint change", { exact: true }).nextElementSibling).toHaveTextContent("-11.044");
    expect(inspector).toHaveTextContent("rounded separately");
  });

  it("exports endpoint dates, exact source paths and the extra support measurements", () => {
    const victor = analysis.rows.find(row => row.label === "Victor Wembanyama")!;
    const csv = buildLabCSV(analysis, [victor]);
    expect(csv.split("\r\n")).toHaveLength(2);
    expect(csv).toContain("Days between window ends (number; raw value)");
    expect(csv).toContain("Qualifying minutes (number; raw value)");
    expect(csv).toContain("Published endpoint change (number; raw value)");
    expect(csv).toContain("top_movers_risers[0].first_date");
    expect(csv).toContain('""first_window_end"":""2023-11-12""');
    expect(csv).toContain(",880,5429.9,19.821,");
  });
});

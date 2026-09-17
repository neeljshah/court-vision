import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ExactCountExplorer } from "./ExactCountExplorer";
import type { ExactCountData } from "@/lib/analytics/exactCountContext";

const rows = [
  { id: "0-0", balls: 0, strikes: 0, leverageClass: "even", n: 10, topPitchType: "FF", topPitchPct: 30, strikeRate: 0.5, inZoneRate: 0.55 },
  { id: "0-1", balls: 0, strikes: 1, leverageClass: "ahead", n: 8, topPitchType: "SL", topPitchPct: 25, strikeRate: 0.4, inZoneRate: 0.45 },
  { id: "0-2", balls: 0, strikes: 2, leverageClass: "ahead", n: 0, topPitchType: null, topPitchPct: 0, strikeRate: 0, inZoneRate: null },
  ...[1, 2, 3].flatMap(balls => [0, 1, 2].map(strikes => ({ id: `${balls}-${strikes}`, balls, strikes, leverageClass: "behind", n: 1, topPitchType: "FF", topPitchPct: 20, strikeRate: 0.3, inZoneRate: 0.4 }))),
];
const data: ExactCountData = { asOf: "2026-07-25", rows };

describe("ExactCountExplorer", () => {
  it("selects a count cell and updates its published details", () => {
    render(<ExactCountExplorer data={data} />);
    fireEvent.click(screen.getByRole("button", { name: /Use count 0-1/i }));
    expect(screen.getByRole("button", { name: /Use count 0-1/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("region", { name: "Count 0-1 details" })).toHaveTextContent("SL");
    expect(screen.getByText(/pitcher ahead count/i)).toBeInTheDocument();
    expect(screen.getByText("2026-07-25")).toHaveAttribute("dateTime", "2026-07-25");
  });

  it("reports a signed percentage-point comparison without inference", () => {
    render(<ExactCountExplorer data={data} />);
    fireEvent.click(screen.getByRole("button", { name: /Use count 0-1/i }));
    fireEvent.change(screen.getByLabelText("Compare with"), { target: { value: "0-0" } });
    expect(screen.getByRole("region", { name: "Count comparison" })).toHaveTextContent("-10.00 pp");
    expect(screen.getByText(/no weighting or statistical inference/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Top pitch share" }));
    expect(screen.getByText(/most-used pitch in each count/i)).toBeInTheDocument();
  });

  it("keeps zero visible and missing values unpublished without using n as a denominator", () => {
    render(<ExactCountExplorer data={data} />);
    fireEvent.click(screen.getByRole("button", { name: /Use count 0-2/i }));
    const details = screen.getByRole("region", { name: "Count 0-2 details" });
    expect(within(details).getAllByText("0.00%").length).toBeGreaterThan(1);
    expect(within(details).getAllByText("Not published")).toHaveLength(2);
    expect(screen.getByText(/n is the count cohort size only/i)).toBeInTheDocument();
  });

  it("states the coded-strike definition and exposes published rows in a native details table", () => {
    render(<ExactCountExplorer data={data} />);
    expect(screen.getByText(/called, swinging, and foul strikes/i)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Published count states (12 of 12 available)"));
    expect(screen.getByRole("table", { name: "Published exact-count values" })).toBeInTheDocument();
  });

  it("keeps missing coordinates visibly unavailable without discarding published rows", () => {
    render(<ExactCountExplorer data={{ ...data, rows: rows.filter(row => row.id !== "2-1") }} />);
    const missing = screen.getByRole("button", { name: "Use count 2-1, Not published" });
    expect(missing).toBeDisabled();
    expect(screen.getByText(/11 of 12 counts available/i)).toBeInTheDocument();
    expect(screen.getByText("Published count states (11 of 12 available)")).toBeInTheDocument();
  });

  it("uses an available comparison when the default 0-0 count is missing", () => {
    render(<ExactCountExplorer data={{ ...data, rows: rows.filter(row => row.id !== "0-0") }} />);
    expect(screen.getByLabelText("Compare with")).toHaveValue("0-1");
    expect(screen.getByRole("region", { name: "Count comparison" })).toHaveTextContent("0-1: 45.00%; 0-1: 45.00%; signed difference: +0.00 pp");
  });
});

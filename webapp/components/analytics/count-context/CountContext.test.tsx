import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import snapshot from "@/public/data/showcase/mlb_count_leverage.json";
import { buildCountContext, type CountContextData } from "@/lib/analytics/countContext";
import { CountContext } from "./CountContext";

const data = { asOf: "2026-07-25", classes: [
  { id: "behind", definition: "balls exceed strikes", overlapping: false, n: 10, pitchTypeN: 9, pitchMix: [{ pitchType: "FF", n: 4, pct: 44.44 }], remainderPct: 55.56, outcomes: { nType: 10, strikeRate: 0.2, ballRate: 0.3, inplayRate: 0.5, nZone: 9, inZoneRate: 0.6 } },
  { id: "two_strike", definition: "two strikes", overlapping: true, n: 8, pitchTypeN: 7, pitchMix: [{ pitchType: "SL", n: 3, pct: 42.86 }], remainderPct: 57.14, outcomes: { nType: 8, strikeRate: 0.4, ballRate: 0.2, inplayRate: 0.4, nZone: 7, inZoneRate: 0.5 } },
] };

describe("CountContext", () => {
  it("changes the selected pitch-mix table and includes the unpublished remainder", () => {
    render(<CountContext data={data} />);
    const mix = within(screen.getByRole("region", { name: "behind pitch mix table" }));
    expect(mix.getByText("FF")).toBeInTheDocument();
    expect(mix.getByText("44.44%")).toBeInTheDocument();
    expect(screen.getByText("Unpublished remainder")).toBeInTheDocument();
    expect(screen.getByText(/100% minus the sum of the rounded published frequencies/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "two_strike" }));
    expect(within(screen.getByRole("region", { name: "two_strike pitch mix table" })).getByText("SL")).toBeInTheDocument();
  });

  it("renders the overlap distinction and sends the selected class to sequencing", () => {
    render(<CountContext data={data} />);
    expect(screen.getByText(/Overlapping views: two-strike and three-ball/i)).toBeInTheDocument();
    expect(screen.getByText(/Overlapping view; it is not additive/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "two_strike" }));
    expect(screen.getByRole("link", { name: "the two_strike sequencing view" })).toHaveAttribute("href", expect.stringMatching(/^\/analytics\/pitch-sequencing\/?\?class=two_strike$/));
  });

  it("formats all outcome fractions as percentages with their denominators", () => {
    render(<CountContext data={data} />);
    const table = within(screen.getByRole("region", { name: "Outcome proxy comparison" }));
    const row = within(table.getByRole("row", { name: /behind/i }));
    for (const value of ["20.00%", "30.00%", "50.00%", "60.00%"]) expect(row.getByText(value)).toBeInTheDocument();
    expect(row.getAllByText("n 10")).toHaveLength(3);
    expect(row.getByText("n 9")).toBeInTheDocument();
  });

  it("preserves zero, one, and missing outcome-rate endpoints", () => {
    const endpoints: CountContextData = { asOf: null, classes: [{ ...data.classes[0], outcomes: {
      nType: 2, strikeRate: 0, ballRate: 1, inplayRate: null, nZone: 2, inZoneRate: 0,
    } }] };
    render(<CountContext data={endpoints} />);
    const row = within(screen.getByRole("region", { name: "Outcome proxy comparison" }).querySelector("tbody tr") as HTMLElement);
    expect(row.getAllByText("0.00%")).toHaveLength(2);
    expect(row.getByText("100.00%")).toBeInTheDocument();
    expect(row.getByText("Not published")).toBeInTheDocument();
  });

  it("renders the published behind outcome rates at percentage scale", () => {
    render(<CountContext data={buildCountContext(snapshot)} />);
    const table = within(screen.getByRole("region", { name: "Outcome proxy comparison" }));
    const row = within(table.getByRole("row", { name: /behind/i }));
    for (const value of ["49.81%", "30.65%", "19.54%", "58.55%"]) expect(row.getByText(value)).toBeInTheDocument();
  });
});

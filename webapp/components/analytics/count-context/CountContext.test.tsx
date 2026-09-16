import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CountContext } from "./CountContext";

const data = { asOf: "2026-07-25", classes: [
  { id: "behind", definition: "balls exceed strikes", overlapping: false, n: 10, pitchTypeN: 9, pitchMix: [{ pitchType: "FF", n: 4, pct: 44.44 }], remainderPct: 55.56, outcomes: { nType: 10, strikeRate: 0.2, ballRate: 0.3, inplayRate: 0.5, nZone: 9, inZoneRate: 0.6 } },
  { id: "two_strike", definition: "two strikes", overlapping: true, n: 8, pitchTypeN: 7, pitchMix: [{ pitchType: "SL", n: 3, pct: 42.86 }], remainderPct: 57.14, outcomes: { nType: 8, strikeRate: 0.4, ballRate: 0.2, inplayRate: 0.4, nZone: 7, inZoneRate: 0.5 } },
] };

describe("CountContext", () => {
  it("changes the selected pitch-mix table and includes the unpublished remainder", () => {
    render(<CountContext data={data} />);
    expect(within(screen.getByRole("region", { name: "behind pitch mix table" })).getByText("FF")).toBeInTheDocument();
    expect(screen.getByText("Unpublished remainder")).toBeInTheDocument();
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
});

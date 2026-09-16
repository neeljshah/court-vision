import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ClaimHistory } from "./ClaimHistory";
import type { ClaimHistoryLedger } from "@/lib/analytics/claimHistory";

function ledger(): ClaimHistoryLedger {
  const families = Array.from({ length: 26 }, (_, index) => ({
    sport: index % 2 ? "mlb" : "basketball_nba",
    hypothesis: index === 0 ? "undated_family" : `family_${index}`,
    currentStatus: index % 2 ? "verified" : "null",
    verdictSequence: [index % 2 ? "CONFIRMED_LOCAL" : "NULL_LOCAL"],
    flipped: index === 3,
    history: [{ verdict: index % 2 ? "CONFIRMED_LOCAL" : "NULL_LOCAL", status: index % 2 ? "verified" : "null", runTs: index === 0 ? null : "2026-07-01T00:00:00Z", corpus: "published_corpus", n: 30, effect: 1.25 }],
  }));
  return { families, flippedFamilies: families.filter(family => family.flipped), runCount: 26, undatedRunCount: 1, asOf: null, byStatus: { null: 13, verified: 13 } };
}

describe("ClaimHistory", () => {
  it("filters the family count", () => {
    render(<ClaimHistory ledger={ledger()} />);
    expect(screen.getByText("26 of 26 families")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Sport filter"), { target: { value: "mlb" } });
    expect(screen.getByText("13 of 26 families")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Changed verdict only"));
    expect(screen.getByText("1 of 26 families")).toBeInTheDocument();
  });

  it("expands source-ordered history with the undated label", () => {
    render(<ClaimHistory ledger={ledger()} />);
    fireEvent.click(screen.getByRole("button", { name: /undated family/i }));
    const table = screen.getByRole("table", { name: /rerun history for undated family/i });
    expect(within(table).getByText("run date not recorded")).toBeInTheDocument();
    expect(within(table).getByText("unit not recorded")).toBeInTheDocument();
  });

  it("shows the next family window", () => {
    render(<ClaimHistory ledger={ledger()} />);
    expect(screen.queryByRole("button", { name: /family 25/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show more families" }));
    expect(screen.getByRole("button", { name: /family 25/i })).toBeInTheDocument();
  });
});

import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import FavoriteLongshotPage from "./page";
import published from "@/public/data/showcase/market_favorite_longshot.json";

it("discloses MLB records omitted from the published probability bins", () => {
  render(<FavoriteLongshotPage />);
  expect(screen.getByText(/Published bins cover 27,976 of 27,983 source records/)).toHaveTextContent(
    "7 source records are outside the published bins. No bucket-level rates or intervals are published for those records.",
  );
  const tables = screen.getAllByRole("table");
  expect(within(tables[1]).getAllByRole("row")).toHaveLength(5);
  expect(within(tables[1]).getByText("[0.65, 0.8)")).toBeInTheDocument();
  expect(within(tables[1]).getByText("(0.6865, 0.7192)")).toBeInTheDocument();
});

it("reports complete tennis bin coverage without inventing an excluded cohort", () => {
  render(<FavoriteLongshotPage />);
  expect(screen.getByText("Published bins cover 33,713 of 33,713 source records.")).toBeInTheDocument();
  expect(screen.getAllByText(/source records are outside the published bins/)).toHaveLength(1);
});

it("qualifies interval assumptions while preserving every published bucket", () => {
  const { container } = render(<FavoriteLongshotPage />);
  const note = screen.getByRole("note", { name: "Interval assumptions" });
  expect(note).toHaveTextContent("95% coverage is not established");
  expect(note).toHaveTextContent("not a finding of duplicate or dependent records");
  expect(container).not.toHaveTextContent("each row is one independent match/game");
  expect(container).not.toHaveTextContent("Wilson CIs are valid here");
  expect(container).not.toHaveTextContent("The result reinforces that the market is efficient");
  expect(screen.getAllByRole("columnheader", { name: "Nominal 95% Wilson" })).toHaveLength(2);
  expect(within(note).getByRole("link", { name: "Wilson interval method (NIST)" })).toHaveAttribute(
    "href", "https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm",
  );
  for (const [index, block] of [published.sports.tennis, published.sports.mlb].entries()) {
    const rows = within(screen.getAllByRole("table")[index]).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(block.buckets.length);
    block.buckets.forEach((bucket, rowIndex) => {
      expect(within(rows[rowIndex]).getAllByRole("cell").map((cell) => cell.textContent)).toEqual([
        `[${bucket.lo}, ${bucket.hi})`, bucket.n.toLocaleString(), String(bucket.impl), String(bucket.real),
        bucket.gap > 0 ? `+${bucket.gap}` : String(bucket.gap), `(${bucket.wilson_lo}, ${bucket.wilson_hi})`,
      ]);
    });
  }
  expect(screen.getByRole("button", { name: "Receipt: descriptive_only for Snapshot generated 2026-07-25" })).toBeInTheDocument();
});

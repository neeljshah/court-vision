import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import FavoriteLongshotPage from "./page";

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

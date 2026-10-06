import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import scoreboard from "../../../public/data/showcase/cross_sport_scoreboard.json";

// Keep the real Home, artifact reader, chart, and receipt components. Atlas
// inventory is unrelated to these scoreboard assertions.
vi.mock("@/lib/atlas.server", () => ({ listPacks: () => [] }));

import Home from "../page";

const fmt = (value: number) => (value >= 0 ? "+" : "") + value.toFixed(4);

describe("Home scoreboard evidence", () => {
  it.each([
    "MARKET_SHARPER_PROVISIONAL",
    "MODEL_SHARPER_PROVISIONAL",
    "UNDERPOWERED",
  ])("retains the full visible %s verdict in every matching row", (verdict) => {
    render(<Home />);
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    const matching = scoreboard.rows
      .map((row, index) => ({ row, index }))
      .filter(({ row }) => row.verdict === verdict);

    expect(matching.length).toBeGreaterThan(0);
    for (const { index } of matching) {
      const cells = within(rows[index]).getAllByRole("cell");
      // Scope to the visible verdict cell: tooltip metadata and chart aria
      // labels must not mask a missing qualification in the displayed pill.
      expect(cells[6]).toHaveTextContent(verdict.replace(/_/g, " "));
      expect(cells[6].textContent?.trim()).toBe(verdict.replace(/_/g, " "));
    }
  });

  it("keeps all staged rows with their sample sizes, intervals, and receipts", () => {
    render(<Home />);
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(scoreboard.n_rows);

    for (const [index, row] of scoreboard.rows.entries()) {
      const cells = within(rows[index]).getAllByRole("cell");
      expect(cells[0].textContent).toBe(row.sport);
      expect(cells[1].textContent).toBe(row.market);
      expect(cells[2].textContent).toBe(row.checkpoint);
      expect(cells[3].textContent).toBe(String(row.n));
      expect(within(cells[4]).getByText(fmt(row.paired_delta_mean))).toBeVisible();
      expect(cells[5].textContent?.trim()).toBe(
        `[${fmt(row.paired_delta_95ci[0])}, ${fmt(row.paired_delta_95ci[1])}]`
      );
      expect(within(cells[4]).getByRole("button", {
        name: "show receipt: source, as-of, verification",
      })).toBeVisible();
    }
  });
});

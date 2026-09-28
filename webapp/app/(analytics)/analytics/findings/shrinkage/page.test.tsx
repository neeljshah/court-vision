import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import source from "@/public/data/showcase/mlb_shrinkage.json";
import * as artifacts from "@/lib/showcase.server";
import ShrinkagePage from "./page";

describe("shrinkage published evidence", () => {
  it("distinguishes catcher source rows from people and retains both repeated-name records", () => {
    render(<ShrinkagePage />);
    const catcher = source.groups.find(group => group.key === "catcher_ooz")!;
    expect(screen.getByText(/distinct catcher identities unavailable/)).toHaveTextContent(`${catcher.n_entities} source rows`);
    expect(screen.getByText(/The source publishes names without catcher IDs/)).toHaveTextContent("Repeated display names remain separate rows");
    const table = screen.getByRole("region", { name: `${catcher.label} biggest regressors scroll horizontally` });
    const repeated = within(table).getAllByRole("rowheader", { name: "Carlos P\u00e9rez" });
    expect(repeated).toHaveLength(2);
    expect(repeated.map(header => within(header.closest("tr")!).getAllByRole("cell").map(cell => cell.textContent)))
      .toEqual([["1,277", "0.2388", "0.2556", "-0.0168"], ["2,234", "0.2534", "0.261", "-0.0076"]]);
  });

  it("preserves every published table value and row order under an explicit signed-gap header", () => {
    render(<ShrinkagePage />);
    for (const group of source.groups) {
      for (const [key, label] of [["biggest_regressors", "biggest regressors"], ["top_by_shrunk", "shrunk leaderboard"]] as const) {
        const region = screen.getByRole("region", { name: `${group.label} ${label} scroll horizontally` });
        const rows = within(region).getAllByRole("row").slice(1);
        expect(rows).toHaveLength(group[key].length);
        group[key].forEach((published, index) => {
          expect(within(rows[index]).getByRole("rowheader").textContent).toBe(published.name);
          const values = [published.n.toLocaleString(), String(published.raw_rate), String(published.shrunk_rate)];
          if ("regression" in published) {
            const gap = Number(published.regression);
            values.push(gap >= 0 ? `+${gap}` : String(gap));
            expect(Math.abs(published.raw_rate - published.shrunk_rate - gap)).toBeLessThanOrEqual(0.00011);
          }
          expect(within(rows[index]).getAllByRole("cell").map(cell => cell.textContent)).toEqual(values);
        });
      }
    }
    expect(screen.getAllByRole("columnheader", { name: "Raw minus shrunk" })).toHaveLength(source.groups.length);
    expect(screen.queryByRole("columnheader", { name: "Moved by" })).not.toBeInTheDocument();
  });

  it("explains both directions and the modeling limits without changing the observation window", () => {
    render(<ShrinkagePage />);
    expect(screen.getAllByText(/negative means shrinkage raised the rate; positive means it lowered it/)).toHaveLength(source.groups.length);
    expect(screen.getAllByText(/not a validated ranking of skill/)).toHaveLength(source.groups.length);
    expect(screen.getByText(/^Window:/)).toHaveTextContent("2022-2023 Statcast slice (statcast_fuller_v1)");
    expect(screen.getByText(/regularized estimate under a modeling/)).toBeVisible();
    expect(screen.queryByText(/the honest ranking/)).not.toBeInTheDocument();
  });

  it("keeps the unavailable state when no snapshot can be read", () => {
    const mock = vi.spyOn(artifacts, "loadArtifact").mockReturnValue(null);
    try {
      render(<ShrinkagePage />);
      expect(screen.getByRole("heading", { level: 1 })).toBeVisible();
      expect(screen.queryByRole("table")).not.toBeInTheDocument();
      expect(screen.queryByText(/source rows/)).not.toBeInTheDocument();
    } finally {
      mock.mockRestore();
    }
  });
});

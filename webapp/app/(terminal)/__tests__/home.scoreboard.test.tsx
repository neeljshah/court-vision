import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import scoreboard from "../../../public/data/showcase/cross_sport_scoreboard.json";
import Home from "../page";
import { modelMinusMarket } from "@/lib/scoreboardDelta";
import { byEvidenceWeight, SMALL_SAMPLE_NOTE, type ScoreRow } from "@/components/home/HomeScoreboard";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

const fmt = (value: number) => (value >= 0 ? "+" : "") + value.toFixed(4);
const sorted = byEvidenceWeight(scoreboard.rows as ScoreRow[]);

describe("Home in-game scoreboard (below the fold)", () => {
  it("keeps every staged row, sorted by n, with sample size, interval, verdict and receipt", () => {
    render(<Home />);
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(scoreboard.n_rows);
    for (const [i, row] of sorted.entries()) {
      const cells = within(rows[i]).getAllByRole("cell");
      expect(cells[0].textContent).toBe(row.sport);
      expect(cells[3].textContent).toBe(String(row.n));
      const d = modelMinusMarket(row.paired_delta_mean, row.paired_delta_95ci as [number, number]);
      expect(within(cells[4]).getByText(fmt(d.delta))).toBeVisible();
      expect(cells[5].textContent?.trim()).toBe(`[${fmt(d.ci[0])}, ${fmt(d.ci[1])}]`);
      expect(cells[6].textContent).toContain(row.verdict);
      expect(within(cells[4]).getByRole("button", { name: /show receipt/ })).toBeVisible();
    }
    const ns = sorted.map((r) => r.n);
    expect(ns).toEqual([...ns].sort((a, b) => b - a));
  });

  it("every small-sample MODEL_SHARPER_PROVISIONAL row carries the qualifier and sits below larger-n rows", () => {
    render(<Home />);
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    sorted.forEach((r, i) => {
      if (r.verdict.startsWith("MODEL_SHARPER")) expect(rows[i].textContent).toContain(SMALL_SAMPLE_NOTE);
    });
  });
});

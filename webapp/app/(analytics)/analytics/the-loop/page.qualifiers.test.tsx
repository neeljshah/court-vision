import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fireEvent, getDefaultNormalizer, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import TheLoopPage from "./page";

interface SourceFamily {
  sport: string;
  hypothesis: string;
  verdict_sequence: string[];
  history: Array<{ verdict: string; corpus: string | null; n: number | null }>;
}

const source = JSON.parse(readFileSync(
  join(process.cwd(), "public/data/showcase/fwd_claim_scoreboard.json"), "utf-8",
)) as { flipped_families: SourceFamily[] };
const fatigue = source.flipped_families.find(family => family.hypothesis === "three_in_four_fatigue")!;

describe("The Loop published verdict qualifiers", () => {
  it("keeps each source verdict's qualifier in the visible flip badge sequence", () => {
    expect(fatigue.verdict_sequence).toEqual(["NULL_LOCAL", "CONFIRMED_LOCAL"]);
    expect(source.flipped_families.some(family => family.verdict_sequence.includes("PROVISIONAL"))).toBe(true);
    render(<TheLoopPage />);
    const flips = screen.getByRole("region", { name: "Verdict flips" });

    for (const family of source.flipped_families) {
      const title = within(flips).getByText(family.hypothesis.replaceAll("_", " "), {
        exact: true,
        normalizer: getDefaultNormalizer({ collapseWhitespace: false }),
      });
      // The title's next sibling contains only visible verdict badges. Receipt
      // labels, chart text and full history cannot satisfy this assertion.
      const sequence = title.nextElementSibling!;
      const badges = Array.from(sequence.children).map(wrapper => wrapper.lastElementChild!);
      expect(badges.map(badge => badge.textContent?.trim()), family.hypothesis)
        .toEqual(family.verdict_sequence.map(verdict => verdict.replaceAll("_", " ")));
      badges.forEach(badge => expect(badge).toBeVisible());
    }
  });

  it("preserves qualified rerun verdicts and their public corpus provenance", () => {
    render(<TheLoopPage />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search families" }), {
      target: { value: fatigue.hypothesis },
    });
    fireEvent.click(screen.getByRole("button", { name: /NBA three in four fatigue/ }));
    const history = screen.getByRole("table", { name: "Rerun history for three in four fatigue" });
    const rows = within(history).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(fatigue.history.length);
    rows.forEach((row, index) => {
      const cells = within(row).getAllByRole("cell");
      const run = fatigue.history[index];
      expect(cells[0]).toHaveTextContent(run.verdict.replaceAll("_", " "));
      expect(cells[3].textContent).toBe(run.corpus);
      expect(cells[4].textContent).toBe(run.n?.toLocaleString("en-US"));
    });
  });
});

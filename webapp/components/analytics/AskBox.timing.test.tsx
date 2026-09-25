import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { loadScoutCorpus } from "@/lib/analytics/scoutCorpus.server";
import { AskBox } from "./AskBox";

const entries = loadScoutCorpus();
const lcf = "novel_live_clock_fraction";
const mfp = "novel_market_foresight_premium";

function ask(question: string) {
  fireEvent.change(screen.getByLabelText("Ask Scout a question"), { target: { value: question } });
  fireEvent.click(screen.getByRole("button", { name: "Search Scout's cited answers" }));
  return within(screen.getByRole("region", { name: "Scout answer" }));
}

function expectSource(module: string) {
  expect(screen.getByRole("link", { name: "Open published source" }))
    .toHaveAttribute("href", `/data/showcase/${module}.json`);
  expect(screen.getByRole("link", { name: "Read analysis" }))
    .toHaveAttribute("href", `/analytics/m/${module}`);
  expect(screen.getByRole("region", { name: "Scout answer" }))
    .toHaveTextContent("observation window is not published");
  expect(screen.queryByRole("button", { name: /Source as of 2026-07-24/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Source as of 2026-09-17/ })).not.toBeInTheDocument();
}

beforeEach(() => window.history.replaceState(null, "", "/analytics/ask/"));

describe("Scout timing answers rendered from the committed corpus", () => {
  it("shows corrected LCF support and keeps the threshold follow-up on current evidence", () => {
    render(<AskBox entries={entries} tours={[]} />);
    const result = ask("How small are the Live-Clock Fraction samples?");
    const answer = result.getByLabelText("Cited answer");
    for (const count of ["174", "97", "26", "12"]) expect(answer).toHaveTextContent(count);
    expectSource(lcf);
    fireEvent.click(result.getByRole("button", { name: "How is the Live-Clock Fraction threshold chosen?" }));
    expect(screen.getByLabelText("Cited answer")).toHaveTextContent("0.5575");
    expect(screen.getByLabelText("Cited answer")).toHaveTextContent("0.4615");
    expectSource(lcf);
    expect(new URLSearchParams(window.location.search).get("q"))
      .toBe("How is the Live-Clock Fraction threshold chosen?");
  });

  it("retrieves the MFP alias with corrected observations and a closing-reference limitation", () => {
    render(<AskBox entries={entries} tours={[]} />);
    const result = ask("mlb mfp curve");
    const answer = result.getByLabelText("Cited answer");
    for (const value of ["0.051", "0.411", "46"]) expect(answer).toHaveTextContent(value);
    expect(answer.textContent?.toLowerCase()).toContain("closing reference");
    expect(answer.textContent?.toLowerCase()).toContain("observations");
    expect(answer).not.toHaveTextContent("rises steadily");
    expectSource(mfp);
  });

  it("preserves missing NBA coverage as a sourced NO_DATA answer", () => {
    render(<AskBox entries={entries} tours={[]} />);
    const result = ask("Why is there no NBA Live-Clock Fraction?");
    expect(result.getByRole("button", { name: /^Receipt: NO_DATA/ })).toBeInTheDocument();
    expect(result.getByLabelText("Cited answer")).toHaveTextContent("not_buildable");
    expectSource(lcf);
  });
});

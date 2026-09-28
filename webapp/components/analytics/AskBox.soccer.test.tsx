import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { loadScoutCorpus } from "@/lib/analytics/scoutCorpus.server";
import { AskBox } from "./AskBox";

const entries = loadScoutCorpus();
const question = "How often does Arsenal keep clean sheets?";

function ask(query: string) {
  fireEvent.change(screen.getByLabelText("Ask Scout a question"), { target: { value: query } });
  fireEvent.click(screen.getByRole("button", { name: "Search Scout's cited answers" }));
  return within(screen.getByRole("region", { name: "Scout answer" }));
}

beforeEach(() => window.history.replaceState(null, "", "/analytics/ask/"));

describe("Scout soccer clean-sheet answers", () => {
  it("shows the source, observation window, and a filtered measurement link", () => {
    render(<AskBox entries={entries} tours={[]} />);
    const result = ask(question);
    const answer = result.getByLabelText("Cited answer");
    expect(answer).toHaveTextContent("60.0%");
    expect(answer).toHaveTextContent("exactly 10 strictly prior all-venue (home or away) matches");
    expect(answer).toHaveTextContent("latest match was dropped");
    expect(answer).toHaveTextContent("Per-team match dates are unpublished");
    expect(answer).toHaveTextContent("historical descriptive snapshot");
    expect(result.getByRole("link", { name: "Open published source" }))
      .toHaveAttribute("href", "/data/showcase/atlas_soccer_manifest.json");
    const destination = new URL(result.getByRole("link", { name: "Read analysis" }).getAttribute("href")!, "https://example.test");
    expect(destination.pathname.replace(/\/$/, "")).toBe("/analytics/research/soccer-trailing-attack-defense");
    expect(Object.fromEntries(destination.searchParams)).toEqual({ q: "Arsenal", metric: "clean_sheet_rate_l10", row: "soccer-scoring-arsenal" });
    expect(new URLSearchParams(window.location.search).get("q")).toBe(question);
  });

  it("restores a shared question and replaces it with another team's alias", () => {
    window.history.replaceState(null, "", `/analytics/ask/?${new URLSearchParams({ q: question })}`);
    render(<AskBox entries={entries} tours={[]} />);
    expect(screen.getByLabelText("Cited answer")).toHaveTextContent("Arsenal's published clean-sheet rate is 60.0%");
    expect(ask("Bayern Munich clean sheets").getByLabelText("Cited answer"))
      .toHaveTextContent("Bayern Munich's published clean-sheet rate is 30.0%");
  });

  it("does not present this snapshot as a current, home-only, or negated answer", () => {
    render(<AskBox entries={entries} tours={[]} />);
    for (const query of ["Arsenal clean sheets today", "Arsenal home clean sheets", "Arsenal does not keep clean sheets"]) {
      const result = ask(query);
      if (query.includes("today")) expect(result.getByRole("button", { name: /^Receipt: NO_DATA/ })).toBeInTheDocument();
      else expect(result.queryByLabelText("Cited answer")).not.toBeInTheDocument();
      expect(screen.getByRole("region", { name: "Scout answer" })).not.toHaveTextContent("published clean-sheet rate is");
    }
  });

  it("rejects external destinations and unrecognized research query parameters", () => {
    const entry = entries.find(candidate => candidate.q === question)!;
    for (const path of ["https://example.test/analytics/research/test/", "//example.test/analytics/research/test/", "/analytics/research/test/?redirect=https://example.test", "/analytics/players/soccer/arsenal?q=Arsenal"]) {
      const { unmount } = render(<AskBox entries={[{ ...entry, a: { ...entry.a, explore_path: path } }]} tours={[]} />);
      ask(question);
      expect(screen.queryByRole("link", { name: "Read analysis" })).not.toBeInTheDocument();
      unmount();
    }
  });
});

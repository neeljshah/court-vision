import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AskBox } from "./AskBox";

const entries = [{
  q: "Known question",
  alt_phrasings: [],
  tags: ["known", "metric"],
  bucket: "test",
  a: { status: "ok" as const, answer: "Committed answer.", source_artifact: "public.json", as_of: "2026-01-01" },
}];

describe("AskBox", () => {
  it("keeps the submitted question attached to its result while the input changes", () => {
    render(<AskBox entries={entries} tours={[]} />);
    const input = screen.getByLabelText("Ask Scout a question");
    fireEvent.change(input, { target: { value: "Known question" } });
    fireEvent.click(screen.getByRole("button", { name: "Search Scout's cited answers" }));

    fireEvent.change(input, { target: { value: "A new, unsubmitted question" } });
    expect(screen.getByLabelText("Cited answer")).toHaveTextContent("Known question");
    expect(screen.getByLabelText("Cited answer")).not.toHaveTextContent("A new, unsubmitted question");
    expect(window.location.search).toBe("?q=Known+question");
  });

  it("links a derived answer to its validated internal analysis path", () => {
    const derived = [{ ...entries[0], a: { ...entries[0].a, explore_path: "/analytics/research/nba-matchup-profile-contrast/" } }];
    render(<AskBox entries={derived} tours={[]} />);
    fireEvent.change(screen.getByLabelText("Ask Scout a question"), { target: { value: "Known question" } });
    fireEvent.click(screen.getByRole("button", { name: "Search Scout's cited answers" }));

    expect(screen.getByRole("link", { name: "Read analysis" })).toHaveAttribute("href", "/analytics/research/nba-matchup-profile-contrast");
    expect(screen.getByRole("link", { name: "Open published answer record" })).toBeInTheDocument();
  });

  it("does not render an internal link for an unvalidated path", () => {
    const invalid = [{ ...entries[0], a: { ...entries[0].a, explore_path: "https://example.test/" } }];
    render(<AskBox entries={invalid} tours={[]} />);
    fireEvent.change(screen.getByLabelText("Ask Scout a question"), { target: { value: "Known question" } });
    fireEvent.click(screen.getByRole("button", { name: "Search Scout's cited answers" }));

    expect(screen.queryByRole("link", { name: "Read analysis" })).not.toBeInTheDocument();
  });

  it("uses the readable profile route as the primary action and keeps source JSON secondary", () => {
    const profile = [{ ...entries[0], bucket: "public-entity-profile", a: { ...entries[0].a, source_artifact: "webapp/public/data/showcase/atlas_nba_manifest.json", explore_path: "/analytics/players/nba_players/nikola_jokic" } }];
    render(<AskBox entries={profile} tours={[]} />);
    fireEvent.change(screen.getByLabelText("Ask Scout a question"), { target: { value: "Known question" } });
    fireEvent.click(screen.getByRole("button", { name: "Search Scout's cited answers" }));
    expect(screen.getByRole("link", { name: "Open profile" })).toHaveAttribute("href", "/analytics/players/nba_players/nikola_jokic");
    expect(screen.getByRole("link", { name: "Open published source" })).toHaveAttribute("href", "/data/showcase/atlas_nba_manifest.json");
  });

  it("labels a published module destination as the primary action", () => {
    const moduleEntries = [{ ...entries[0], bucket: "public-analytics-module", a: { ...entries[0].a, explore_path: "/analytics/m/calibration_over_time" } }];
    render(<AskBox entries={moduleEntries} tours={[]} />);
    fireEvent.change(screen.getByLabelText("Ask Scout a question"), { target: { value: "Known question" } });
    fireEvent.click(screen.getByRole("button", { name: "Search Scout's cited answers" }));
    expect(screen.getByRole("link", { name: "Open module" })).toHaveAttribute("href", "/analytics/m/calibration_over_time");
  });

  it("renders a recognized pair's compare route as the primary action", () => {
    const pairEntries = [
      { ...entries[0], q: "Nikola Jokic profile", entity: { name: "Nikola Jokic", pack: "nba_players", slug: "nikola_jokic" } },
      { ...entries[0], q: "Giannis Antetokounmpo profile", entity: { name: "Giannis Antetokounmpo", pack: "nba_players", slug: "giannis_antetokounmpo" } },
    ];
    render(<AskBox entries={pairEntries} tours={[]} />);
    fireEvent.change(screen.getByLabelText("Ask Scout a question"), { target: { value: "Compare Jokic and Giannis" } });
    fireEvent.click(screen.getByRole("button", { name: "Search Scout's cited answers" }));

    expect(screen.getByRole("link", { name: "Compare Nikola Jokic and Giannis Antetokounmpo" })).toHaveAttribute(
      "href", "/analytics/compare?pack=nba_players&a=nikola_jokic&b=giannis_antetokounmpo"
    );
  });

  it("renders an explicit profile choice for an ambiguous short name", () => {
    const players = [
      { ...entries[0], q: "Stephen Curry profile", entity: { name: "Stephen Curry", pack: "nba_players", slug: "stephen_curry" } },
      { ...entries[0], q: "Seth Curry profile", entity: { name: "Seth Curry", pack: "nba_players", slug: "seth_curry" } },
    ];
    render(<AskBox entries={players} tours={[]} />);
    fireEvent.change(screen.getByLabelText("Ask Scout a question"), { target: { value: "Curry" } });
    fireEvent.click(screen.getByRole("button", { name: "Search Scout's cited answers" }));

    expect(screen.getByText("Did you mean:")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Stephen Curry (NBA players)" })).toHaveAttribute(
      "href", "/analytics/players/nba_players/stephen_curry"
    );
    expect(screen.getByRole("link", { name: "Seth Curry (NBA players)" })).toHaveAttribute(
      "href", "/analytics/players/nba_players/seth_curry"
    );
    expect(screen.queryByLabelText("Cited answer")).not.toBeInTheDocument();
  });

  it("does not repeat a suggested question in the follow-up panel", () => {
    const withFollowUp = [...entries, { ...entries[0], q: "Try another question" }];
    render(<AskBox entries={withFollowUp} tours={[{ label: "Start here", questions: ["Try another question"] }]} />);
    fireEvent.change(screen.getByLabelText("Ask Scout a question"), { target: { value: "Known question" } });
    fireEvent.click(screen.getByRole("button", { name: "Search Scout's cited answers" }));

    expect(screen.queryByText("Continue exploring")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Try another question" })).toHaveLength(1);
  });

  it("focuses the updated answer after a follow-up replaces the result", async () => {
    const followUpEntries = [...entries, { ...entries[0], q: "Try another question" }];
    render(<AskBox entries={followUpEntries} tours={[]} />);
    fireEvent.change(screen.getByLabelText("Ask Scout a question"), { target: { value: "Known question" } });
    fireEvent.click(screen.getByRole("button", { name: "Search Scout's cited answers" }));
    fireEvent.click(screen.getByRole("button", { name: "Try another question" }));

    const answer = screen.getByRole("region", { name: "Scout answer" });
    await waitFor(() => expect(answer).toHaveFocus());
    expect(answer).toHaveTextContent("Try another question");
  });

  it("keeps tour suggestions focused on the search input", async () => {
    render(<AskBox entries={entries} tours={[{ label: "Start here", questions: ["Known question"] }]} />);
    const input = screen.getByLabelText("Ask Scout a question");
    fireEvent.click(screen.getByRole("button", { name: "Known question" }));

    await waitFor(() => expect(input).toHaveFocus());
    expect(screen.getByRole("region", { name: "Scout answer" })).toHaveTextContent("Committed answer.");
  });

  it("uses plain-language source help and labels related results clearly", () => {
    const related = [{ ...entries[0], q: "Closest available question", alt_phrasings: ["Related question"] }];
    render(<AskBox entries={related} tours={[]} />);
    fireEvent.change(screen.getByLabelText("Ask Scout a question"), { target: { value: "Different available question" } });
    fireEvent.click(screen.getByRole("button", { name: "Search Scout's cited answers" }));

    expect(screen.getByText("Scout searches published answers and links each result to its source.")).toBeInTheDocument();
    expect(screen.getByText("Closest available question:")).toBeInTheDocument();
  });
});

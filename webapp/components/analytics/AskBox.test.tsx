import { fireEvent, render, screen } from "@testing-library/react";
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

    expect(screen.getByRole("link", { name: "Explore this analysis" })).toHaveAttribute("href", "/analytics/research/nba-matchup-profile-contrast/");
    expect(screen.getByRole("link", { name: "Open published answer record" })).toBeInTheDocument();
  });

  it("does not render an internal link for an unvalidated path", () => {
    const invalid = [{ ...entries[0], a: { ...entries[0].a, explore_path: "https://example.test/" } }];
    render(<AskBox entries={invalid} tours={[]} />);
    fireEvent.change(screen.getByLabelText("Ask Scout a question"), { target: { value: "Known question" } });
    fireEvent.click(screen.getByRole("button", { name: "Search Scout's cited answers" }));

    expect(screen.queryByRole("link", { name: "Explore this analysis" })).not.toBeInTheDocument();
  });

  it("does not repeat a suggested question in the follow-up panel", () => {
    const withFollowUp = [...entries, { ...entries[0], q: "Try another question" }];
    render(<AskBox entries={withFollowUp} tours={[{ label: "Start here", questions: ["Try another question"] }]} />);
    fireEvent.change(screen.getByLabelText("Ask Scout a question"), { target: { value: "Known question" } });
    fireEvent.click(screen.getByRole("button", { name: "Search Scout's cited answers" }));

    expect(screen.queryByText("Continue exploring")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Try another question" })).toHaveLength(1);
  });
});

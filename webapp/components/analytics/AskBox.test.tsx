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
});

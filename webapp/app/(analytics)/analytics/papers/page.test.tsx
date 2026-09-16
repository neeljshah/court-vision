import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PapersIndex from "@/components/analytics/papers/PapersIndex";
import { loadPapers } from "@/lib/analytics/papers.server";
import { SPORT_LABELS } from "@/lib/analytics/papers";
import PapersIndexPage from "./page";

describe("PapersIndexPage", () => {
  it("lists one card per published paper", () => {
    const papers = loadPapers();
    const { container } = render(<PapersIndexPage />);
    const cards = container.querySelectorAll("a.paper-card");
    expect(cards).toHaveLength(papers.length);
    expect(screen.getByRole("status")).toHaveTextContent(`${papers.length} of ${papers.length}`);
    papers.forEach(paper => {
      expect(screen.getByRole("heading", { name: paper.title })).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: paper.title }).closest("a"))
        .toHaveAttribute("href", expect.stringMatching(new RegExp(`/analytics/papers/${paper.slug}/?$`)));
    });
  });

  it("puts the sample paper's own date, sport, reading time and artifact count on its card", () => {
    const paper = loadPapers().find(entry => entry.slug === "how-to-read-a-courtvision-paper");
    expect(paper).toBeDefined();
    render(<PapersIndexPage />);
    const card = screen.getByRole("heading", { name: paper!.title }).closest("a") as HTMLElement;
    expect(card.textContent).toContain(paper!.date);
    expect(card.textContent).toContain(SPORT_LABELS[paper!.sport]);
    expect(card.textContent).toContain(`${paper!.evidence.length} artifacts`);
    expect(card.textContent).toContain(paper!.abstract.slice(0, 60));
  });

  it("narrows the list with a keyword select and restores it", () => {
    const papers = loadPapers();
    render(<PapersIndex papers={papers} />);
    const keyword = papers[0].keywords[0];
    const expected = papers.filter(paper => paper.keywords.includes(keyword)).length;
    fireEvent.change(screen.getByLabelText("Keyword"), { target: { value: keyword } });
    expect(screen.getByRole("status")).toHaveTextContent(`${expected} of ${papers.length}`);
    fireEvent.change(screen.getByLabelText("Keyword"), { target: { value: "any" } });
    expect(screen.getByRole("status")).toHaveTextContent(`${papers.length} of ${papers.length}`);
  });

  it("shows an empty state when nothing is published", () => {
    render(<PapersIndex papers={[]} />);
    expect(screen.getByText(/No papers are published yet/)).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

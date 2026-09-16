import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { loadPapers } from "@/lib/analytics/papers.server";
import PaperPage, { generateMetadata, generateStaticParams } from "./page";

const SAMPLE = "how-to-read-a-courtvision-paper";

describe("PaperPage", () => {
  it("emits a static param for every published paper", () => {
    expect(generateStaticParams()).toEqual(loadPapers().map(paper => ({ slug: paper.slug })));
  });

  it("renders the sample paper with its sections, evidence and back link", () => {
    const paper = loadPapers().find(entry => entry.slug === SAMPLE);
    expect(paper).toBeDefined();
    render(<PaperPage params={{ slug: SAMPLE }} />);

    expect(screen.getByRole("heading", { level: 1, name: paper!.title })).toBeInTheDocument();
    const toc = screen.getByRole("navigation", { name: "Sections" });
    expect(within(toc).getAllByRole("link")).toHaveLength(paper!.sections.length);
    paper!.sections.forEach(section => {
      // Section and box headings share text ("Limitations"), so scope by the section id.
      const body = document.getElementById(section.id) as HTMLElement;
      expect(body).not.toBeNull();
      expect(within(body).getByRole("heading", { level: 2 }).textContent).toContain(section.heading);
    });
    const evidence = screen.getByRole("region", { name: "Evidence" });
    paper!.evidence.forEach(entry => expect(within(evidence).getByText(entry.artifact)).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /Research papers/ }))
      .toHaveAttribute("href", expect.stringMatching(/\/analytics\/papers\/?$/));
  });

  it("titles the page metadata from the paper itself", () => {
    const paper = loadPapers().find(entry => entry.slug === SAMPLE);
    expect(generateMetadata({ params: { slug: SAMPLE } }).title).toBe(paper!.title);
    expect(generateMetadata({ params: { slug: "no-such-paper" } }).title).toBe("Research paper");
  });
});

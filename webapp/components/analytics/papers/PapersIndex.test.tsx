import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import PapersIndex from "./PapersIndex";
import type { Paper } from "@/lib/analytics/papers";

const papers: Paper[] = [
  {
    slug: "nba-profile", title: "NBA profile", subtitle: "A published NBA description.", authors: ["CourtVision"], date: "2026-09-01",
    sport: "nba", keywords: ["shot profile"], abstract: "A short description of a published NBA measurement.",
    sections: [{ id: "method", heading: "Method", blocks: [{ type: "p", text: "Published method." }] }],
    evidence: [{ artifact: "nba.json", module: "nba-module", asOf: null, fields: ["value"] }], limitations: ["A limitation."], related: [],
  },
  {
    slug: "mlb-profile", title: "MLB profile", subtitle: "A published MLB description.", authors: ["CourtVision"], date: "2026-09-02",
    sport: "mlb", keywords: ["pitch mix"], abstract: "A short description of a published MLB measurement.",
    sections: [{ id: "method", heading: "Method", blocks: [{ type: "p", text: "Published method." }] }],
    evidence: [{ artifact: "mlb.json", module: "mlb-module", asOf: null, fields: ["value"] }], limitations: ["A limitation."], related: [],
  },
];

describe("PapersIndex", () => {
  beforeEach(() => window.history.replaceState(null, "", "/analytics/papers/"));
  afterEach(() => window.history.replaceState(null, "", "/analytics/papers/"));

  it("restores valid URL filters and falls back from unknown values", async () => {
    window.history.replaceState(null, "", "/analytics/papers/?sport=nba&keyword=shot%20profile");
    const { unmount } = render(<PapersIndex papers={papers} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "NBA" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByLabelText("Keyword")).toHaveValue("shot profile");
    unmount();

    window.history.replaceState(null, "", "/analytics/papers/?sport=cricket&keyword=unknown");
    render(<PapersIndex papers={papers} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "All sports" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByLabelText("Keyword")).toHaveValue("any");
  });

  it("writes encoded keyword filters without disturbing unrelated URL state", async () => {
    window.history.replaceState({ preserved: true }, "", "/analytics/papers/?source=brief#filters");
    render(<PapersIndex papers={papers} />);
    await screen.findByLabelText("Keyword");
    fireEvent.click(screen.getByRole("button", { name: "MLB" }));
    fireEvent.change(screen.getByLabelText("Keyword"), { target: { value: "pitch mix" } });
    await waitFor(() => expect(window.location.search).toContain("keyword=pitch+mix"));
    const params = new URLSearchParams(window.location.search);
    expect(params.get("sport")).toBe("mlb");
    expect(params.get("keyword")).toBe("pitch mix");
    expect(params.get("source")).toBe("brief");
    expect(window.location.hash).toBe("#filters");
    expect(window.history.state).toEqual({ preserved: true });
  });

  it("restores filters on popstate and keeps Reset filters focused after an empty result", async () => {
    render(<PapersIndex papers={papers} />);
    await screen.findByLabelText("Keyword");
    fireEvent.click(screen.getByRole("button", { name: "NBA" }));
    fireEvent.change(screen.getByLabelText("Keyword"), { target: { value: "pitch mix" } });
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("0 of 2 papers"));
    const reset = screen.getByRole("button", { name: "Reset filters" });
    reset.focus();
    fireEvent.click(reset);
    expect(reset).toHaveFocus();
    expect(screen.getByRole("status")).toHaveTextContent("2 of 2 papers");

    window.history.replaceState(null, "", "/analytics/papers/?sport=mlb&keyword=pitch%20mix");
    fireEvent(window, new PopStateEvent("popstate"));
    await waitFor(() => expect(screen.getByRole("button", { name: "MLB" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByLabelText("Keyword")).toHaveValue("pitch mix");
  });

  it("shows the published-empty state without filter controls", () => {
    render(<PapersIndex papers={[]} />);
    expect(screen.getByText(/No papers are published yet/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Keyword")).not.toBeInTheDocument();
  });
});

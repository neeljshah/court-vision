import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/analytics/scoutCorpus.server", () => ({
  loadScoutCorpus: () => [
    { q: "NBA question", alt_phrasings: [], tags: [" NBA "], bucket: "test", a: { status: "ok", answer: "Published.", source_artifact: "public.json" } },
    { q: "MLB question", alt_phrasings: [], tags: ["mlb"], bucket: "test", a: { status: "ok", answer: "Published.", source_artifact: "public.json" } },
  ],
}));

import AskPage from "./page";

describe("AskPage", () => {
  it("derives the displayed sports count from normalized entry tags", () => {
    render(<AskPage />);

    expect(screen.getByLabelText("Search coverage")).toHaveTextContent("2 sports");
    expect(screen.queryByText(/nine typed MCP tools/i)).not.toBeInTheDocument();
    expect(screen.getByText(/documents a set of typed MCP tools/i)).toBeInTheDocument();
  });
});

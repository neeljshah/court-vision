import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/analytics/stateContrasts.server", () => ({ loadStateContrasts: () => [] }));

import StateContrastsPage from "./page";

describe("StateContrastsPage", () => {
  it("keeps its reading shell when the published snapshot is unavailable", () => {
    render(<StateContrastsPage />);

    expect(screen.getByRole("heading", { level: 1, name: "Compare published state buckets." })).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Reading trail" })).getByText(/Read first:/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse published modules" })).toHaveAttribute("href", expect.stringMatching(/\/analytics\/browse\/?$/));
  });
});

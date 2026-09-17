import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/showcase.server", () => ({ loadArtifact: () => null }));

import ObservationDependencePage from "./page";

describe("ObservationDependencePage", () => {
  it("keeps its reading shell when the published snapshot is unavailable", () => {
    render(<ObservationDependencePage />);

    expect(screen.getByRole("heading", { level: 1, name: "Repeated ticks are not repeated evidence." })).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Reading trail" })).getByText(/Next question:/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse published modules" })).toHaveAttribute("href", expect.stringMatching(/\/analytics\/browse\/?$/));
  });
});

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/analytics/blowoutTiming.server", () => ({ loadBlowoutTiming: () => [] }));

import BlowoutTimingPage from "./page";

describe("BlowoutTimingPage", () => {
  it("keeps its reading shell when the published snapshot is unavailable", () => {
    render(<BlowoutTimingPage />);

    expect(screen.getByRole("heading", { level: 1, name: "Lasting leads by threshold." })).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Reading trail" })).getByText(/Read first:/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse published modules" })).toHaveAttribute("href", expect.stringMatching(/\/analytics\/browse\/?$/));
  });
});

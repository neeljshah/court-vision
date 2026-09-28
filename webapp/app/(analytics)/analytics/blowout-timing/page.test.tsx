import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildBlowoutTiming } from "@/lib/analytics/blowoutTiming";
import { loadBlowoutTiming } from "@/lib/analytics/blowoutTiming.server";
import published from "@/public/data/showcase/blowout_dynamics.json";

vi.mock("@/lib/analytics/blowoutTiming.server", () => ({ loadBlowoutTiming: vi.fn(() => []) }));

import BlowoutTimingPage from "./page";

describe("BlowoutTimingPage", () => {
  beforeEach(() => vi.mocked(loadBlowoutTiming).mockReturnValue([]));
  it("keeps its reading shell when the published snapshot is unavailable", () => {
    render(<BlowoutTimingPage />);

    expect(screen.getByRole("heading", { level: 1, name: "Lasting leads by threshold." })).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Reading trail" })).getByText(/Read first:/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse published modules" })).toHaveAttribute("href", expect.stringMatching(/\/analytics\/browse\/?$/));
  });

  it("passes the same source date to the page receipt and both sport captions", () => {
    vi.mocked(loadBlowoutTiming).mockReturnValue(buildBlowoutTiming(published));
    render(<BlowoutTimingPage />);
    const receipt = screen.getByRole("button", { name: "Receipt: descriptive_only for Source as of 2026-09-17" });
    expect(receipt).toHaveTextContent("Source as of 2026-09-17");
    expect(screen.getAllByText("Source as of 2026-09-17")).toHaveLength(3);
  });
});

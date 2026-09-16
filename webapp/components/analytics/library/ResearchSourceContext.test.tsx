import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { observationPeriod, ResearchSourceContext } from "./ResearchSourceContext";

afterEach(() => vi.unstubAllGlobals());

describe("ResearchSourceContext", () => {
  it("keeps mixed source windows distinct beside their snapshot dates", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve({ ok: true, json: async () => url.includes("nba_q4_shift")
      ? { observation_window: { seasons: "2024-25, 2025-26 present in this cache" } }
      : { seasons: { "2024_25": {}, "2025_26": {} } } })));
    render(<ResearchSourceContext fields={[
      { key: "shift", label: "Q4 shift", unit: "number", sourceId: "nba_q4_shift" },
      { key: "delta", label: "Net rating delta", unit: "number", sourceId: "on_off_showcase" },
    ]} sources={[
      { id: "nba_q4_shift", asOf: "2026-07-24", fields: ["shift"] },
      { id: "on_off_showcase", asOf: "not recorded", fields: ["delta"] },
    ]} />);
    const context = screen.getByLabelText("Source context");
    await waitFor(() => expect(within(context).getByText("Observation period: 2024-25, 2025-26 present in this cache")).toBeInTheDocument());
    expect(within(context).getByText("Observation period: 2024-25, 2025-26")).toBeInTheDocument();
    expect(within(context).getByText("Snapshot date: 2026-07-24")).toBeInTheDocument();
    expect(within(context).getByText("Feeds: Q4 shift")).toBeInTheDocument();
  });

  it("reports an unrecorded period when the published module has no window", () => {
    expect(observationPeriod({ label: "No window" })).toBeNull();
  });
});

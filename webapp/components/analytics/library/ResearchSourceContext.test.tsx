import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { observationPeriod, ResearchSourceContext } from "./ResearchSourceContext";

afterEach(() => vi.unstubAllGlobals());

describe("ResearchSourceContext", () => {
  it("keeps row windows distinct from source coverage beside their snapshot dates", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve({ ok: true, json: async () => url.includes("nba_q4_shift")
      ? { observation_window: { seasons: "2024-25, 2025-26 present in this cache" } }
      : { seasons: { "2024_25": {}, "2025_26": {} } } })));
    render(<ResearchSourceContext fields={[
      { key: "shift", label: "Q4 shift", unit: "number", sourceId: "nba_q4_shift" },
      { key: "delta", label: "Net rating delta", unit: "number", sourceId: "on_off_showcase" },
    ]} sources={[
      { id: "nba_q4_shift", asOf: "2026-07-24", fields: ["shift"], rowWindows: { shift: ["2025-26"] } },
      { id: "on_off_showcase", asOf: "not recorded", fields: ["delta"], rowWindows: { delta: ["2025-26"] } },
    ]} />);
    const context = screen.getByLabelText("Source context");
    await waitFor(() => expect(within(context).getByText("Source coverage: 2024-25, 2025-26 present in this cache")).toBeInTheDocument());
    expect(within(context).getByText("Source coverage: 2024-25, 2025-26")).toBeInTheDocument();
    expect(within(context).getByText("Row window: Q4 shift: 2025-26")).toBeInTheDocument();
    expect(within(context).getByText("Row window: Net rating delta: 2025-26")).toBeInTheDocument();
    expect(within(context).getByText("Snapshot date: 2026-07-24")).toBeInTheDocument();
    expect(within(context).getByText("Feeds: Q4 shift")).toBeInTheDocument();
    expect(within(context).getByRole("link", { name: "nba_q4_shift" })).toHaveAttribute("href", "/analytics/m/nba_q4_shift");
    expect(within(context).getByRole("link", { name: "on_off_showcase" })).toHaveAttribute("href", "/analytics/m/on_off_showcase");
  });

  it("reports an unrecorded period when the published module has no window", () => {
    expect(observationPeriod({ label: "No window" })).toBeNull();
  });

it("uses real atlas pack and module routes", () => {
  expect(sourceHref("atlas_nba_teams_manifest")).toBe("/analytics/players#nba_teams");
  expect(sourceHref("ctx_team_states")).toBe("/analytics/m/ctx_team_states");
});

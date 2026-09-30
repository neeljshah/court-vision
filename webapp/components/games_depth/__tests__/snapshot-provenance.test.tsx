import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import served from "@/public/demo-data/api_ingame_mlb_401816143.json";
import full from "@/public/demo-data/api_ingame_mlb_401816143_full.json";
import boxscore from "@/public/demo-data/api_boxscore_mlb_401816143.json";
import mlbReport from "@/public/demo-data/api_report_mlb_401816143.json";
import soccer from "@/public/demo-data/api_predict_soccer.json";
import type { Report } from "@/lib/api";

vi.mock("@/lib/fetchHonest", () => ({ isSnapshotMode: true }));
vi.mock("@/lib/api", () => ({
  api: { getPredict: () => Promise.resolve(soccer) },
  isUnavailable: (value: { status?: string }) => value.status === "unavailable",
}));
vi.mock("@/lib/useLiveData", () => ({
  useLiveData: (_fetcher: unknown, options: { cacheKey: string }) => ({
    data: options.cacheKey.endsWith(":boxscore") ? boxscore : served,
    ageSec: 2, isStale: false, isLoading: false, error: null,
  }),
  useLiveDataUrl: () => ({
    data: full, ageSec: 2, isStale: false, isLoading: false, error: null,
  }),
}));

import { InGameNumber } from "@/app/(terminal)/games/[sport]/[gameId]/InGameNumber";
import { BoxScorePanel } from "@/components/p6/BoxScorePanel";
import { GameReport } from "@/components/p6/GameReport";
import { LiveInGamePanel } from "@/components/live/LiveInGamePanel";
import { LiveExample } from "@/components/explain/LiveExample";

describe("Published snapshot provenance", () => {
  it("does not present recent retrieval as fresh live game data", () => {
    const props = { sport: "mlb", gameId: "401816143" };
    const { container } = render(<>
      <InGameNumber {...props} />
      <BoxScorePanel {...props} />
      <LiveInGamePanel {...props} matchupLabel="NYM @ PHI" pregameProb={0.6433} />
      <GameReport report={mlbReport as unknown as Report} />
    </>);
    expect(screen.getByText("snapshot P(home win)")).toBeInTheDocument();
    expect(screen.getByText("In-game (snapshot)")).toBeInTheDocument();
    expect(screen.getAllByText(/published snapshot/i)).toHaveLength(3);
    expect(container.textContent).not.toMatch(/updated 2s ago|live P\(home win\)/i);
    expect(container.textContent).not.toContain(new Date(Date.now() - 2000).toLocaleTimeString());
    expect(screen.getByTestId("ingame-pwin")).toHaveTextContent("64.3%");
  });

  it("shows the actual home_ml forecast separately from published market references", async () => {
    render(<LiveExample />);
    expect(await screen.findByText("Arsenal vs Coventry City")).toBeInTheDocument();
    expect(screen.getByText("a published example")).toBeInTheDocument();
    expect(screen.getByText(`Published snapshot: ${soccer.generated_at}`)).toBeInTheDocument();
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "60");
    expect(screen.getByRole("columnheader", { name: /market prob/i })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: /model prob/i })).toBeNull();
    expect(screen.getAllByText(/espn:DraftKings \| proxy reference/)).toHaveLength(2);
  });
});

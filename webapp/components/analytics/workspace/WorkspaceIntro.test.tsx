import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { WorkspaceIntro } from "./WorkspaceIntro";

const example = { bin_lo: 0.5, bin_hi: 0.6, mean_p: 0.5436, mean_y: 0.4619, n: 17652, n_games: 186, mean_y_ci: [0.3685, 0.5575] as [number, number], gap: -0.0818, gap_ci: [-0.1736, 0.0137] as [number, number], ci_pct: [2.5, 97.5] as [number, number], cluster_unit: "game_id", n_boot: 1000, artifact_date: "2026-07-23", integrity_status: "regenerated" as const };

describe("WorkspaceIntro", () => {
  it("renders the published calibration sentence and its reading sequence", () => {
    render(<WorkspaceIntro example={example} />);
    const calibration = screen.getByRole("region", { name: "Published MLB calibration example" });
    expect(within(calibration).getByText(/These MLB\/soccer numbers are revision 2, computed on the segment-clean corpus/)).toBeInTheDocument();
    expect(within(calibration).getByRole("link", { name: "Read the finding." })).toHaveAttribute("href", expect.stringMatching(/^\/analytics\/findings\/ingame-join-integrity\/?$/));
    expect(within(calibration).getByText((_, node) => node?.textContent === "For MLB, model forecasts of 50% to 60%, the mean forecast was 54.36% and the observed frequency was 46.19%, from 17,652 observations across 186 games. Snapshot date: 2026-07-23.")).toBeInTheDocument();
    expect((calibration.textContent || "").replace(/\s+/g, " ")).toContain("Observed-frequency interval: 36.85% to 55.75% (95.00% game-cluster bootstrap interval; 2.5% to 97.5% percentiles; 1,000 resamples)");
    expect(within(calibration).getByText(/includes zero, and does not establish agreement/i)).toBeInTheDocument();
    expect(within(calibration).getByRole("link", { name: /inspect this exact calibration bin/i })).toHaveAttribute("href", "/analytics/calibration?sport=mlb&series=model&bin_lo=0.5&bin_hi=0.6");

    const sequence = screen.getByRole("navigation", { name: "Read calibration sequence" });
    expect(within(sequence).getByRole("link", { name: "Reliability" })).toHaveAttribute("href", expect.stringContaining("/analytics/calibration/"));
    expect(within(sequence).getByRole("link", { name: /repeated observations/i })).toHaveAttribute("href", expect.stringContaining("/analytics/observation-dependence/"));
    expect(within(sequence).getByRole("link", { name: /state reliability/i })).toHaveAttribute("href", expect.stringContaining("/analytics/state-reliability/"));
  });
});

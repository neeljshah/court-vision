import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { WorkspaceIntro } from "./WorkspaceIntro";

const example = { mean_p: 0.5436, mean_y: 0.4619, n: 17652, n_games: 186, mean_y_ci: [0.3685, 0.5575] as [number, number], artifact_date: "2026-07-23" };

describe("WorkspaceIntro", () => {
  it("renders the published calibration sentence and its reading sequence", () => {
    render(<WorkspaceIntro example={example} />);
    const calibration = screen.getByRole("region", { name: "Published MLB calibration example" });
    expect(within(calibration).getByText((_, node) => node?.textContent === "In the published MLB model bin, the mean forecast was 54.36% and the observed frequency was 46.19%, from 17,652 observations across 186 games on 2026-07-23.")).toBeInTheDocument();
    expect(within(calibration).getByText("Observed frequency interval: 36.85% to 55.75%.")).toBeInTheDocument();

    const sequence = screen.getByRole("navigation", { name: "Read calibration sequence" });
    expect(within(sequence).getByRole("link", { name: "Reliability" })).toHaveAttribute("href", expect.stringContaining("/analytics/calibration/"));
    expect(within(sequence).getByRole("link", { name: /repeated observations/i })).toHaveAttribute("href", expect.stringContaining("/analytics/observation-dependence/"));
    expect(within(sequence).getByRole("link", { name: /state reliability/i })).toHaveAttribute("href", expect.stringContaining("/analytics/state-reliability/"));
  });
});

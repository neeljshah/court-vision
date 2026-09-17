import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ForecasterReport } from "./ForecasterReport";
import type { ForecasterArms } from "./forecaster.server";

const currentArmLiterals = [
  { sport: "NBA", static_brier: 0.209, score_only_brier: 0.172, combined_brier: 0.159, mechanical_share: "~73%", model_prior_share: "-0.014 (~27%)" },
  { sport: "MLB", static_brier: 0.241, score_only_brier: 0.128, combined_brier: 0.126, mechanical_share: "~99%", model_prior_share: "-0.001 (~1%)" },
];

function artifact(): ForecasterArms {
  const path = join(process.cwd(), "public", "data", "forecaster", "forecaster-arms.json");
  return JSON.parse(readFileSync(path, "utf8")) as ForecasterArms;
}

describe("ForecasterPage", () => {
  it("reproduces the current three-arm literals from the public artifact", () => {
    expect(artifact().arms.map(({ sport, static_brier, score_only_brier, combined_brier, mechanical_share, model_prior_share }) => ({ sport, static_brier, score_only_brier, combined_brier, mechanical_share, model_prior_share }))).toEqual(currentArmLiterals);
  });

  it("uses public receipts and renders each published arm value", () => {
    const data = artifact();
    render(<ForecasterReport data={data} />);

    screen.getAllByRole("link", { name: /receipt/i }).forEach(link => {
      expect(link.getAttribute("href")).toMatch(/^\/data\/forecaster\/forecaster-arms\.json#\/arms\/\d+$/);
    });
    data.arms.forEach(arm => {
      [arm.static_brier, arm.score_only_brier, arm.combined_brier].forEach(value => {
        expect(screen.getAllByText(value!.toFixed(3)).length).toBeGreaterThan(0);
      });
    });
  });

  it("links the reading trail to exported page routes", () => {
    render(<ForecasterReport data={artifact()} />);
    const trail = screen.getByRole("region", { name: "Reading trail" });
    expect(within(trail).getByRole("link", { name: "Calibration reliability" }).getAttribute("href")).toMatch(/^\/analytics\/calibration\/?$/);
    expect(within(trail).getByRole("link", { name: "State reliability" }).getAttribute("href")).toMatch(/^\/analytics\/state-reliability\/?$/);
  });

  it("renders not published when a fixture omits a measurement", () => {
    const data = artifact();
    render(<ForecasterReport data={{ ...data, arms: [{ ...data.arms[0], combined_brier: null }] }} />);
    expect(screen.getAllByText("not published").length).toBeGreaterThan(0);
  });
});

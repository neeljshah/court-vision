// Chart/artifact parity: the served PNG must not predate the artifact it draws.
//
// The failure this guards: an artifact gets regenerated (revision 2) while its
// docs/img PNG stays at revision 1, so the module page and the paper figures
// print numbers the JSON no longer holds. The PNGs are matplotlib output and
// carry NO embedded date (only a "Software: Matplotlib ..." tEXt chunk), so
// there is no in-file provenance to compare -- this test asserts file presence
// in the served directory plus file mtime >= the module's published as_of date
// instead. Regenerate a stale chart with
//   python -m scripts.platformkit.analytics_showcase.replot_from_json <id> --stage
import { existsSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { snapshot } from "./labHelpers";
import { getPublishedChartPresentation } from "./publishedChartPresentation";

type ManifestModule = { id: string; chart_path?: string | null; as_of?: string | null };

const served = (chartPath: string) => join(process.cwd(), "public/img/showcase", chartPath.split(/[\\/]/).pop() || "");
const day = (value: string | null | undefined) => (value || "").slice(0, 10);
const mtimeDay = (path: string) => new Date(statSync(path).mtimeMs).toISOString().slice(0, 10);

describe("published chart / artifact parity", () => {
  const modules = snapshot<{ modules: ManifestModule[] }>("site_manifest").modules;
  const charted = modules.filter(entry => !!entry.chart_path);

  it("serves a PNG for every module the manifest gives a chart_path", () => {
    expect(charted.length).toBeGreaterThan(50);
    const missing = charted.filter(entry => !existsSync(served(entry.chart_path!)));
    expect(missing.map(entry => entry.id)).toEqual([]);
  });

  it("never serves a chart image older than its artifact's as_of", () => {
    const stale = charted
      .map(entry => ({ id: entry.id, asOf: day(entry.as_of), png: mtimeDay(served(entry.chart_path!)) }))
      .filter(row => row.asOf && row.png < row.asOf);
    expect(stale).toEqual([]);
  });

  it("keeps the regenerated revision-2 artifacts charted and approved", () => {
    const regenerated = ["brier_skill_scores", "calibration_by_market_type", "calibration_over_time", "calibration_stability",
      "info_arrival_curve", "market_disagreement_profile", "market_overreaction", "residual_anatomy",
      "residual_autocorrelation", "soccer_calibration_pack", "blowout_dynamics", "comeback_atlas", "kernel_transfer",
      "market_convergence", "novel_live_clock_fraction", "novel_market_foresight_premium", "why_attribution"];
    regenerated.forEach(id => {
      const entry = modules.find(module => module.id === id);
      expect(entry?.chart_path, id).toBeTruthy();
      expect(existsSync(served(entry!.chart_path!)), id).toBe(true);
      expect(getPublishedChartPresentation(id).approved, id).toBe(true);
    });
  });
});

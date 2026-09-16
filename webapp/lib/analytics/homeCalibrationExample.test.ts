import { describe, expect, it } from "vitest";
import { buildHomeCalibrationExample } from "./homeCalibrationExample";

const bin = (meanP: number, n: number) => ({ bin_lo: meanP < 0.5 ? 0.4 : 0.5, bin_hi: meanP < 0.5 ? 0.5 : 0.6, mean_p: meanP, mean_y: 0.4619001, n, n_games: 186, mean_y_ci: [0.3685001, 0.5575001], gap: -0.0818001, gap_ci: [-0.1736001, 0.0137001] });

describe("buildHomeCalibrationExample", () => {
  it("selects the largest readable mid-probability MLB model bin and rounds display fields", () => {
    const example = buildHomeCalibrationExample({ as_of: "2026-07-23T03:21:27.493056+00:00", ci_pct: [2.5, 97.5], n_boot: 1000, cluster_unit: "game_id", sports: { mlb: { sides: { model_prob: { bins: [bin(0.4568, 14736), bin(0.5436001, 17652), bin(0.748, 99999)] } } } } });
    expect(example).toEqual({ bin_lo: 0.5, bin_hi: 0.6, mean_p: 0.5436, mean_y: 0.4619, n: 17652, n_games: 186, mean_y_ci: [0.3685, 0.5575], gap: -0.0818, gap_ci: [-0.1736, 0.0137], ci_pct: [2.5, 97.5], cluster_unit: "game_id", n_boot: 1000, artifact_date: "2026-07-23", integrity_status: "withdrawn-pending-regeneration" });
  });

  it("preserves a missing artifact date as null", () => {
    const example = buildHomeCalibrationExample({ ci_pct: [2.5, 97.5], n_boot: 1000, cluster_unit: "game_id", sports: { mlb: { sides: { model_prob: { bins: [bin(0.5, 1)] } } } } });
    expect(example?.artifact_date).toBeNull();
  });

  it("treats a placeholder artifact date as absent", () => {
    const example = buildHomeCalibrationExample({ as_of: "Published snapshot", ci_pct: [2.5, 97.5], n_boot: 1000, cluster_unit: "game_id", sports: { mlb: { sides: { model_prob: { bins: [bin(0.5, 1)] } } } } });
    expect(example?.artifact_date).toBeNull();
  });
});

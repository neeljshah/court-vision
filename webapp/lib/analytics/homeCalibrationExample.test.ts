import { describe, expect, it } from "vitest";
import { buildHomeCalibrationExample } from "./homeCalibrationExample";

const bin = (meanP: number, n: number) => ({ mean_p: meanP, mean_y: 0.4619001, n, n_games: 186, mean_y_ci: [0.3685001, 0.5575001] });

describe("buildHomeCalibrationExample", () => {
  it("selects the largest readable mid-probability MLB model bin and rounds display fields", () => {
    const example = buildHomeCalibrationExample({ as_of: "2026-07-23T03:21:27.493056+00:00", sports: { mlb: { sides: { model_prob: { bins: [bin(0.4568, 14736), bin(0.5436001, 17652), bin(0.748, 99999)] } } } } });
    expect(example).toEqual({ mean_p: 0.5436, mean_y: 0.4619, n: 17652, n_games: 186, mean_y_ci: [0.3685, 0.5575], artifact_date: "2026-07-23" });
  });

  it("preserves a missing artifact date as null", () => {
    const example = buildHomeCalibrationExample({ sports: { mlb: { sides: { model_prob: { bins: [bin(0.5, 1)] } } } } });
    expect(example?.artifact_date).toBeNull();
  });
});

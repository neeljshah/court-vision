import { describe, expect, it } from "vitest";
import { buildLineupProxyResearch } from "./researchLineupProxy";

const player = (player_name: string, delta_win_rate: number) => ({ team: "DEN", player_name, n_active: 20, n_missed: 5, win_rate_active: 0.7, win_rate_missed: 0.4, delta_win_rate, ci95_offset: [-0.15, 0.15] });

describe("lineup proxy research", () => {
  it("builds active-versus-missed measurements and a Wald half-width", () => {
    const analysis = buildLineupProxyResearch({ players: [player("Nikola Jokic", 0.3)], floors: { min_active: 15, min_missed: 5 } })[0];
    expect(analysis).toMatchObject({ id: "lineup-proxy-active-missed-record", source: "ctx_lineup_proxy" });
    expect(analysis.rows[0].values).toMatchObject({ win_rate_difference: 0.3, wald_95_half_width: 0.15, games_active: 20, games_missed: 5 });
    expect(analysis.rows[0].sourcePaths).toContain("players[].ci95_offset[1]");
    expect(analysis.bindings?.every(binding => binding.valueKey in analysis.rows[0].values)).toBe(true);
    expect(analysis.caveat).toContain("This comparison does not isolate the player's causal contribution.");
  });

  it("orders players by active-minus-missed rate", () => {
    const rows = buildLineupProxyResearch({ players: [player("Beta", -0.1), player("Alpha", 0.2)] })[0].rows;
    expect(rows.map(row => row.label)).toEqual(["Alpha (DEN)", "Beta (DEN)"]);
  });

  it("returns no rows for malformed support or interval values", () => {
    expect(buildLineupProxyResearch({ players: [{ ...player("Nikola Jokic", 0.3), ci95_offset: [-0.1] }] })[0].rows).toEqual([]);
    expect(buildLineupProxyResearch({})[0].rows).toEqual([]);
  });
});

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { getBasketballDepthResearch } from "./researchBasketballDepth";

const source = (id: string) => JSON.parse(readFileSync(join(process.cwd(), "public/data/showcase", `${id}.json`), "utf8"));
const data = getBasketballDepthResearch();
const get = (id: string) => data.find(item => item.id === id)!;

describe("basketball depth research", () => {
  it("publishes five distinct analyses with source-backed row counts", () => {
    expect(data.map(item => item.id)).toEqual([
      "nba-venue-shooting-gap", "nba-venue-box-profile", "nba-player-venue-dispersion",
      "nba-pra-role-composition", "nba-context-ts-dominant-gap",
    ]);
    expect(data.map(item => item.rows.length)).toEqual([9, 15, 3, 30, 50]);
    expect(data.every(item => item.asOf === undefined)).toBe(true);
    expect(data.every(item => item.references.every(ref => ref.url.startsWith("https://www.nba.com/")))).toBe(true);
    expect(get("nba-venue-shooting-gap").rows.map(row => row.label).slice(0, 3)).toEqual(["Field goal", "Three-point", "Free throw"]);
    expect(get("nba-venue-shooting-gap").rows.every(row => !row.label.includes("_pct"))).toBe(true);
    expect(get("nba-venue-box-profile").rows.map(row => row.label)).toEqual([
      "Points", "Rebounds", "Offensive rebounds", "Defensive rebounds", "Assists", "Steals", "Blocks", "Turnovers",
      "Personal fouls", "Field-goal attempts", "Three-point attempts", "Free-throw attempts", "Field goals made",
      "Three-pointers made", "Free throws made",
    ]);
  });

  it("converts source percentage points to field fractions without changing operands", () => {
    const raw = source("home_away_anatomy").by_season["2023-24"].league_shooting_pct.fg_pct;
    const derived = get("nba-venue-shooting-gap").rows.find(row => row.id === "2023-24-fg_pct")!;
    expect(derived.values.home_pct).toBe(raw.home_pct / 100);
    expect(derived.values.away_pct).toBe(raw.away_pct / 100);
    expect(derived.values.gap).toBeCloseTo(derived.values.home_pct! - derived.values.away_pct!, 10);
    expect(derived.values.home_rows).toBe(source("home_away_anatomy").by_season["2023-24"].coverage.n_home);
  });

  it("recomputes dispersion and PRA shares independently", () => {
    const rawVenue = source("home_away_anatomy").by_season["2024-25"].player_distribution;
    const dispersion = get("nba-player-venue-dispersion").rows.find(row => row.label === "2024-25")!;
    expect(dispersion.values.middle_80_span).toBeCloseTo(rawVenue.p90_delta - rawVenue.p10_delta, 12);
    expect(dispersion.values.players).toBe(rawVenue.n_players);

    const rawPlayer = source("box_value_index").top_30[0];
    const role = get("nba-pra-role-composition").rows[0];
    const pra = rawPlayer.pts_per36 + rawPlayer.reb_per36 + rawPlayer.ast_per36;
    expect(role.values.pra_per36).toBeCloseTo(pra, 12);
    expect(role.values.scoring_share! + role.values.rebound_share! + role.values.assist_share!).toBeCloseTo(1, 12);
  });

  it("retains context direction, cell support, and finite-or-missing contracts", () => {
    const raw = source("ctx_player_splits").players[0];
    const derived = get("nba-context-ts-dominant-gap").rows[0];
    const gaps = [raw.splits.opp_def_tier.delta_ts_pct, raw.splits.home_away.delta_ts_pct, raw.splits.rest.delta_ts_pct];
    expect(derived.values.defense_gap).toBe(gaps[0]);
    expect(derived.values.largest_abs_gap).toBe(Math.max(...gaps.map(Math.abs)));
    expect(derived.values.rest_min_n).toBe(Math.min(raw.splits.rest.b2b.n, raw.splits.rest.rest2plus.n));
    for (const item of data) {
      expect(item.rows.every(row => Object.values(row.values).every(value => value === null || Number.isFinite(value)))).toBe(true);
      expect(item.rows.every(row => row.note && row.note.length > 20)).toBe(true);
    }
    expect(data.some(item => item.source === "clutch_context")).toBe(false);
  });
});

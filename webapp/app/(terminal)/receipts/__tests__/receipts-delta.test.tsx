import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import board from "@/public/data/showcase/cross_sport_scoreboard.json";
import receipts from "@/public/receipts.json";
import { modelMinusMarket } from "@/lib/scoreboardDelta";
import { FIGURES } from "@/lib/figures";
import ReceiptsPage from "../page";
import { CELL_FLOOR, DELTA_HEADER, modelMinusMarketCell, underFloor } from "../ledger";

const fmt = (v: number) => (v >= 0 ? "+" : "") + v.toFixed(4);

describe("/receipts/ delta column", () => {
  it("prints model minus market under the stated header", () => {
    const { container } = render(<ReceiptsPage />);
    expect(container.textContent).toContain(DELTA_HEADER);
    expect(DELTA_HEADER).toBe("model minus market (95% CI); positive = model worse");
  });

  it("the nba end_q1 row equals the home scoreboard value", () => {
    const i = receipts.rows.findIndex((r) => r.sport_market === "nba" && r.checkpoint === "end_q1");
    const home = board.rows.find((r) => r.sport === "nba" && r.checkpoint === "end_q1")!;
    const d = modelMinusMarket(home.paired_delta_mean, home.paired_delta_95ci as [number, number])!;
    const want = `${fmt(d.delta)} [${fmt(d.ci[0])}, ${fmt(d.ci[1])}]`;
    expect(modelMinusMarketCell(receipts.rows[i].delta_ci)).toBe(want);
    const { container } = render(<ReceiptsPage />);
    expect(container.querySelectorAll('[data-role="delta"]')[i].textContent).toBe(want);
    expect(want.startsWith("+")).toBe(true); // model Brier 0.2006 above market 0.1922: model worse
  });

  it("MODEL_SHARPER under the canonical cell floor is neutral with the UNDERPOWERED qualifier", () => {
    expect(CELL_FLOOR).toBe(FIGURES.forward_cell_floor_games.value);
    expect(underFloor("MODEL_SHARPER_PROVISIONAL", CELL_FLOOR - 1)).toBe(true);
    expect(underFloor("MODEL_SHARPER_PROVISIONAL", CELL_FLOOR)).toBe(false);
    expect(underFloor("UNDERPOWERED", 5)).toBe(false);
    expect(modelMinusMarketCell("n/a")).toBe("n/a");
  });
});

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { buildMovementEvidence } from "@/lib/analytics/movementEvidence";
import { MovementEvidence } from "./MovementEvidence";

const evidence = buildMovementEvidence({ buckets: { soccer_intl: { "6-10pt": { n: 21, moved_to_price: 0.3495, outcome_rate: 0.7143, moved_to_minus_outcome: -0.3648 } } } }, {
  sports: {
    nba: { status: "ok", observation_window: { start: "2026-06-18", end: "2026-07-17", days: 30, files: 30 }, interval_minutes: { median: 1.117, p90: 1.183, mean: 1.866 }, n_pregame_snapshots: 183478, n_move_pairs: 182054, n_series_used: 160, total_abs_move: 23.28469, final_hour_movement_share: 0.3247, move_by_bucket: { "0-1h": { mean_abs_move: 0.00117 } } },
    kbo: { status: "insufficient_data", observation_window: { start: "2026-07-04", end: "2026-07-17", days: 13, files: 13 }, n_pregame_snapshots: 0, n_move_pairs: 0, n_series_used: 0 },
  },
});

describe("MovementEvidence", () => {
  it("renders both overreaction operands and qualifies the n=21 soccer bucket", () => {
    render(<MovementEvidence kind="market_overreaction" evidence={evidence.overreaction} />);
    const table = screen.getByRole("region", { name: "Market overreaction operands table" });
    expect(within(table).getByText("34.95%")).toBeInTheDocument();
    expect(within(table).getByText("71.43%")).toBeInTheDocument();
    expect(screen.getByText(/International soccer.*n=21/i)).toBeInTheDocument();
  });

  it("renders sport-specific absorption coverage and keeps unavailable rows visible", () => {
    render(<MovementEvidence kind="micro_absorption" evidence={evidence.absorption} />);
    const table = screen.getByRole("region", { name: "Micro absorption operands table" });
    expect(within(table).getByText("2026-06-18 to 2026-07-17 (30 days; 30 files)")).toBeInTheDocument();
    expect(within(table).getByText("32.47%")).toBeInTheDocument();
    expect(within(table).getByText("Unavailable")).toBeInTheDocument();
    expect(screen.getByText(/Independent-game counts are not published/)).toBeInTheDocument();
  });
});

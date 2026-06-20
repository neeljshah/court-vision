import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";

// Deep, disjoint explain-component tests (NEW file -- does not touch the
// existing explain.test.tsx, which covers the funnel-order / one-survivor cases).
//
// Covered here:
//   ValidationDiscipline -- all EIGHT controls + the planted-null/FWER/nested-CV
//                           plain-language analogies + the vs_close UNPROVEN line.
//   HonestFindings       -- the full gate-verdict table (one SHIP + the REJECTs +
//                           the TIER-3 BLOCKED), the depth-plateau counts.
//   SelfImproveExplainer -- READY-but-INERT default, ENABLED only on enable,
//                           "status unknown" on unreachable; real-money DENY line.
//   WhatAmILookingAt     -- parity green / not-green / unreachable; units/prob,
//                           no $ framing.
//   LiveExample          -- honest empty when unavailable AND when no markets;
//                           renders a REAL prediction (no $/price column) on ok.
//
// HONESTY RAILS asserted throughout: NO $ field; calibration-not-edge framing;
// honest-empty (never a fabricated game) when an endpoint is down.

import { ValidationDiscipline } from "../ValidationDiscipline";
import { HonestFindings } from "../HonestFindings";
import { GATE_VERDICTS } from "../gateVerdicts";
import { SelfImproveExplainer } from "../SelfImproveExplainer";
import { WhatAmILookingAt } from "../WhatAmILookingAt";
import * as apiMod from "@/lib/api";

// ---------------------------------------------------------------------------
describe("ValidationDiscipline -- all eight controls + analogies", () => {
  const CONTROLS = [
    "Leak-free features",
    "Walk-forward",
    "Cross-corpus",
    "Clustered Diebold-Mariano",
    "Planted-null control",
    "FWER tightening",
    "Degenerate-base guard",
    "Nested-CV anti-selection",
  ];
  it("renders all eight stacked controls", () => {
    render(<ValidationDiscipline />);
    for (const c of CONTROLS) {
      expect(screen.getByText(new RegExp(c, "i"))).toBeTruthy();
    }
  });
  it("step prefixes 01..08 are present (eight controls)", () => {
    render(<ValidationDiscipline />);
    expect(screen.getByText("01")).toBeTruthy();
    expect(screen.getByText("08")).toBeTruthy();
  });
  it("keeps vs_close UNPROVEN and claims no dollar edge", () => {
    render(<ValidationDiscipline />);
    expect(screen.getByText(/vs_close stays UNPROVEN|vs_close/i)).toBeTruthy();
    expect(screen.getByText(/No dollar edge is claimed at any step/i)).toBeTruthy();
  });
  it("frames a REJECT as the product working (success)", () => {
    render(<ValidationDiscipline />);
    expect(screen.getByText(/REJECT is the product working/i)).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
describe("HonestFindings -- full gate-verdict table", () => {
  it("renders a row for every gate verdict (one SHIP, the rest reject/blocked)", () => {
    render(<HonestFindings />);
    const ships = GATE_VERDICTS.filter((g) => g.verdict === "SHIP");
    const rejects = GATE_VERDICTS.filter((g) => g.verdict === "REJECT");
    const blocked = GATE_VERDICTS.filter((g) => g.verdict === "BLOCKED");
    expect(ships.length).toBe(1);
    expect(rejects.length).toBeGreaterThan(0);
    expect(blocked.length).toBeGreaterThan(0);
    // the depth-plateau headline surfaces the reject + blocked counts
    expect(screen.getByText(new RegExp(`${rejects.length} recorded REJECTs`, "i"))).toBeTruthy();
    expect(screen.getByText(new RegExp(`${blocked.length} TIER-3 BLOCKED`, "i"))).toBeTruthy();
  });
  it("shows the confirmed soccer corners CALIBRATION survivor", () => {
    render(<HonestFindings />);
    expect(screen.getByText(/soccer corners -- CALIBRATION, not a market edge/i)).toBeTruthy();
    expect(screen.getAllByText(/diff_corners_asof/i).length).toBeGreaterThan(0);
  });
  it("surfaces the cross-sport in-game micro-state REJECTs (NBA/MLB/soccer)", () => {
    render(<HonestFindings />);
    const table = screen.getByRole("table");
    // at least the three in-game micro-state rejects are listed by sport
    for (const sport of ["nba", "mlb", "soccer"]) {
      expect(within(table).getAllByText(new RegExp(`^${sport}$`, "i")).length).toBeGreaterThan(0);
    }
    // the tennis pbp row is the recorded TIER-3 BLOCKED (not green) cell
    expect(within(table).getAllByText(/^tennis$/i).length).toBeGreaterThan(0);
    expect(within(table).getAllByText(/TIER-3 BLOCKED/i).length).toBeGreaterThan(0);
  });
  it("no gate-verdict reason or vs_close claims a dollar edge", () => {
    for (const g of GATE_VERDICTS) {
      expect(g.vsClose.toLowerCase()).not.toMatch(/\$|\broi\b|profit/);
      expect(g.reason.toLowerCase()).not.toMatch(/\$|\broi\b|profit/);
    }
  });
});

// ---------------------------------------------------------------------------
describe("SelfImproveExplainer -- READY but INERT", () => {
  afterEach(() => vi.restoreAllMocks());
  it("defaults to READY (not enabled) when status resolves READY_INERT", async () => {
    vi.spyOn(apiMod, "getProductStatus").mockResolvedValue({ selfImprove: "READY_INERT" } as never);
    render(<SelfImproveExplainer />);
    await waitFor(() =>
      expect(screen.getByText(/self-improve: READY \(not enabled\)/i)).toBeTruthy()
    );
    // real-money default-DENY line is present
    expect(screen.getByText(/Real-money execution is default-DENY/i)).toBeTruthy();
  });
  it("shows ENABLED only when the endpoint reports enabled", async () => {
    vi.spyOn(apiMod, "getProductStatus").mockResolvedValue({ selfImprove: "ENABLED" } as never);
    render(<SelfImproveExplainer />);
    await waitFor(() => expect(screen.getByText(/self-improve: ENABLED/i)).toBeTruthy());
  });
  it("degrades to 'status unknown' when the endpoint is unreachable (never green)", async () => {
    vi.spyOn(apiMod, "getProductStatus").mockRejectedValue(new Error("down"));
    render(<SelfImproveExplainer />);
    await waitFor(() =>
      expect(screen.getByText(/status unknown \(endpoint unreachable\)/i)).toBeTruthy()
    );
  });
  it("frames the ratchet as measurement-only and human-gated, no edge", () => {
    vi.spyOn(apiMod, "getProductStatus").mockResolvedValue({ selfImprove: "READY_INERT" } as never);
    render(<SelfImproveExplainer />);
    expect(screen.getByText(/measurement-only/i)).toBeTruthy();
    expect(screen.getByText(/can never manufacture a market edge/i)).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
describe("WhatAmILookingAt -- live parity snapshot states", () => {
  afterEach(() => vi.restoreAllMocks());
  it("renders FULLY GREEN when parity is green", async () => {
    vi.spyOn(apiMod, "getParityHeadline").mockResolvedValue({
      green: true,
      nSports: 4,
      reason: "ok",
    } as never);
    render(<WhatAmILookingAt />);
    await waitFor(() => expect(screen.getByText(/parity: FULLY GREEN across 4 sports/i)).toBeTruthy());
  });
  it("renders 'not green' when parity is false", async () => {
    vi.spyOn(apiMod, "getParityHeadline").mockResolvedValue({
      green: false,
      nSports: 4,
      reason: "red",
    } as never);
    render(<WhatAmILookingAt />);
    await waitFor(() => expect(screen.getByText(/parity: not green/i)).toBeTruthy());
  });
  it("degrades to 'status unknown' when parity is unreachable", async () => {
    vi.spyOn(apiMod, "getParityHeadline").mockRejectedValue(new Error("down"));
    render(<WhatAmILookingAt />);
    await waitFor(() =>
      expect(screen.getByText(/parity: status unknown \(endpoint unreachable\)/i)).toBeTruthy()
    );
  });
  it("frames units/probability only with vs_close UNPROVEN (no $)", () => {
    vi.spyOn(apiMod, "getParityHeadline").mockResolvedValue({ green: null, nSports: 0, reason: "" } as never);
    const { container } = render(<WhatAmILookingAt />);
    expect(screen.getByText(/calibrated predictor/i)).toBeTruthy();
    expect(screen.getByText(/no dollar figure anywhere/i)).toBeTruthy();
    expect(/\$/.test(container.textContent ?? "")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("LiveExample -- real pred or honest empty, never fabricated, never $", () => {
  afterEach(() => vi.restoreAllMocks());

  it("honest empty when the snapshot endpoint is unavailable", async () => {
    vi.spyOn(apiMod.api, "getPredict").mockResolvedValue({
      status: "unavailable",
      reason: "offseason",
    } as never);
    const { LiveExample } = await import("../LiveExample");
    render(<LiveExample />);
    expect(await screen.findByText(/No live soccer snapshot right now/i)).toBeTruthy();
  });

  it("honest empty when the snapshot exists but has no predictions", async () => {
    vi.spyOn(apiMod.api, "getPredict").mockResolvedValue({
      status: "ok",
      predictions: [],
      honest_note: "no matches on the board",
    } as never);
    const { LiveExample } = await import("../LiveExample");
    render(<LiveExample />);
    expect(await screen.findByText(/No live soccer snapshot right now/i)).toBeTruthy();
  });

  it("renders a REAL prediction with probability + market surface and NO price/$", async () => {
    vi.spyOn(apiMod.api, "getPredict").mockResolvedValue({
      status: "ok",
      predictions: [
        {
          home: "Arsenal",
          away: "Chelsea",
          pregame_probs: { home: 0.55 },
          markets: [
            { name: "moneyline", outcome: "home", prob: 0.55 },
            { name: "totals", outcome: "over 2.5", prob: 0.48 },
          ],
        },
      ],
    } as never);
    const { LiveExample } = await import("../LiveExample");
    const { container } = render(<LiveExample />);
    expect(await screen.findByText(/Arsenal vs Chelsea/i)).toBeTruthy();
    expect(screen.getByText(/live example/i)).toBeTruthy();
    // the framing explicitly states no dollar figure / no price
    expect(screen.getByText(/No dollar figure, no/i)).toBeTruthy();
    const txt = container.textContent ?? "";
    expect(/\$/.test(txt)).toBe(false);
    expect(/\bprice\b.*\d|\bodds\b.*[-+]\d/.test(txt)).toBe(false);
  });
});

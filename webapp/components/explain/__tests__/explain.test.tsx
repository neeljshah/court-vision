import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { FunnelDetail } from "../FunnelDetail";
import { ValidationDiscipline } from "../ValidationDiscipline";
import { HonestFindings } from "../HonestFindings";
import { GATE_VERDICTS, SURVIVOR, countByVerdict } from "../gateVerdicts";

// ---------------------------------------------------------------------------
// How-it-works (explain) honesty-rail tests:
//   * the funnel renders all six stages in order
//   * the validation section frames REJECT as success
//   * the findings show EXACTLY one survivor and it is CALIBRATION not edge
//   * no explain component source emits a $/pnl/roi field (units/prob only)
//   * the survivor's vs_close is UNPROVEN, never an edge claim
// ---------------------------------------------------------------------------

describe("FunnelDetail -- all six stages, in order", () => {
  it("renders DATA through INTELLIGENCE", () => {
    render(<FunnelDetail />);
    for (const label of [
      "DATA",
      "SIGNALS",
      "MODELS",
      "ENGINES",
      "ONE PREDICTION",
      "INTELLIGENCE",
    ]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });
});

describe("ValidationDiscipline -- reject framed as success", () => {
  it("states an honest REJECT is the product working", () => {
    render(<ValidationDiscipline />);
    expect(screen.getByText(/why most signals honestly reject/i)).toBeTruthy();
    expect(screen.getByText(/nested-cv anti-selection/i)).toBeTruthy();
  });
});

describe("HonestFindings -- one CALIBRATION survivor, the rest reject", () => {
  it("the verdict snapshot has exactly one SHIP", () => {
    expect(countByVerdict("SHIP")).toBe(1);
    expect(SURVIVOR.sport).toBe("soccer");
  });

  it("the survivor's vs_close is UNPROVEN / CALIBRATION, never an edge", () => {
    expect(SURVIVOR.vsClose.toUpperCase()).toContain("UNPROVEN");
    expect(SURVIVOR.vsClose.toLowerCase()).toContain("calibration");
    for (const g of GATE_VERDICTS) {
      // no verdict line may claim a dollar edge
      expect(g.vsClose.toLowerCase()).not.toMatch(/\$|roi|profit/);
      expect(g.reason.toLowerCase()).not.toMatch(/\$|roi|profit/);
    }
  });

  it("renders the depth-plateau and survivor framing", () => {
    render(<HonestFindings />);
    expect(screen.getByText(/depth plateau/i)).toBeTruthy();
    expect(screen.getByText(/calibration, not a market edge/i)).toBeTruthy();
  });
});

describe("LiveExample -- honest empty, never a fabricated game", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders the honest empty state when no snapshot is available", async () => {
    const mod = await import("@/lib/api");
    vi.spyOn(mod.api, "getPredict").mockResolvedValue({
      status: "unavailable",
      reason: "no snapshot",
    } as never);
    const { LiveExample } = await import("../LiveExample");
    render(<LiveExample />);
    expect(
      await screen.findByText(/No live soccer snapshot right now/i)
    ).toBeTruthy();
  });
});

describe("HonestFindings -- survivor uses the SHIP badge with UNPROVEN framing", () => {
  it("renders the calibration-only / vs_close UNPROVEN framing for the SHIP", () => {
    render(<HonestFindings />);
    // SignalVerdictBadge always prints the SHIP note text.
    expect(screen.getAllByText(/calibration-only, vs_close UNPROVEN/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/diff_corners_asof/i).length).toBeGreaterThan(0);
  });
});

describe("no explain component emits a $/pnl/roi field", () => {
  it("source scan of components/explain is clean of money output", () => {
    const testDir = dirname(fileURLToPath(import.meta.url));
    const dir = join(testDir, "..");
    const files = readdirSync(dir).filter((f) => f.endsWith(".tsx") || f.endsWith(".ts"));
    const banned = /\bpnl\b|\bbankroll\b|\$\{?[a-zA-Z_]*?(pnl|roi|profit|dollars?)\b/i;
    const offenders: string[] = [];
    for (const f of files) {
      const src = readFileSync(join(dir, f), "utf8");
      if (banned.test(src)) offenders.push(f);
    }
    expect(offenders).toEqual([]);
  });
});

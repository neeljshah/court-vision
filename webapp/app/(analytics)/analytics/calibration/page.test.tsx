import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PACKET_VERDICTS, BANNED_COPY, RETRACTED_TOKENS } from "@/lib/packetVerdicts";
import { decompose } from "@/components/analytics/calibration/CalibrationDecomposition";
import CalibrationPage from "./page";

describe("/analytics/calibration/ (T2)", () => {
  it("renders the T2 blocks in order with a status line", () => {
    render(<CalibrationPage />);
    const h2 = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    const want = ["Verdict table", "Reliability diagrams with game-cluster intervals", "Brier decomposition", "Sharpness", "Coverage", "Inspectors", "Summary by market", "Limitations"];
    expect(h2.filter((t) => want.includes(t ?? ""))).toEqual(want);
    expect(screen.getByTestId("status-line")).toHaveTextContent(/TRAILS_CLOSE on \d+ of \d+ rows/);
  });

  it("every verdict-table row is a full metric block with a packet verdict", () => {
    const { container } = render(<CalibrationPage />);
    const rows = [...container.querySelectorAll("tr.metric")] as HTMLElement[];
    expect(rows.length).toBeGreaterThanOrEqual(3);
    const ns = rows.map((r) => Number(r.querySelector('[data-role="n"]')!.textContent!.replace(/,/g, "")));
    expect(ns).toEqual([...ns].sort((a, b) => b - a));
    for (const r of rows) {
      for (const role of ["verdict", "n", "interval", "asof", "receipt"]) expect(r.querySelector(`[data-role="${role}"]`)).not.toBeNull();
      expect(PACKET_VERDICTS as readonly string[]).toContain(r.querySelector('[data-role="verdict"]')!.textContent);
      expect(r.textContent).toContain("0.2500");
      expect(r.textContent).toMatch(/lower is better/);
    }
  });

  it("prints a Limitations block with at least three bullets and no banned copy", () => {
    const { container } = render(<CalibrationPage />);
    const limits = screen.getByRole("heading", { name: "Limitations" }).closest("section")!;
    expect(within(limits).getAllByRole("listitem").length).toBeGreaterThanOrEqual(3);
    const txt = container.textContent ?? "";
    expect(BANNED_COPY.test(txt)).toBe(false);
    for (const t of RETRACTED_TOKENS) expect(txt).not.toContain(t);
  });
});

describe("decompose (binned Murphy)", () => {
  it("reliability - resolution + uncertainty reproduces Brier for a perfectly binned forecast", () => {
    const bin = (p: number, y: number, n: number) => ({ binLo: 0, binHi: 1, meanP: p, meanY: y, meanYCi: [null, null] as const, gap: null, gapCi: [null, null] as const, n, nGames: 1, lowN: false });
    const d = decompose([bin(0.2, 0.25, 100), bin(0.8, 0.75, 100)])!;
    expect(d.reliability).toBeCloseTo(0.0025, 6);
    expect(d.uncertainty).toBeCloseTo(0.25, 6);
    expect(d.resolution).toBeCloseTo(0.0625, 6);
    expect(d.total).toBeCloseTo(0.19, 6);
    expect(decompose([])).toBeNull();
  });
});

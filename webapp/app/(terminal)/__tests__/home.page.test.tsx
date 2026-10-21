import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { PACKET_VERDICTS, BANNED_COPY, RETRACTED_TOKENS } from "@/lib/packetVerdicts";

// Home (/) -- the first-screen contract (DESIGN_PRINCIPLES P2.1-P2.4).

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

import Home from "../page";

const canon = JSON.parse(readFileSync(join(process.cwd(), "../docs/evidence/CANONICAL_FIGURES.json"), "utf-8"));

describe("Home (/) first screen", () => {
  it("states the one-sentence what-this-is", () => {
    render(<Home />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(
      /calibrated sports forecaster that publishes its own scorecard against the market/i);
  });

  it("leads with the verdict in plain words, then the scoring rule and reference as glossary terms", () => {
    render(<Home />);
    const verdict = screen.getByTestId("home-h2");
    expect(verdict.textContent).toMatch(/^\s*Pregame vs the devigged close:/);
    expect(verdict.textContent).not.toMatch(/within noise/i);
    expect(screen.getByRole("button", { name: "Brier score" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "devigged close" })).toBeTruthy();
    expect(verdict.nextElementSibling!.textContent).toMatch(/To check a number, open its receipt or the truth source/);
  });

  it("headline verdict rows come from CANONICAL_FIGURES, largest n first, each a full metric block", () => {
    const { container } = render(<Home />);
    const blocks = [...container.querySelectorAll("li.metric")] as HTMLElement[];
    expect(blocks.map((b) => b.dataset.key)).toEqual([
      "mlb_ml_pregame_vs_close", "soccer_ou25_pregame_vs_close", "nba_ml_pregame_vs_close_shin"]);
    for (const b of blocks) {
      const f = canon.figures.find((x: { key: string }) => x.key === b.dataset.key);
      for (const role of ["verdict", "n", "interval", "asof", "receipt"]) {
        expect(b.querySelector(`[data-role="${role}"]`), `${f.key} ${role}`).not.toBeNull();
      }
      expect(b.querySelector('[data-role="verdict"]')!.textContent).toBe(f.verdict);
      expect(b.textContent).toContain(f.model.toFixed(4));
      expect(b.textContent).toContain(f.as_of);
      expect(b.textContent).toMatch(/lower is better/);
    }
    // NBA: 0.1735 vs 0.1666 at n=372, MATCHES_CLOSE + UNDERPOWERED qualifier.
    expect(blocks[2].textContent).toMatch(/0\.1735 model vs 0\.1666 close/);
    expect(blocks[2].textContent).toMatch(/n = 372/);
    expect(blocks[2].querySelector('[data-role="qualifier"]')!.textContent).toBe("UNDERPOWERED");
  });

  it("every verdict slot in the first screen uses a packet word", () => {
    const { container } = render(<Home />);
    const first = container.querySelector("section")!;
    for (const el of first.querySelectorAll('[data-role="verdict"], [data-role="qualifier"]')) {
      expect(PACKET_VERDICTS as readonly string[]).toContain(el.textContent);
    }
  });

  it("shows the forward series status with a receipt, and the what-this-is-not block", () => {
    render(<Home />);
    const fwd = screen.getByTestId("forward-status");
    expect(fwd.textContent).toMatch(/run since 2026-10-06\. It has no calibration\s+verdict yet/);
    expect(within(fwd).getByRole("button", { name: /show receipt/ })).toBeTruthy();
    expect(screen.getByTestId("not-claimed").textContent).toMatch(/paper units only/);
  });

  it("has exactly two primary actions and a byline with contact", () => {
    render(<Home />);
    const evidence = screen.getByRole("link", { name: "Read the evidence" });
    const board = screen.getByRole("link", { name: "See today's board" });
    expect(evidence.getAttribute("href")).toBe("/evidence/");
    expect(board.getAttribute("href")).toBe("/games/");
    const primary = screen.getAllByRole("link").filter((a) => /\bbg-primary\b/.test(a.className));
    expect(primary).toHaveLength(2);
    expect(within(screen.getByTestId("byline")).getByRole("link", { name: /@/ }).getAttribute("href"))
      .toMatch(/^mailto:/);
    const byline = screen.getByTestId("byline").textContent ?? "";
    expect(screen.getByTestId("byline-roles").textContent).toBe(
      "Open to data-science / forecasting, quant-research, ML-engineering and analytics-engineering roles.");
    expect(byline.indexOf("roles.")).toBeLessThan(byline.indexOf("Education:"));
    expect(within(screen.getByTestId("byline")).queryByRole("link", { name: /resume/i })).toBeNull();
  });

  it("no banned copy or retracted figure outside the what-this-is-not block", () => {
    const { container } = render(<Home />);
    container.querySelector('[data-testid="not-claimed"]')!.remove();
    const txt = container.textContent ?? "";
    expect(BANNED_COPY.test(txt)).toBe(false);
    for (const t of RETRACTED_TOKENS) expect(txt).not.toContain(t);
  });
});

import { render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { PACKET_VERDICTS, BANNED_COPY, RETRACTED_TOKENS, VERDICT_QUALIFIER, type PacketVerdict } from "@/lib/packetVerdicts";
import { decompose } from "@/components/analytics/calibration/CalibrationDecomposition";
import { SPORT } from "@/components/analytics/calibration/CalibrationVerdictTable";
import CalibrationPage from "./page";

type Fig = { key: string; sport: string; market: string; metric: string; n?: number; n_unit?: string; model?: number; close?: number; verdict: string; ci95?: [number, number] };
const canon = JSON.parse(readFileSync(join(process.cwd(), "../docs/evidence/CANONICAL_FIGURES.json"), "utf-8")) as { figures: Fig[] };
const VERDICT_WORD = new RegExp(`\\b(${PACKET_VERDICTS.join("|")})\\b`);

/** Text of a subtree without the glossary tooltips Term mounts (their definitions are kit text, not page prose). */
function prose(el: Element, drop = ""): string {
  const copy = el.cloneNode(true) as HTMLElement;
  copy.querySelectorAll([".ev-term__tip", drop].filter(Boolean).join(", ")).forEach((n) => n.remove());
  return (copy.textContent ?? "").replace(/\s+/g, " ").trim();
}

// The home h2 mapping, re-derived from the JSON: sport, market, verdict, packet qualifier; repeats print once.
function clauses(rows: Fig[]): string {
  const out: string[] = [];
  for (const f of rows) {
    const q = VERDICT_QUALIFIER[f.verdict as PacketVerdict];
    const zero = f.ci95 != null && f.ci95[0] <= 0 && f.ci95[1] >= 0;
    const c = zero ? `${SPORT[f.sport] ?? f.sport} ${f.market} cannot tell (interval includes zero; underpowered)`
      : `${SPORT[f.sport] ?? f.sport} ${f.market} ${f.verdict}${q ? ` (${q})` : ""}`;
    if (!out.includes(c)) out.push(c);
  }
  return out.join("; ");
}

describe("/analytics/calibration/ (T2)", () => {
  it("renders the T2 blocks in order with a status line", () => {
    render(<CalibrationPage />);
    const h2 = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    const want = ["Verdict table", "Reliability diagrams with game-cluster intervals", "Brier decomposition", "Sharpness", "Coverage", "Inspectors", "Summary by market", "Limitations"];
    expect(h2.filter((t) => want.includes(t ?? ""))).toEqual(want);
    expect(screen.getByTestId("status-line")).toHaveTextContent(/TRAILS_CLOSE on \d+ of \d+ pregame rows, BEHIND on \d+ of \d+ in-play rows/);
  });

  it("the intro verdict sentence is computed from CANONICAL_FIGURES with the home h2 mapping", () => {
    render(<CalibrationPage />);
    const rows = canon.figures.filter((f) => f.metric === "Brier" && f.model != null && f.close != null).sort((a, b) => (b.n ?? 0) - (a.n ?? 0));
    const pregame = rows.filter((f) => f.n_unit !== "games");
    const inplay = rows.filter((f) => f.n_unit === "games");
    expect(pregame.length).toBeGreaterThan(0);
    expect(inplay.length).toBeGreaterThan(0);
    const want = `Verdict. Pregame vs the devigged close: ${clauses(pregame)}. In play: ${clauses(inplay)}. ` +
      "Every row below is scored by Brier score (lower is better) and shows its n, 95% interval, as-of date and receipt.";
    const intro = screen.getByTestId("calibration-intro");
    expect(prose(intro)).toBe(want);
    // every verdict word in the sentence is a VerdictLabel, one per distinct clause
    const labels = [...intro.querySelectorAll(".ev-verdict")].map((el) => el.getAttribute("data-verdict"));
    expect(labels).toEqual([...want.matchAll(new RegExp(VERDICT_WORD.source, "g"))].map((m) => m[1]));
  });

  it("no verdict word appears outside a VerdictLabel or the generated sentence", () => {
    const { container } = render(<CalibrationPage />);
    expect(prose(container)).toMatch(VERDICT_WORD); // the page does print verdicts
    expect(prose(container, ".ev-verdict, [data-testid='calibration-intro']")).not.toMatch(VERDICT_WORD);
    expect(prose(screen.getByTestId("calibration-intro"), ".ev-verdict")).not.toMatch(VERDICT_WORD);
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
    // In-play rows print the packet word BEHIND verbatim next to their reference; no alias to TRAILS_CLOSE.
    const inplay = rows.filter((r) => r.textContent!.includes("Kalshi in-play mid"));
    expect(inplay.length).toBeGreaterThan(0);
    for (const r of inplay) expect(r.querySelector('[data-role="verdict"]')!.textContent).toBe("BEHIND");
  });

  it("NBA prose reads cannot tell; the 227-game in-play row carries the licensed caveat and links", () => {
    const { container } = render(<CalibrationPage />);
    const intro = prose(screen.getByTestId("calibration-intro"));
    expect(intro).toContain("NBA moneyline cannot tell (interval includes zero; underpowered)");
    expect(intro).not.toContain("MATCHES_CLOSE");
    const row = container.querySelector('tr[data-key="mlb_ingame_vs_kalshi_mid"]')!;
    expect(row.querySelector('[data-role="caveat-ref"] a')!.getAttribute("href")).toBe("#ingame-join-caveat");
    const note = container.querySelector("#ingame-join-caveat")!;
    expect(note.textContent).toContain("Measured 2026-09-14 on the 227-game corpus that later failed the join-integrity check; the 178-game segmented revision keeps the verdict BEHIND.");
    const hrefs = [...note.querySelectorAll("a")].map((a) => a.getAttribute("href"));
    // next/link may prefix the basePath and drop the trailing slash in jsdom
    expect(hrefs.some((h) => /\/analytics\/findings\/ingame-join-integrity\/?$/.test(h))).toBe(true);
    expect(hrefs.some((h) => h!.endsWith("docs/papers/INPLAY_LATENCY_2026.md"))).toBe(true);
    const soccer = container.querySelector('tr[data-key="soccer_ingame_vs_kalshi_mid"]')!;
    expect(soccer.querySelector('[data-role="caveat-ref"] a')!.getAttribute("href")).toBe("#soccer-join-note");
    expect(container.querySelector("#soccer-join-note")!.textContent).toContain("Measured before the join-integrity repair; not re-established after it.");
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

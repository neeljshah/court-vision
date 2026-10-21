import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import RetractionsPage from "./page";
import { RETRACTED_FIGURE, parsePacketTable } from "./packetTable";
import RetractionStoryStub from "../retraction-story/page";
import AnalyticsRetractionStub from "../../../(analytics)/analytics/findings/retraction/page";

const FIG = RETRACTED_FIGURE;

describe("retraction record", () => {
  it("renders the packet table with every retracted figure inside a Retracted row", () => {
    const { container } = render(<RetractionsPage />);
    const rows = [...container.querySelectorAll("tbody tr")];
    expect(rows.length).toBeGreaterThanOrEqual(10);
    const flagged = rows.filter((r) => FIG.test(r.textContent ?? ""));
    expect(flagged.length).toBeGreaterThanOrEqual(4);
    for (const r of rows) {
      const hit = new RegExp(RETRACTED_FIGURE.source).test(r.textContent ?? "");
      if (hit) expect(r.textContent).toMatch(/retracted/i);
    }
    // Each retracted row carries a replacement and a YYYY-MM-DD date.
    for (const r of flagged) {
      const cells = r.querySelectorAll("td");
      expect(cells[3].textContent?.trim().length).toBeGreaterThan(10);
      expect(cells[0].textContent).toMatch(/\d{4}-\d{2}-\d{2}/);
    }
    // Nothing outside the table carries a retracted figure.
    const outside = container.cloneNode(true) as HTMLElement;
    outside.querySelector("table")?.remove();
    expect(new RegExp(RETRACTED_FIGURE.source).test(outside.textContent ?? "")).toBe(false);
  });

  it("filters coaching sentences and return figures at render time; tracking row is three sentences", () => {
    const { container } = render(<RetractionsPage />);
    const txt = container.textContent ?? "";
    expect(txt).not.toContain("Apply as an ML-infra/modeling/CV hire.");
    expect(txt).not.toContain("that is the discipline, not an embarrassment");
    expect(txt).toContain("includes the first red run and its fix.");
    for (const r of container.querySelectorAll("tbody tr")) {
      const say = r.querySelectorAll("td")[3].textContent ?? "";
      expect(say).not.toMatch(/[~+-]\s?-?\d+(?:\.\d+)?%|break-even|ROI|P&L/);
    }
    expect(txt).not.toMatch(/~-4%|-2\.00%/);
    const tracking = [...container.querySelectorAll("tbody tr")].find((r) => /reliably follows players/.test(r.textContent ?? ""))!;
    const why = tracking.querySelectorAll("td")[2].textContent ?? "";
    expect(why.split(/(?<=\.)\s+(?=[A-Z])/).length).toBe(3);
    expect(why).toMatch(/2026-09-04/);
    expect(why).toMatch(/G267/);
    expect(container.querySelector("header")!.textContent).toContain("The six withdrawn figures sit in four rows");
    expect(container.querySelector("header")!.textContent).toMatch(/only inside retraction framing: here and the methodology\s+do-not-claim list/);
    expect(container.querySelectorAll('tbody tr[data-status="Retracted"]').length).toBe(4);
  });

  it("parses a minimal table and marks status by figure", () => {
    const md = "## 4. Retired\n\n| a | b | c |\n|---|---|---|\n| **\"+18.38% x\"** | why | say |\n| \"13 months\" (added 2026-10-19) | w | s |\n\n## 5. Next\n";
    const rows = parsePacketTable(md)!;
    expect(rows.map((r) => r.status)).toEqual(["Retracted", "Retired"]);
    expect(rows[1].date).toBe("2026-10-19");
  });

  it("old retraction routes are stubs without the figures", () => {
    for (const Stub of [RetractionStoryStub, AnalyticsRetractionStub]) {
      const { container, unmount } = render(<Stub />);
      expect(container.querySelector('meta[http-equiv="refresh"]')?.getAttribute("content")).toContain("/evidence/retractions/");
      expect(new RegExp(RETRACTED_FIGURE.source).test(container.textContent ?? "")).toBe(false);
      unmount();
    }
  });
});

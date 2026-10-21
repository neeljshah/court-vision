// GateStatus.test.tsx -- the gate ledger's tokens are a separate vocabulary from the packet
// verdicts: nine tokens, each glossed, none of them a packet verdict (and none may be added
// to lib/packetVerdicts.ts); the component renders the token in its own style with the gloss
// and the ledger note; the legend is one line in ledger order.
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  GATE_GLOSS, GATE_LEDGER_NOTE, GATE_STATUSES, GateStatus, GateStatusLegend,
  gateStatusTitle, gateStatusesIn, isGateStatus, toGateStatus,
} from "./GateStatus";
import { PACKET_VERDICTS, isPacketVerdict } from "@/lib/packetVerdicts";

const NINE = [
  "SHIP", "SHIP_REVIEW", "WORSE", "STANDING_BASELINE_SET", "NULL_UNDERPOWERED",
  "VALIDATION_PENDING", "ALREADY_DONE_ON_CORE_METHOD", "COVERAGE_LOW", "DESCRIPTIVE_ONLY",
];

describe("gate ledger statuses", () => {
  it("are the nine ledger tokens, each with a plain-words gloss, and none is a packet verdict", () => {
    expect([...GATE_STATUSES]).toEqual(NINE);
    for (const t of GATE_STATUSES) {
      expect(GATE_GLOSS[t]).toMatch(/^[a-z][a-z ,]+$/);
      expect(isPacketVerdict(t)).toBe(false);
      expect((PACKET_VERDICTS as readonly string[]).includes(t)).toBe(false);
      expect(isGateStatus(t)).toBe(true);
      expect(gateStatusTitle(t)).toBe(`${t}: ${GATE_GLOSS[t]}. ${GATE_LEDGER_NOTE}.`);
    }
    for (const v of PACKET_VERDICTS) expect(isGateStatus(v)).toBe(false);
    expect(GATE_LEDGER_NOTE).toBe("gate ledger status, not a packet verdict");
    expect(isGateStatus("ship")).toBe(false);
    expect(isGateStatus(null)).toBe(false);
    expect(toGateStatus("WORSE")).toBe("WORSE");
    expect(toGateStatus("REJECT")).toBeNull();
  });

  it("gateStatusesIn keeps ledger order, once each, and ignores everything else", () => {
    expect(gateStatusesIn(["REJECT", "WORSE", "SHIP", "WORSE", null, 3, "descriptive_only", "SHIP_REVIEW"]))
      .toEqual(["SHIP", "SHIP_REVIEW", "WORSE"]);
    expect(gateStatusesIn([])).toEqual([]);
  });

  it("renders the token with its gloss and the ledger note, in the kit's gate style, never the verdict style", () => {
    render(<GateStatus token="SHIP_REVIEW" />);
    const el = screen.getByTitle("SHIP_REVIEW: passed, awaiting human review. gate ledger status, not a packet verdict.");
    expect(el).toHaveClass("ev-gate");
    expect(el).toHaveAttribute("data-gate", "SHIP_REVIEW");
    expect(el).not.toHaveAttribute("data-verdict");
    expect(el).not.toHaveClass("ev-verdict");
    expect(el.querySelector(".ev-gate__kind")).toHaveTextContent("gate");
    expect(el.querySelector(".ev-gate__label")).toHaveTextContent("SHIP_REVIEW");
    expect(el.querySelector(".ev-gate__gloss")).toHaveTextContent("passed, awaiting human review");
  });

  it("gloss={false} keeps the gloss and the note in the title only", () => {
    render(<GateStatus token="COVERAGE_LOW" gloss={false} className="extra" />);
    const el = screen.getByTitle(/COVERAGE_LOW: too little coverage\. gate ledger status, not a packet verdict\./);
    expect(el).toHaveClass("ev-gate", "extra");
    expect(el.querySelector(".ev-gate__gloss")).toBeNull();
    expect(el.textContent).toBe("gateCOVERAGE_LOW");
  });

  it("refuses a token outside the ledger set (a page cannot dress a verdict as a gate status)", () => {
    const quiet = vi.spyOn(console, "error").mockImplementation(() => undefined);
    try {
      expect(() => render(<GateStatus token={"REJECT" as never} />)).toThrow(/not a gate ledger status/);
    } finally {
      quiet.mockRestore();
    }
  });

  it("legend: one line, the lead, TOKEN = gloss for the tokens given in ledger order; null for none; all nine by default", () => {
    const { container, unmount } = render(<GateStatusLegend tokens={["WORSE", "SHIP"]} className="mt-2" />);
    const legend = screen.getByTestId("gate-status-legend");
    expect(legend.tagName).toBe("P");
    expect(legend).toHaveClass("ev-gate-legend", "mt-2");
    expect(legend.textContent).toBe("Gate ledger statuses, not packet verdicts: SHIP = passed every gate; WORSE = worse than baseline.");
    expect(container.querySelectorAll(".ev-gate-legend__token").length).toBe(2);
    unmount();
    const none = render(<GateStatusLegend tokens={[]} />);
    expect(none.container.innerHTML).toBe("");
    none.unmount();
    render(<GateStatusLegend />);
    const all = screen.getByTestId("gate-status-legend").textContent ?? "";
    for (const t of GATE_STATUSES) expect(all).toContain(`${t} = ${GATE_GLOSS[t]}`);
    expect(all.endsWith(".")).toBe(true);
  });
});

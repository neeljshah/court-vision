import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PACKET_VERDICTS, VERDICT_MEANING, VerdictLabel, isPacketVerdict, toPacketVerdict, verdictQualifier, type PacketVerdict } from "./VerdictLabel";
import { BANNED_COPY } from "@/lib/packetVerdicts";

describe("VerdictLabel", () => {
  it.each(PACKET_VERDICTS)("renders %s with the packet wording and a data attribute", (verdict) => {
    render(<VerdictLabel verdict={verdict} />);
    const label = screen.getByText(verdict);
    expect(label.parentElement).toHaveAttribute("data-verdict", verdict);
    expect(label.parentElement?.getAttribute("title")).toMatch(new RegExp(`^${verdict}`));
  });

  it("always qualifies MATCHES_CLOSE as underpowered, with the MDE when known", () => {
    const { rerender } = render(<VerdictLabel verdict="MATCHES_CLOSE" />);
    expect(screen.getByText("underpowered")).toBeInTheDocument();
    rerender(<VerdictLabel verdict="MATCHES_CLOSE" mde={0.0152} />);
    expect(screen.getByText("underpowered, MDE 0.0152")).toBeInTheDocument();
  });

  it("carries the small-sample qualifier on MODEL_SHARPER_PROVISIONAL", () => {
    render(<VerdictLabel verdict="MODEL_SHARPER_PROVISIONAL" />);
    expect(screen.getByText("small-sample retrospective diagnostic")).toBeInTheDocument();
    expect(screen.getByText("MODEL_SHARPER_PROVISIONAL").parentElement?.getAttribute("title")).toContain("not evidence of market outperformance");
  });

  it("keeps the qualifier in the title when it is hidden", () => {
    render(<VerdictLabel verdict="MATCHES_CLOSE" qualifier={false} />);
    expect(screen.queryByText("underpowered")).not.toBeInTheDocument();
    expect(screen.getByText("MATCHES_CLOSE").parentElement?.getAttribute("title")).toContain("(underpowered)");
    expect(verdictQualifier("TRAILS_CLOSE")).toBeNull();
  });

  it("refuses an unknown label at render time", () => {
    // React re-logs a render-time throw through console.error; keep the run quiet.
    const quiet = vi.spyOn(console, "error").mockImplementation(() => {});
    const bogus = "MODEL SHARPER" as unknown as PacketVerdict;
    expect(() => render(<VerdictLabel verdict={bogus} />)).toThrow(/not a packet verdict/);
    quiet.mockRestore();
  });

  it("refuses an unknown label at the type level", () => {
    // @ts-expect-error -- SURVIVES_PREREG is a ledger word, not a packet verdict label
    const element = <VerdictLabel verdict="SURVIVES_PREREG" />;
    expect(element).toBeTruthy();
  });

  it("narrows runtime strings to the packet set", () => {
    expect(isPacketVerdict("TRAILS_CLOSE")).toBe(true);
    expect(toPacketVerdict("MARKET_SHARPER_PROVISIONAL")).toBe("MARKET_SHARPER_PROVISIONAL");
    expect(toPacketVerdict("UNDERPOWERED")).toBe("UNDERPOWERED");
    expect(toPacketVerdict("MODEL SHARPER")).toBeNull();
    expect(toPacketVerdict(null)).toBeNull();
  });

  it("covers the 17 packet labels, each with a meaning and clean body copy", () => {
    expect(PACKET_VERDICTS).toHaveLength(17);
    for (const v of PACKET_VERDICTS) {
      expect(VERDICT_MEANING[v].length).toBeGreaterThan(20);
      expect(verdictQualifier(v) ?? "").not.toMatch(BANNED_COPY);
    }
    expect(verdictQualifier("BEHIND")).toBe("vs the Kalshi in-play mid");
  });
});

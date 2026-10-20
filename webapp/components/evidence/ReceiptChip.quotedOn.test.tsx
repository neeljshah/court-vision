import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReceiptChip } from "./ReceiptChip";
import { quotedOn } from "@/lib/quotedOn.server";

describe("ReceiptChip quoted-on", () => {
  it("renders no quoted-on affordance without the prop", () => {
    render(<ReceiptChip source="docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md" asOf="2026-09-24" />);
    expect(screen.queryByTestId("receipt-quoted-on")).toBeNull();
  });

  it("expands to the build-time list of quoting pages", () => {
    const list = quotedOn("scripts/platformkit/analytics_showcase/out/bookmaker_accuracy.json");
    expect(list.some((q) => q.href === "/analytics/findings/bookmaker-accuracy/")).toBe(true);
    render(<ReceiptChip source="scripts/platformkit/analytics_showcase/out/bookmaker_accuracy.json" asOf="2026-07-25" quotedOn={list} />);
    const box = screen.getByTestId("receipt-quoted-on");
    expect(within(box).getByText(`quoted on ${list.length} ${list.length === 1 ? "page" : "pages"}`)).toBeInTheDocument();
    expect(within(box).getAllByRole("listitem")).toHaveLength(list.length);
    expect(within(box).getByRole("link", { name: "/analytics/findings/bookmaker-accuracy/" })).toBeInTheDocument();
  });

  it("says so when nothing quotes the source", () => {
    render(<ReceiptChip source="docs/x/none.json" asOf="2026-07-25" quotedOn={[]} />);
    expect(screen.getByText("quoted on 0 pages")).toBeInTheDocument();
    expect(screen.getByText(/no other page in this build/)).toBeInTheDocument();
  });
});

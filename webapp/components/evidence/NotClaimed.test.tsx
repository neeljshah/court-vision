import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { NOT_CLAIMED_LINES, NotClaimed } from "./NotClaimed";

describe("NotClaimed", () => {
  it("renders the standard block as a labelled aside with the packet receipt", () => {
    const { container } = render(<NotClaimed />);
    const aside = screen.getByRole("complementary", { name: "What this is not" });
    const items = within(aside).getAllByRole("listitem").map((li) => li.textContent);
    expect(items).toEqual([...NOT_CLAIMED_LINES]);
    expect(aside.textContent).toMatch(/No edge, ROI or profit claim/);
    expect(aside.textContent).toMatch(/Paper only\. No real-money order/);
    const receipt = within(aside).getByRole("link");
    expect(receipt).toHaveAttribute("href", "https://github.com/neeljshah/court-vision/blob/master/docs/JOB_EVIDENCE_PACKET.md");
    expect(receipt.getAttribute("aria-label")).toContain("docs/JOB_EVIDENCE_PACKET.md");
    expect(container.textContent).not.toMatch(/\$\s?\d/);
  });

  it("renders one page-specific extra sentence after the standard lines", () => {
    render(<NotClaimed>Stakes are in units, never dollars.</NotClaimed>);
    expect(screen.getByText("Stakes are in units, never dollars.")).toHaveClass("ev-notclaimed__extra");
  });
});

/** RTL tests for LegendDialog.
 * Verifies the trigger button, dialog open behavior, honest explanatory copy,
 * and the absence of any edge/profit language. Radix renders dialog content
 * into a portal -- screen queries still find it after the dialog opens because
 * RTL queries the whole document body, not just the render container. */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { LegendDialog } from "./LegendDialog";

// ---------------------------------------------------------------------------
// Trigger button (closed state)
// ---------------------------------------------------------------------------

describe("LegendDialog - trigger button", () => {
  it('renders a button accessible by name matching /how to read/i', () => {
    render(<LegendDialog />);
    expect(
      screen.getByRole("button", { name: /how to read/i })
    ).toBeInTheDocument();
  });

  it("dialog content is NOT in the document before the trigger is clicked", () => {
    render(<LegendDialog />);
    // Radix mounts the portal lazily; dialog role should be absent.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Open state -- Radix portal content is in the document body so screen finds it
// ---------------------------------------------------------------------------

describe("LegendDialog - open state", () => {
  async function openDialog() {
    const user = userEvent.setup();
    render(<LegendDialog />);
    await user.click(screen.getByRole("button", { name: /how to read/i }));
    return { user };
  }

  it("clicking the trigger reveals a dialog role", async () => {
    await openDialog();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("dialog contains explanatory text about in-corpus matchups", async () => {
    await openDialog();
    // Multiple elements may mention "in-corpus"; at least one must be present.
    expect(screen.getAllByText(/in-corpus/i).length).toBeGreaterThan(0);
  });

  it("dialog contains explanatory text about market-implied probability", async () => {
    await openDialog();
    // Multiple elements may mention "market-implied"; at least one must be present.
    expect(screen.getAllByText(/market-implied/i).length).toBeGreaterThan(0);
  });

  it("dialog contains explanatory text about score and clock (SCORE ONLY row)", async () => {
    await openDialog();
    // SCORE ONLY meaning paragraph: "-> just the live score and clock are shown"
    // The badge label "SCORE ONLY" also matches the alternate branch of the regex.
    // Use getAllByText to tolerate both matches; at least one must be present.
    expect(screen.getAllByText(/score and clock|score only/i).length).toBeGreaterThan(0);
  });

  it('dialog contains the honest disclaimer copy matching /edge claimed/i', async () => {
    await openDialog();
    expect(screen.getByText(/edge claimed/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Honesty guard -- forbidden profit / edge language must be absent
// ---------------------------------------------------------------------------

describe("LegendDialog - honesty guard", () => {
  async function openDialog() {
    const user = userEvent.setup();
    render(<LegendDialog />);
    await user.click(screen.getByRole("button", { name: /how to read/i }));
    return { user };
  }

  it('does NOT contain the phrase "beat the market"', async () => {
    await openDialog();
    expect(screen.queryByText(/beat the market/i)).toBeNull();
  });

  it('does NOT contain the phrase "+EV"', async () => {
    await openDialog();
    expect(screen.queryByText(/\+EV/i)).toBeNull();
  });
});

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReceiptChip } from "./ReceiptChip";

const BLOB = "https://github.com/neeljshah/court-vision/blob/master/";

describe("ReceiptChip", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("links a repo path to its GitHub blob on master and names source, date and status", () => {
    render(<ReceiptChip source="docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md" asOf="2026-09-24" status="edge_claimed:false" />);
    const link = screen.getByRole("link", { name: "Receipt: docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md, as of 2026-09-24, edge_claimed:false" });
    expect(link).toHaveAttribute("href", `${BLOB}docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md`);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
    expect(link).toHaveAttribute("data-status", "edge_claimed:false");
    expect(link.getAttribute("title")).toMatch(/^Receipt\. Source docs\/evidence\/pregame\/DM_RECOMPUTE_2026-09-24\.md\. as of 2026-09-24\. Verification: edge_claimed:false\./);
    expect(link).toHaveTextContent("DM_RECOMPUTE_2026-09-24.md");
    expect(link).toHaveTextContent("as of 2026-09-24");
    expect(link).toHaveTextContent("edge_claimed:false");
    expect(link).toHaveClass("ev-chip");
  });

  it("is keyboard focusable", () => {
    render(<ReceiptChip source="docs/JOB_EVIDENCE_PACKET.md" asOf="2026-10-06" />);
    const link = screen.getByRole("link");
    link.focus();
    expect(link).toHaveFocus();
  });

  it("makes the analytics pages' webapp-relative public/ paths repo-relative", () => {
    render(<ReceiptChip source="public/data/showcase/calibration_stability.json" asOf="2026-07-25" />);
    expect(screen.getByRole("link")).toHaveAttribute("href", `${BLOB}webapp/public/data/showcase/calibration_stability.json`);
    expect(screen.getByRole("link").getAttribute("aria-label")).toContain("webapp/public/data/showcase/calibration_stability.json");
  });

  it("renders validation_pending and 'date not published' without a date, never a default green", () => {
    render(<ReceiptChip source="docs/JOB_EVIDENCE_PACKET.md" asOf={null} status="descriptive_only" />);
    const link = screen.getByRole("link", { name: /validation_pending/ });
    expect(link).toHaveAttribute("data-status", "validation_pending");
    expect(link).toHaveTextContent("date not published");
  });

  it("links a bare published artifact name to the exported JSON on this site", () => {
    vi.stubEnv("NEXT_PUBLIC_BASE_PATH", "/court-vision");
    render(<ReceiptChip source="blowout_dynamics.json" asOf="2026-07-25" />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/court-vision/data/showcase/blowout_dynamics.json");
    expect(link).not.toHaveAttribute("target");
  });

  it("shows a non-path source in full as not published, with no dead link", () => {
    render(<ReceiptChip source="git rev-list --count origin/master" asOf="2026-10-19" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    const note = screen.getByRole("note");
    expect(note).toHaveTextContent("git rev-list --count origin/master (not published)");
    expect(note.getAttribute("title")).toContain("Artifact not published on this site.");
  });

  it("keeps source and status in the accessible name when compact", () => {
    render(<ReceiptChip compact source="scripts/platformkit/analytics_showcase/out/honesty_exhibit.json" asOf="2026-07-22T20:15:22Z" />);
    const link = screen.getByRole("link");
    expect(link.getAttribute("aria-label")).toBe("Receipt: scripts/platformkit/analytics_showcase/out/honesty_exhibit.json, as of 2026-07-22, descriptive_only");
    expect(link.textContent).toBe("R");
  });

  it("words an artifact generation stamp as generated, and carries a note into the title", () => {
    render(<ReceiptChip source="docs/evidence/CANONICAL_FIGURES.json" asOf="2026-10-19" kind="snapshot" note="module_count in site_manifest.json" />);
    const link = screen.getByRole("link");
    expect(link).toHaveTextContent("generated 2026-10-19");
    expect(link.getAttribute("title")).toContain("(module_count in site_manifest.json)");
  });
});

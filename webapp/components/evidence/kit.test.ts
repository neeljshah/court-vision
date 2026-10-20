import { afterEach, describe, expect, it, vi } from "vitest";
import { PACKET_HREF, basename, blobUrl, dayOf, formatFigureField, isRepoPath, normalizeRepoPath, receiptHref } from "./kit";

describe("evidence kit helpers", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("recognises repo paths under the public roots only", () => {
    expect(isRepoPath("docs/JOB_EVIDENCE_PACKET.md")).toBe(true);
    expect(isRepoPath("webapp/app/(analytics)/analytics/findings/")).toBe(true);
    expect(isRepoPath("scripts\\platformkit\\analytics_showcase\\out\\honesty_exhibit.json")).toBe(true);
    expect(isRepoPath("public/data/showcase/calibration_stability.json")).toBe(true);
    expect(isRepoPath("README.md")).toBe(true);
    expect(isRepoPath("data/registry/signal_registry.parquet")).toBe(false);
    expect(isRepoPath("git rev-list --count origin/master")).toBe(false);
    expect(isRepoPath("docs/../secrets.txt")).toBe(false);
    expect(isRepoPath("")).toBe(false);
  });

  it("builds GitHub blob links under master, keeping parentheses readable", () => {
    expect(blobUrl("docs/evidence/CANONICAL_FIGURES.json")).toBe("https://github.com/neeljshah/court-vision/blob/master/docs/evidence/CANONICAL_FIGURES.json");
    expect(blobUrl("webapp/app/(analytics)/analytics/findings/")).toBe("https://github.com/neeljshah/court-vision/blob/master/webapp/app/(analytics)/analytics/findings/");
    expect(PACKET_HREF).toBe("https://github.com/neeljshah/court-vision/blob/master/docs/JOB_EVIDENCE_PACKET.md");
    expect(normalizeRepoPath("./public/data/showcase/x.json")).toBe("webapp/public/data/showcase/x.json");
    expect(basename("docs/evidence/forward/fill_realism/")).toBe("fill_realism");
  });

  it("resolves a receipt href: explicit, blob, exported artifact, else none", () => {
    vi.stubEnv("NEXT_PUBLIC_BASE_PATH", "/court-vision");
    expect(receiptHref("docs/JOB_EVIDENCE_PACKET.md", "https://example.test/pinned")).toBe("https://example.test/pinned");
    expect(receiptHref("docs/JOB_EVIDENCE_PACKET.md")).toBe(PACKET_HREF);
    expect(receiptHref("blowout_dynamics.json")).toBe("/court-vision/data/showcase/blowout_dynamics.json");
    expect(receiptHref("private_measurement.json")).toBeNull();
    expect(receiptHref("count of finding pages")).toBeNull();
  });

  it("extracts valid calendar days only", () => {
    expect(dayOf("2026-10-19")).toBe("2026-10-19");
    expect(dayOf("2026-07-22T20:15:22.041778+00:00")).toBe("2026-07-22");
    expect(dayOf("2026-02-30")).toBeNull();
    expect(dayOf("Published snapshot")).toBeNull();
    expect(dayOf(null)).toBeNull();
  });

  it("formats every figure field one way", () => {
    expect(formatFigureField("gap", 0.0039)).toBe("+0.0039");
    expect(formatFigureField("gap", -0.0042)).toBe("-0.0042");
    expect(formatFigureField("model", 0.2429)).toBe("0.2429");
    expect(formatFigureField("mde", 0.015)).toBe("0.0150");
    expect(formatFigureField("n", 13992)).toBe("13,992");
    expect(formatFigureField("ci95", [0.0028, 0.0051])).toBe("[+0.0028, +0.0051]");
    expect(formatFigureField("dm_p", "3.6e-12")).toBe("3.6e-12");
    expect(formatFigureField("value", "2026-10-16")).toBe("2026-10-16");
    expect(formatFigureField("close", null)).toBe("not published");
  });
});

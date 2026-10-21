import { describe, expect, it } from "vitest";
import { findingHref } from "./findingHref";
import { findingsIndex } from "./findingsIndex";
import { resolveRedirect } from "@/lib/redirects";

describe("findingHref", () => {
  it("builds the exported finding page path with the trailing slash", () => {
    expect(findingHref("shrinkage")).toBe("/analytics/findings/shrinkage/");
  });

  it("sends a retired finding slug to its new home instead of the redirect stub", () => {
    expect(findingHref("retraction")).toBe("/evidence/retractions/");
  });

  it("never links a registered finding to a redirect stub", () => {
    for (const finding of findingsIndex) expect(resolveRedirect(findingHref(finding.slug)), finding.slug).toBeNull();
  });
});

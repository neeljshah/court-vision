// evidence.server.test.ts -- the evidence spine fails loudly: a missing, corrupt or
// empty index throws (instead of dropping every /evidence/<slug> page with a green
// build), claim_count / claims / docs/evidence/<slug>.md must agree, edge_claimed is
// pending unless explicitly false, and a gap in a claim's markdown is logged by slug.
import { afterEach, describe, expect, it, vi } from "vitest";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { buildClaimIndex, buildClaimPage, readEvidenceIndex, type RawIndex } from "../evidence.server";

const idx: RawIndex = {
  claim_count: 2, bucket_order: ["b"], edge_claimed: false,
  claims: [
    { slug: "a-one", bucket: "b", title: "A", edge_claimed: false, strongest_receipt: { source: "x.json", label: "x" } },
    { slug: "b-two", bucket: "b", title: "B" }, // no edge_claimed key at all
  ],
};

/** A temp index file plus a docs/evidence directory holding one .md per name. */
function fixture(index: unknown, mds: Record<string, string>) {
  const dir = mkdtempSync(join(tmpdir(), "evidence-"));
  const file = join(dir, "evidence_index.json");
  writeFileSync(file, typeof index === "string" ? index : JSON.stringify(index));
  const evidenceDir = join(dir, "evidence");
  mkdirSync(evidenceDir);
  for (const [name, body] of Object.entries(mds)) writeFileSync(join(evidenceDir, `${name}.md`), body);
  return { file, evidenceDir };
}

afterEach(() => vi.restoreAllMocks());

describe("readEvidenceIndex", () => {
  it("throws when the index is missing, corrupt or has no claims", () => {
    const { file, evidenceDir } = fixture("{not json", {});
    expect(() => readEvidenceIndex(join(evidenceDir, "none.json"), evidenceDir)).toThrow(/missing or unreadable/);
    expect(() => readEvidenceIndex(file, evidenceDir)).toThrow(/not valid JSON/);
    const empty = fixture({ claim_count: 0, claims: [] }, {});
    expect(() => readEvidenceIndex(empty.file, empty.evidenceDir)).toThrow(/has no claims/);
  });

  it("throws when claim_count, claims.length and the docs/evidence/<slug>.md files disagree", () => {
    const docs = { "a-one": "# A\n", "b-two": "# B\n" };
    const miscount = fixture({ ...idx, claim_count: 3 }, docs);
    expect(() => readEvidenceIndex(miscount.file, miscount.evidenceDir)).toThrow(/claim_count=3, claims=2/);
    const missingDoc = fixture(idx, { "a-one": "# A\n" });
    expect(() => readEvidenceIndex(missingDoc.file, missingDoc.evidenceDir)).toThrow(/no \.md for b-two/);
    const extraDoc = fixture(idx, { ...docs, "c-three": "# C\n" });
    expect(() => readEvidenceIndex(extraDoc.file, extraDoc.evidenceDir)).toThrow(/\.md without an index row: c-three/);
    const ok = fixture(idx, docs);
    expect(readEvidenceIndex(ok.file, ok.evidenceDir).claims).toHaveLength(2);
  });

  it("accepts the staged index on this clone", () => {
    const real = readEvidenceIndex();
    expect(real.claims!.length).toBe(real.claim_count);
    expect(real.claims!.length).toBeGreaterThan(0);
  });
});

describe("edge_claimed", () => {
  it("is verified only when the index says false explicitly; an absent key is pending", () => {
    const { evidenceDir } = fixture(idx, { "a-one": "# A\n", "b-two": "# B\n" });
    const entries = buildClaimIndex(idx).buckets[0].claims;
    expect(entries.map((e) => [e.slug, e.verified])).toEqual([["a-one", "edge_claimed:false"], ["b-two", "validation_pending"]]);
    expect(buildClaimPage("b-two", { index: idx, evidenceDir })?.verified).toBe("validation_pending");
    expect(buildClaimPage("a-one", { index: idx, evidenceDir })?.verified).toBe("edge_claimed:false");
    for (const bucket of buildClaimIndex().buckets) {
      for (const c of bucket.claims) expect(c.verified, c.slug).toBe("edge_claimed:false");
    }
  });
});

describe("markdown gaps", () => {
  it("are logged by slug: a missing heading, a Receipts section with no table, an unstaged image", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const md = [
      "# A", "", "> lede", "", "## The claim", "", "Text.", "", "## Receipts", "", "No table here.", "",
      "![a figure](img/not-staged-anywhere.png)", "", "## Reproduce", "", "Run it.", "",
    ].join("\n");
    // Its own slug: report() dedupes per (slug, gap) across the whole module.
    const gaps: RawIndex = { claim_count: 1, bucket_order: ["b"], claims: [{ slug: "c-gaps", bucket: "b", title: "C" }] };
    const { evidenceDir } = fixture(gaps, { "c-gaps": md });
    const page = buildClaimPage("c-gaps", { index: gaps, evidenceDir });
    expect(page?.status).toBe("MEASURED");
    expect(page?.receipts).toEqual([]);
    expect(page?.figures).toEqual([]);
    const msgs = warn.mock.calls.map((c) => String(c[0]));
    expect(msgs).toContain('evidence: docs/evidence/c-gaps.md has no "## How it works" heading');
    expect(msgs).toContain('evidence: docs/evidence/c-gaps.md has no "## Why this matters" heading');
    expect(msgs).toContain("evidence: docs/evidence/c-gaps.md has a Receipts section with no table rows");
    expect(msgs).toContain("evidence: docs/evidence/c-gaps.md has a Reproduce section with no code block");
    expect(msgs).toContain("evidence: docs/evidence/c-gaps.md cites image not-staged-anywhere.png, which is not staged under public/img/showcase");
    expect(msgs.some((m) => /"## The claim"/.test(m))).toBe(false);
    // Logged once per (slug, gap): a second build of the same page adds nothing.
    const n = warn.mock.calls.length;
    buildClaimPage("c-gaps", { index: gaps, evidenceDir });
    expect(warn.mock.calls.length).toBe(n);
  });
});

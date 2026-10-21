// receipts-ordering.test.ts -- the /receipts/<i> contract. public/receipts.json rows carry
// no stable id, so a receipt's URL is its position in `rows`: the detail pages
// (generateStaticParams), the sitemap family and the ledger links all derive from that
// one array in file order. The day a row gains an id, this test fails and the three
// readers switch to it together.
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import receipts from "@/public/receipts.json";
import { sitemapFamilies } from "@/lib/sitemapFamilies.server";
import { generateStaticParams } from "../[row]/page";

const rows = receipts.rows as Record<string, unknown>[];

describe("/receipts/<i> ordering contract", () => {
  it("rows carry no id key, so the array position is the only stable key", () => {
    expect(rows.length).toBeGreaterThan(0);
    for (const [i, r] of rows.entries()) {
      for (const k of ["id", "row_id", "receipt_id", "slug", "key"]) expect(r, `row ${i} has ${k}`).not.toHaveProperty(k);
    }
  });

  it("the detail pages, the sitemap family and the ledger links all use that position", async () => {
    expect(await generateStaticParams()).toEqual(rows.map((_, i) => ({ row: String(i) })));
    expect(sitemapFamilies().receipts).toEqual(rows.map((_, i) => `/receipts/${i}`));
    const ledger = readFileSync(join(process.cwd(), "app/(terminal)/receipts/page.tsx"), "utf-8");
    expect(ledger).toMatch(/href=\{`\/receipts\/\$\{i\}`\}/);
  });
});

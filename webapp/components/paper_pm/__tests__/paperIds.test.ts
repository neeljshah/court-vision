// paperIds.test.ts -- every baked forward fill round-trips link -> exported directory
// -> route param -> lookup, so each /paper/<id>/ page resolves its own fill.
import { describe, it, expect } from "vitest";
import trail from "@/public/demo-data/api_paper_trail_limit_400.json";
import type { PaperTrailRow } from "@/lib/p5api";
import { paperDetailHref } from "@/lib/paperLinks";
import { fillParam, findFill, canonicalId } from "../paperIds";
import { bakedFillParams } from "@/components/paper_pm/bakedFillParams.server";
import { generateStaticParams } from "@/app/(terminal)/paper/[betId]/page";

const rows = (trail as unknown as { trail: PaperTrailRow[] }).trail;

describe("forward fill ids", () => {
  it("the baked trail has 29 fills with 29 distinct ids, and the page exports exactly those", async () => {
    const params = rows.map(fillParam);
    expect(rows.length).toBe(29);
    expect(new Set(params).size).toBe(29);
    expect(bakedFillParams()).toEqual(params);
    expect(await generateStaticParams()).toEqual(params.map(betId => ({ betId })));
  });

  it("link -> directory -> param -> lookup returns the same fill for every row", () => {
    for (const row of rows) {
      const param = fillParam(row); // generateStaticParams value = exported directory name
      const seg = paperDetailHref(param).split("/")[2]; // what the href carries
      const dir = decodeURIComponent(seg); // the host decodes one layer
      expect(dir).toBe(param);
      // the client may see the param with zero, one or two layers still encoded
      for (const seen of [seg, dir, decodeURIComponent(dir)]) expect(findFill(rows, seen)).toBe(row);
    }
  });

  it("an unknown id finds nothing (no same-game fallback)", () => {
    const r = rows[0];
    expect(findFill(rows, encodeURIComponent(`${r.sport}|${r.game_id}|nope`))).toBeNull();
    expect(canonicalId("%E0%A4%A")).toBe("%E0%A4%A"); // malformed escape stays as is
  });
});

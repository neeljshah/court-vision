// app/atlas/page.tsx -- Entity Atlas pack index (T1.2). Static server
// component: reads the 7 staged atlas_*_manifest.json files at build time via
// lib/atlas.server (no client fetch, no /api route). Descriptive-only spine:
// these are reference cards, never predictions or edge claims.

import { PackIndex } from "@/components/atlas/PackIndex";
import { listPacks } from "@/lib/atlas.server";

export const metadata = {
  title: "Atlas",
  description:
    "The browsable entity atlas: 7 descriptive packs across NBA, MLB, soccer, " +
    "and tennis, reference cards only, no predictions.",
};

export default function AtlasIndexPage() {
  const packs = listPacks();
  const totalEntities = packs.reduce((sum, p) => sum + p.count, 0);

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <header>
        <p className="microlabel">atlas</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          Entity Atlas
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          {totalEntities} entities across {packs.length} packs -- career / last-N
          reference cards, descriptive only. No prediction and no edge claim
          lives on this page; every number carries its own receipt.
        </p>
      </header>

      <PackIndex packs={packs} />
    </main>
  );
}

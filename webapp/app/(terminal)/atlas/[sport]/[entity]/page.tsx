// app/atlas/[sport]/[entity]/page.tsx -- one entity's descriptive card (T1.4).
//
// Server component, part of the static export: getEntity() reads the staged
// manifest at build time (no client fetch). generateStaticParams enumerates all
// 1,549 entities across the 7 packs. Renders the mandatory descriptive_only
// banner, the HTML EntityCard (not a PNG), a sample-floor note, and cross-links
// to related descriptive artifacts. Mirrors mockups/atlas-entity.html.
//
// Export cost note for the gate: 1,549 fully-static pages. That is a lot of
// HTML but each is tiny and data-free at runtime; NOT truncated here. If build
// time becomes a problem, shard generateStaticParams by pack -- do not silently
// drop entities.

import { existsSync } from "node:fs";
import { join } from "node:path";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getEntity, entityParams } from "@/lib/atlas.server";
import { HonestBanner } from "@/components/showcase/HonestBanner";
import { EntityCard } from "@/components/atlas/EntityCard";
import { EntityLinks, type EntityLink } from "@/components/atlas/EntityLinks";
import { Panel, PanelHead } from "@/components/ui/terminal";
import { ReceiptChip } from "@/components/showcase/ReceiptChip";

const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";
const SHOWCASE_DIR = join(process.cwd(), "public", "data", "showcase");

export function generateStaticParams() {
  return entityParams();
}

export function generateMetadata({ params }: { params: { sport: string; entity: string } }) {
  const e = getEntity(params.sport, params.entity);
  return {
    title: e ? `Atlas / ${e.label} / ${e.entity}` : "Atlas entity",
    description: e
      ? `Descriptive reference card for ${e.entity} -- historical rates, not a prediction.`
      : "Atlas entity not found.",
  };
}

// Curated per-pack descriptive artifacts that cover an entity's pack. Kept
// small and honest: only NBA has a mockup-backed set today. ponytail: extend
// this map per sport when those packs get their own showcase artifacts -- an
// empty list just renders no cross-links section.
const CROSS_LINKS: Record<string, { file: string; title: string; desc: string }[]> = {
  nba: [
    { file: "nba_consistency_profiles", title: "Consistency profile", desc: "Game-to-game variance of the per-36 rates" },
    { file: "on_off_showcase", title: "On / off net rating", desc: "Team net rating with the player on vs off the floor" },
    { file: "nba_matchup_grid", title: "Matchup grid", desc: "Head-to-head descriptive splits by opponent" },
  ],
};

function crossLinks(sport: string, asOf: string | null): EntityLink[] {
  const specs = CROSS_LINKS[sport] ?? [];
  return specs
    .filter((s) => existsSync(join(SHOWCASE_DIR, `${s.file}.json`)))
    .map((s) => ({
      id: s.file,
      title: s.title,
      desc: s.desc,
      href: `${BASE_PATH}/data/showcase/${s.file}.json`,
      chip: {
        sourceArtifact: `webapp/public/data/showcase/${s.file}.json`,
        asOf,
        verified: "descriptive_only" as const,
        href: null,
      },
    }));
}

export default function AtlasEntityPage({
  params,
}: {
  params: { sport: string; entity: string };
}) {
  const entity = getEntity(params.sport, params.entity);
  if (!entity) notFound();

  const links = crossLinks(entity.sport, entity.asOf);

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <nav aria-label="Breadcrumb" className="microlabel">
        <Link href="/atlas" className="hover:text-primary">
          atlas
        </Link>{" "}
        /{" "}
        <Link href={`/atlas/${params.sport}`} className="hover:text-primary">
          {entity.label}
        </Link>{" "}
        / <span className="text-foreground">{entity.entity}</span>
      </nav>

      <HonestBanner kind="descriptive_only" asOf={entity.asOf}>
        These are historical per-period rates and splits for {entity.entity}, not a
        prediction and not an edge claim. descriptive_only: true.
      </HonestBanner>

      <EntityCard {...entity} />

      {entity.floors && (
        <Panel>
          <PanelHead
            title="sample floor"
            asOf={entity.asOf ?? undefined}
            right={<ReceiptChip {...entity.chip} />}
          />
          <p className="m-0 px-3.5 py-3 text-sm leading-relaxed text-muted-foreground">
            An entity earns a descriptive card only after clearing a minimum-sample
            floor, so rates are not read off tiny samples. The floor for this pack is{" "}
            <span className="font-data text-foreground">{entity.floors}</span>. Entities
            below the floor are deliberately left off -- we do not print rates we cannot
            stand behind.
          </p>
        </Panel>
      )}

      {links.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="microlabel">related descriptive artifacts</h2>
          <EntityLinks artifacts={links} />
        </section>
      )}

      <footer className="border-t border-border pt-4 text-xs text-faint">
        Built by Neel Shah. Every figure on this card traces to a committed JSON under
        webapp/public/data/showcase/. Descriptive only: no prediction, ROI, or edge is
        claimed. Truth source: docs/JOB_EVIDENCE_PACKET.md.
      </footer>
    </main>
  );
}

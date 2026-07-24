// app/atlas/[sport]/page.tsx -- one pack's sortable entity table (T1.3).
//
// Server component: reads the staged manifest via atlas.server at build time,
// renders the mandatory descriptive_only banner + a receipt chip on the panel
// head, then hands rows to the client EntityTable for sort/filter.

import Link from "next/link";
import { notFound } from "next/navigation";
import { getPack, packParams } from "@/lib/atlas.server";
import { Panel, PanelHead } from "@/components/ui/terminal";
import { HonestBanner } from "@/components/showcase/HonestBanner";
import { ReceiptChip } from "@/components/showcase/ReceiptChip";
import { EntityTable } from "@/components/atlas/EntityTable";

export function generateStaticParams() {
  return packParams();
}

export function generateMetadata({ params }: { params: { sport: string } }) {
  const pack = getPack(params.sport);
  return {
    title: pack ? `Atlas / ${pack.label}` : "Atlas",
    description: pack
      ? `Descriptive reference cards for ${pack.rows.length} ${pack.label}.`
      : "Atlas pack not found.",
  };
}

export default function AtlasPackPage({ params }: { params: { sport: string } }) {
  const pack = getPack(params.sport);
  if (!pack) notFound();

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <header className="flex flex-col gap-2">
        <p className="microlabel">
          <Link href="/atlas" className="hover:text-primary">
            atlas
          </Link>{" "}
          / {pack.label}
        </p>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          {pack.label}
        </h1>
      </header>

      <HonestBanner kind="descriptive_only" asOf={pack.asOf} />

      <Panel>
        <PanelHead
          title={`${pack.rows.length} entries`}
          asOf={pack.asOf ?? undefined}
          right={<ReceiptChip {...pack.chip} />}
        />
        <div className="p-3">
          <EntityTable columns={pack.columns} rows={pack.rows} sport={pack.slug} />
        </div>
      </Panel>
    </main>
  );
}

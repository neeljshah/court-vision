// EntityLinks.tsx -- "related descriptive artifacts" cross-links (T1.4).
//
// Server component. Each row links to a staged descriptive showcase artifact
// that covers this entity's pack, with a receipt chip and a one-line note.
// These are pack-level descriptive artifacts (consistency, on/off, matchup,
// ...), not per-entity claims -- the copy says so, honestly. Renders nothing
// when the list is empty (e.g. a pack with no curated cross-links).

import { Panel } from "@/components/ui/terminal";
import { ReceiptChip, type ReceiptChipProps } from "@/components/showcase/ReceiptChip";

export type EntityLink = {
  id: string;
  title: string;
  desc: string;
  href: string;
  chip: ReceiptChipProps;
};

export function EntityLinks({ artifacts }: { artifacts: EntityLink[] }) {
  if (artifacts.length === 0) return null;
  return (
    <Panel>
      {artifacts.map((a) => (
        <div
          key={a.id}
          className="flex items-center justify-between gap-3 border-t border-border px-3.5 py-3 first:border-t-0"
        >
          <div>
            <div className="text-sm text-foreground">{a.title}</div>
            <div className="microlabel mt-0.5">{a.desc}</div>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            <ReceiptChip {...a.chip} />
            <a href={a.href} className="font-data text-xs text-primary hover:underline">
              view -&gt;
            </a>
          </div>
        </div>
      ))}
    </Panel>
  );
}

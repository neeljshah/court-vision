// components/lab/InstrumentPanel.tsx -- thin wrapper for a microstructure
// instrument. Renders a <Panel> with the instrument title, a novelty badge
// (STANDARD_INSTRUMENT etc., faint -- these are textbook descriptive measures,
// not a new method), and a fixed edge_claimed:false label so the honesty stance
// is on every instrument. Body is caller-supplied (chart or table). ASCII only.

import { Panel, PanelHead } from "@/components/ui/terminal";
import { ReceiptChip, type ReceiptChipProps } from "@/components/showcase/ReceiptChip";

export function InstrumentPanel({
  title,
  novelty,
  asOf,
  stale = false,
  receipt,
  caption,
  children,
}: {
  title: string;
  novelty?: string | null; // e.g. "STANDARD_INSTRUMENT"
  asOf?: string | null;
  stale?: boolean;
  receipt?: ReceiptChipProps;
  caption?: string; // honest source/method note under the figure
  children: React.ReactNode;
}) {
  return (
    <Panel>
      <PanelHead
        title={title}
        asOf={asOf}
        stale={stale}
        right={
          <span className="flex items-center gap-2">
            {novelty && (
              <span className="microlabel border border-border px-1.5 py-px text-faint">
                {novelty}
              </span>
            )}
            <span className="microlabel border border-info/50 px-1.5 py-px text-info">
              edge_claimed:false
            </span>
          </span>
        }
      />
      <div className="p-3">{children}</div>
      {(caption || receipt) && (
        <div className="flex items-start gap-1 border-t border-border px-3 py-2 text-[11px] text-faint">
          {caption && <span className="max-w-[68ch] leading-relaxed">{caption}</span>}
          {receipt && <ReceiptChip {...receipt} />}
        </div>
      )}
    </Panel>
  );
}

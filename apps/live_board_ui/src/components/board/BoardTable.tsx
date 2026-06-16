/**
 * BoardTable -- virtualized, sectioned list of BoardRow items.
 * Sections: Live > Upcoming > Finished (collapsible when >12).
 * Uses @tanstack/react-virtual for performance with 300+ tennis rows.
 * Dynamic columns: Odds and Total tracks appear only when data is present.
 * flashKeys: optional Set of gameKey strings whose rows should animate on score change.
 */
import { useRef, useState, useMemo, type CSSProperties } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { BoardRow, Sport } from "@/types/board";
import type { Density } from "@/hooks/useDensity";
import { sortRows } from "@/lib/format";
import { cn } from "@/lib/utils";
import { BoardRowItem } from "@/components/board/BoardRowItem";
import { computeColumns, rowGridClass } from "@/components/board/columns";
import { gameKey } from "@/lib/gameKey";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type DisplayItem =
  | { type: "header"; label: string; key: string; toggle?: boolean; count?: number }
  | { type: "row"; row: BoardRow; key: string };

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const FINISHED_COLLAPSE_THRESHOLD = 12;
const HEADER_HEIGHT = 34;
const ROW_HEIGHT_BY_DENSITY: Record<Density, number> = { comfortable: 96, compact: 64 };

// Static column header definitions; optional entries are filtered at render time.
const COL_HEADERS_BASE = [
  { label: "Status",  always: true,  cls: "" },
  { label: "Matchup", always: true,  cls: "" },
  { label: "Score",   always: true,  cls: "" },
  { label: "Win %",   always: true,  cls: "" },
  { label: "Odds",    always: false, cls: "hidden lg:block", key: "odds" },
  { label: "Total",   always: false, cls: "hidden lg:block", key: "total" },
  { label: "Source",  always: true,  cls: "" },
  { label: "Updated", always: true,  cls: "hidden lg:block" },
] as const;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface BoardTableProps {
  rows: BoardRow[];
  sport: Sport;
  generatedAt: string | null;
  onSelect?: (row: BoardRow) => void;
  flashKeys?: Set<string>;
  density?: Density;
}

export function BoardTable({ rows, sport, generatedAt, onSelect, flashKeys, density = "comfortable" }: BoardTableProps) {
  const [showFinished, setShowFinished] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Derive dynamic column visibility from the live row set.
  const columns = useMemo(() => computeColumns(rows), [rows]);

  // 1. Sort and partition into sections
  const sorted = useMemo(() => sortRows(rows), [rows]);

  const liveRows     = useMemo(() => sorted.filter((r) => r.state === "in"),   [sorted]);
  const upcomingRows = useMemo(() => sorted.filter((r) => r.state === "pre"),  [sorted]);
  const finishedRows = useMemo(() => sorted.filter((r) => r.state === "post"), [sorted]);

  const collapsible = finishedRows.length > FINISHED_COLLAPSE_THRESHOLD;

  // 2. Build flat display list
  const displayItems = useMemo<DisplayItem[]>(() => {
    const items: DisplayItem[] = [];

    if (liveRows.length > 0) {
      items.push({ type: "header", label: "Live", key: "hdr-live" });
      liveRows.forEach((r, i) =>
        items.push({ type: "row", row: r, key: `live-${i}` })
      );
    }

    if (upcomingRows.length > 0) {
      items.push({ type: "header", label: "Upcoming", key: "hdr-upcoming" });
      upcomingRows.forEach((r, i) =>
        items.push({ type: "row", row: r, key: `upcoming-${i}` })
      );
    }

    if (finishedRows.length > 0) {
      if (collapsible) {
        items.push({
          type: "header",
          label: showFinished ? "Hide Finished" : `Show ${finishedRows.length} Finished`,
          key: "hdr-finished",
          toggle: true,
          count: finishedRows.length,
        });
        if (showFinished) {
          finishedRows.forEach((r, i) =>
            items.push({ type: "row", row: r, key: `finished-${i}` })
          );
        }
      } else {
        items.push({ type: "header", label: "Finished", key: "hdr-finished" });
        finishedRows.forEach((r, i) =>
          items.push({ type: "row", row: r, key: `finished-${i}` })
        );
      }
    }

    return items;
  }, [liveRows, upcomingRows, finishedRows, collapsible, showFinished]);

  // 3. Virtualizer
  const virtualizer = useVirtualizer({
    count: displayItems.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: (index) => {
      const item = displayItems[index];
      return item?.type === "header" ? HEADER_HEIGHT : ROW_HEIGHT_BY_DENSITY[density];
    },
    measureElement:
      typeof window !== "undefined" &&
      navigator.userAgent.indexOf("Firefox") === -1
        ? (el) => el.getBoundingClientRect().height
        : undefined,
    overscan: 6,
  });

  const virtualItems = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();

  // Resolve the grid template from the dynamic column set.
  const gridTemplate = rowGridClass(columns);

  // Filter column headers to only those that are always-shown or toggled on.
  const visibleHeaders = COL_HEADERS_BASE.filter((col) => {
    if (col.always) return true;
    if ("key" in col) {
      return col.key === "odds" ? columns.odds : columns.total;
    }
    return false;
  });

  return (
    <div className="flex flex-col gap-2">
      {/* Column header bar -- desktop only. Purely visual: each row carries its
          own accessible labels, so the bar is hidden from assistive tech. */}
      <div
        aria-hidden="true"
        className={cn(
          "hidden md:grid items-center gap-2 px-3 py-1",
          gridTemplate,
          "text-[10.5px] uppercase tracking-wide font-bold text-muted select-none"
        )}
      >
        {visibleHeaders.map(({ label, cls }) => (
          <span key={label} className={cls}>
            {label}
          </span>
        ))}
      </div>

      {/* Scroll container */}
      <div
        ref={scrollRef}
        role="list"
        aria-label={`${sport.toUpperCase()} games`}
        className="max-h-[calc(100vh-220px)] overflow-auto rounded-lg border border-line bg-surface outline-none focus-visible:ring-2 focus-visible:ring-accent"
        tabIndex={0}
      >
        {displayItems.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-muted text-sm">
            No games to display.
          </div>
        ) : (
          <div style={{ height: totalSize, width: "100%", position: "relative" }}>
            {virtualItems.map((virtualItem) => {
              const item = displayItems[virtualItem.index];
              if (!item) return null;

              const itemStyle: CSSProperties = {
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                transform: `translateY(${virtualItem.start}px)`,
              };

              if (item.type === "header") {
                const isToggle = item.toggle === true;
                return (
                  <div
                    key={item.key}
                    data-index={virtualItem.index}
                    ref={virtualizer.measureElement}
                    style={itemStyle}
                    role="presentation"
                  >
                    {isToggle ? (
                      <button
                        type="button"
                        onClick={() => setShowFinished((v) => !v)}
                        className={cn(
                          "w-full flex items-center gap-1.5 px-3 py-1.5",
                          "bg-surface2 text-[10.5px] uppercase tracking-wide text-muted font-bold",
                          "hover:text-txt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                          "transition-colors"
                        )}
                        aria-expanded={showFinished}
                      >
                        {showFinished ? (
                          <ChevronUp
                            className="w-3 h-3 shrink-0"
                            aria-hidden="true"
                          />
                        ) : (
                          <ChevronDown
                            className="w-3 h-3 shrink-0"
                            aria-hidden="true"
                          />
                        )}
                        <span>
                          {showFinished
                            ? "Hide Finished"
                            : `Show ${item.count ?? 0} Finished`}
                        </span>
                      </button>
                    ) : (
                      <div
                        className="bg-surface2 text-[10.5px] uppercase tracking-wide text-muted px-3 py-1.5 font-bold flex items-center gap-1.5"
                      >
                        {item.label === "Live" && (
                          <span
                            className="inline-block w-1.5 h-1.5 rounded-full bg-live animate-live-pulse"
                            aria-hidden="true"
                          />
                        )}
                        {item.label}
                      </div>
                    )}
                  </div>
                );
              }

              // Row item -- compute the stable game key and forward flashing state.
              const key = gameKey(item.row);
              return (
                <div
                  key={item.key}
                  data-index={virtualItem.index}
                  ref={virtualizer.measureElement}
                  style={itemStyle}
                  role="listitem"
                >
                  <BoardRowItem
                    row={item.row}
                    generatedAt={generatedAt}
                    columns={columns}
                    style={{ position: "relative" } as CSSProperties}
                    onSelect={onSelect}
                    flashing={flashKeys?.has(key) ?? false}
                    density={density}
                  />
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

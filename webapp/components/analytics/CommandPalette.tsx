"use client";
// Global Cmd+K / "/" command palette -- typo-tolerant search over the static
// showcase record list (1,637 destinations). cmdk supplies the dialog + keyboard
// nav; MiniSearch supplies fuzzy/prefix scoring. The 410KB record JSON is
// lazy-fetched on first open, never bundled. DESIGN_ANALYTICS palette request.
import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import MiniSearch from "minisearch";

interface Rec {
  id: string;
  title: string;
  subtitle: string;
  href: string;
  type: "entity" | "module" | "finding" | "page";
  keywords: string[];
}

const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";
const GROUP_ORDER: Array<{ type: Rec["type"]; heading: string }> = [
  { type: "page", heading: "Pages" },
  { type: "finding", heading: "Findings" },
  { type: "module", heading: "Modules" },
  { type: "entity", heading: "Entities" },
];

type LoadState = "idle" | "loading" | "ready" | "error";

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const recordsRef = useRef<Map<string, Rec>>(new Map());
  const indexRef = useRef<MiniSearch<Rec> | null>(null);
  const [results, setResults] = useState<Rec[]>([]);

  const load = useCallback(() => {
    if (loadState !== "idle") return;
    setLoadState("loading");
    fetch(`${BASE_PATH}/data/showcase/search_records.json`)
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((data: { records: Rec[] }) => {
        const recs = data.records || [];
        recs.forEach((r) => recordsRef.current.set(r.id, r));
        const mini = new MiniSearch<Rec>({
          idField: "id",
          fields: ["title", "subtitle", "keywords"],
          storeFields: ["id", "title", "subtitle", "href", "type"],
          searchOptions: { fuzzy: 0.2, prefix: true, boost: { title: 3 } },
        });
        mini.addAll(recs);
        indexRef.current = mini;
        setLoadState("ready");
      })
      .catch(() => setLoadState("error"));
  }, [loadState]);

  // Default (empty-query) list: findings + top-level pages only, not all 1,549.
  const defaults = useCallback((): Rec[] => {
    const all = Array.from(recordsRef.current.values());
    return all.filter((r) => r.type === "page" || r.type === "finding");
  }, []);

  // loadState is a dependency: the records are lazy-fetched AFTER the palette
  // opens, so this must re-run when they arrive (idle->loading->ready) or an
  // empty query renders defaults() against an empty map -> a spurious "No results".
  useEffect(() => {
    if (!query.trim()) {
      setResults(open ? defaults() : []);
      return;
    }
    if (!indexRef.current) return;
    const hits = indexRef.current.search(query, { fuzzy: 0.2, prefix: true, boost: { title: 3 } });
    const recs = hits
      .slice(0, 30)
      .map((h) => recordsRef.current.get(String(h.id)))
      .filter((r): r is Rec => Boolean(r));
    setResults(recs);
  }, [query, open, defaults, loadState]);

  const openPalette = useCallback(() => {
    setOpen(true);
    load();
  }, [load]);

  useEffect(() => {
    const onKeydown = (e: KeyboardEvent) => {
      const isMod = e.metaKey || e.ctrlKey;
      if (isMod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => {
          const next = !v;
          if (next) load();
          return next;
        });
        return;
      }
      if (e.key === "/") {
        const el = document.activeElement;
        const typing =
          el &&
          (el.tagName === "INPUT" ||
            el.tagName === "TEXTAREA" ||
            el.tagName === "SELECT" ||
            (el as HTMLElement).isContentEditable);
        if (typing || open) return;
        e.preventDefault();
        openPalette();
      }
    };
    window.addEventListener("keydown", onKeydown);
    return () => window.removeEventListener("keydown", onKeydown);
  }, [open, load, openPalette]);

  // Let the small nav trigger button (rendered separately, outside this
  // client boundary) open the palette without a shared store.
  useEffect(() => {
    const onOpenEvent = () => openPalette();
    window.addEventListener("cv-open-palette", onOpenEvent);
    return () => window.removeEventListener("cv-open-palette", onOpenEvent);
  }, [openPalette]);

  const select = (r: Rec) => {
    setOpen(false);
    setQuery("");
    router.push(r.href);
  };

  const grouped = GROUP_ORDER.map((g) => ({
    ...g,
    items: results.filter((r) => r.type === g.type),
  })).filter((g) => g.items.length > 0);

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label="Search CourtVision"
      shouldFilter={false}
      style={dialogS}
      overlayClassName="cv-cmdk-overlay"
      contentClassName="cv-cmdk-content"
    >
      <Command.Input
        value={query}
        onValueChange={setQuery}
        placeholder="Search players, modules, findings..."
        aria-label="Search CourtVision"
        style={inputS}
      />
      <Command.List style={listS}>
        {loadState === "error" ? (
          <Command.Empty style={emptyS}>Search unavailable.</Command.Empty>
        ) : loadState === "loading" ? (
          <Command.Loading style={emptyS}>Loading...</Command.Loading>
        ) : results.length === 0 ? (
          <Command.Empty style={emptyS}>No results.</Command.Empty>
        ) : (
          grouped.map((g): ReactNode => (
            <Command.Group key={g.type} heading={g.heading} style={groupS}>
              {g.items.map((r) => (
                <Command.Item
                  key={r.id}
                  value={r.id}
                  onSelect={() => select(r)}
                  style={itemS}
                >
                  <span className="serif" style={{ color: "var(--ink)" }}>{r.title}</span>
                  <span className="mono" style={typeTagS}>{r.type}</span>
                  <span style={{ color: "var(--ink-3)", fontSize: 12 }}>{r.subtitle}</span>
                </Command.Item>
              ))}
            </Command.Group>
          ))
        )}
      </Command.List>
    </Command.Dialog>
  );
}

const dialogS: CSSProperties = {
  position: "fixed", top: "12%", left: "50%", transform: "translateX(-50%)",
  width: "min(560px, 92vw)", maxHeight: "70vh",
  background: "var(--paper-raised)", border: "1px solid var(--rule)",
  borderRadius: "var(--radius-card)", boxShadow: "var(--shadow-raise)",
  overflow: "hidden", display: "flex", flexDirection: "column", zIndex: 100,
};
const inputS: CSSProperties = {
  width: "100%", boxSizing: "border-box", border: 0, borderBottom: "1px solid var(--rule)",
  background: "transparent", color: "var(--ink)", fontSize: 16, padding: "16px 18px", outline: "none",
};
const listS: CSSProperties = { overflowY: "auto", padding: "6px 0", flex: 1 };
const groupS: CSSProperties = { padding: "8px 10px 2px", color: "var(--ink-3)", fontSize: 11 };
const itemS: CSSProperties = {
  display: "flex", alignItems: "center", gap: 10, padding: "8px 16px", cursor: "pointer", fontSize: 14,
};
const typeTagS: CSSProperties = {
  color: "var(--ink-3)", fontSize: 10, border: "1px solid var(--rule)",
  borderRadius: "var(--radius-chip, 4px)", padding: "1px 6px",
};
const emptyS: CSSProperties = { padding: "24px 18px", color: "var(--ink-3)", fontSize: 14 };

export default CommandPalette;

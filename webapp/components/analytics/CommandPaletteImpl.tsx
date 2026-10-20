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
const EXTRA_DESTINATIONS: Rec[] = [
  { id: "page-measurement-lab", title: "Measurement lab", subtitle: "Inspect published measurements and source context", href: "/analytics/lab", type: "page", keywords: ["lab", "measurement", "tables"] },
  { id: "page-compare-profiles", title: "Compare profiles", subtitle: "Compare published Atlas profiles", href: "/analytics/compare", type: "page", keywords: ["compare", "profiles", "atlas"] },
  { id: "page-evidence-platform", title: "Evidence & Platform", subtitle: "Browse source-linked visual evidence", href: "/analytics/evidence", type: "page", keywords: ["evidence", "platform", "charts", "sources"] },
];
const SCOPES: Array<{ value: "all" | Rec["type"]; label: string }> = [
  { value: "all", label: "All" }, { value: "page", label: "Pages" }, { value: "entity", label: "Entities" }, { value: "module", label: "Modules" }, { value: "finding", label: "Findings" },
];

type LoadState = "idle" | "loading" | "ready" | "error";

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [scope, setScope] = useState<"all" | Rec["type"]>("all");
  const recordsRef = useRef<Map<string, Rec>>(new Map());
  const indexRef = useRef<MiniSearch<Rec> | null>(null);
  const [results, setResults] = useState<Rec[]>([]);

  const load = useCallback((retry = false) => {
    if (loadState === "loading" || (!retry && loadState !== "idle")) return;
    setLoadState("loading");
    fetch(`${BASE_PATH}/analytics/search-index.json`)
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((data: { records: Rec[] }) => {
        const recs = [...(data.records || []), ...EXTRA_DESTINATIONS];
        recordsRef.current.clear();
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
  const inScope = useCallback((records: Rec[]): Rec[] => (
    scope === "all" ? records : records.filter((record) => record.type === scope)
  ), [scope]);

  const defaults = useCallback((): Rec[] => {
    const all = Array.from(recordsRef.current.values());
    return inScope(all.filter((r) => r.type === "page" || r.type === "finding"));
  }, [inScope]);

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
    const recs = inScope(hits
      .map((h) => recordsRef.current.get(String(h.id)))
      .filter((r): r is Rec => Boolean(r)))
      .slice(0, 30);
    setResults(recs);
  }, [query, open, defaults, inScope, loadState]);

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
      <div aria-label="Search scope" style={scopeS}>
        {SCOPES.map((item) => <button key={item.value} type="button" onClick={() => setScope(item.value)} aria-pressed={scope === item.value} style={{ ...scopeButtonS, ...(scope === item.value ? scopeActiveS : null) }}>{item.label}</button>)}
      </div>
      <Command.List style={listS}>
        {loadState === "error" ? (
          <Command.Empty style={emptyS}>Search unavailable. <button type="button" onClick={() => load(true)} style={retryS}>Retry</button></Command.Empty>
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
const scopeS: CSSProperties = { display: "flex", gap: 6, overflowX: "auto", padding: "9px 12px", borderBottom: "1px solid var(--rule)" };
const scopeButtonS: CSSProperties = { border: "1px solid var(--rule)", borderRadius: "var(--radius-chip, 4px)", background: "transparent", color: "var(--ink-3)", cursor: "pointer", fontSize: 11, padding: "5px 8px", whiteSpace: "nowrap" };
const scopeActiveS: CSSProperties = { background: "var(--paper-tint)", color: "var(--ink)", border: "1px solid var(--rule-strong)" };
const groupS: CSSProperties = { padding: "8px 10px 2px", color: "var(--ink-3)", fontSize: 11 };
const itemS: CSSProperties = {
  display: "flex", alignItems: "center", gap: 10, padding: "8px 16px", cursor: "pointer", fontSize: 14,
};
const typeTagS: CSSProperties = {
  color: "var(--ink-3)", fontSize: 10, border: "1px solid var(--rule)",
  borderRadius: "var(--radius-chip, 4px)", padding: "1px 6px",
};
const emptyS: CSSProperties = { padding: "24px 18px", color: "var(--ink-3)", fontSize: 14 };
const retryS: CSSProperties = { border: 0, background: "transparent", color: "var(--accent)", cursor: "pointer", font: "inherit", fontWeight: 600, padding: 0, textDecoration: "underline" };

export default CommandPalette;

"use client";
// components/shell/CrossGroupNav.tsx -- one root layout now hosts both route groups, so a
// <Link> from a terminal page to an /analytics page would be a soft navigation that keeps
// globals.css loaded next to analytics.css (both define --accent and body rules on :root).
// A capture listener on window runs before React's document-level Link handler; stopping
// propagation leaves the browser's default full page load in place for cross-group clicks.
// ponytail: router.push() calls (the CommandPalette) still soft-navigate; retire this when
// the two token sets are merged into one stylesheet.
import { useEffect } from "react";
import { normalizePath } from "./nav";

const group = (path: string) => (/^\/analytics(\/|$)/.test(normalizePath(path)) ? "analytics" : "site");

export function CrossGroupNav() {
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as Element | null)?.closest?.("a[href]") as HTMLAnchorElement | null;
      if (!a || a.target === "_blank" || a.origin !== window.location.origin) return;
      if (group(a.pathname) !== group(window.location.pathname)) e.stopPropagation();
    };
    window.addEventListener("click", onClick, true);
    return () => window.removeEventListener("click", onClick, true);
  }, []);
  return null;
}

export default CrossGroupNav;

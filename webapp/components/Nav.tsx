"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

// Nav links -- the product areas of the cohesive product (FD: ONE nav).
//   Home          /              -- the cohesive landing.
//   Games         /games         -- slate-of-cards funnel (also /p6 dashboard).
//   Bets          /bets          -- Best Bets board: Live/Pregame/Done sections.
//   Models        /models        -- AI improvement: ratchet/Brier/ECE/BSS deltas.
//   How it works  /how-it-works  -- DATA->...->VALIDATION funnel explainer.
//   System        /system        -- parity / self-improve / honest findings.
//
// Analytics / AI-Assistant / Settings: DO NOT exist; never add them.
// Progress: replaced by Models (/models) which is the honest "getting better" view.
// FIVE primary destinations on the bar; everything else lives in "More".
// (User 2026-07-15: bar was overloaded -- keep the top simple.)
const PRIMARY_LINKS = [
  { href: "/today",         label: "Today",  short: "Today", exact: false, also: [] as string[] },
  { href: "/live",          label: "Live",   short: "Live",  exact: false, also: [] as string[] },
  { href: "/games",         label: "Games",  short: "Games", exact: false, also: ["/p6"] },
  { href: "/paper-trading", label: "Paper",  short: "Paper", exact: false, also: ["/paper", "/records"] },
  { href: "/bets",          label: "Bets",   short: "Bets",  exact: false, also: [] as string[] },
] as const;

const MORE_LINKS = [
  { href: "/models",       label: "Models",       short: "Models", exact: false, also: ["/progress"] },
  { href: "/records",      label: "Records",      short: "Rec",    exact: false, also: [] as string[] },
  { href: "/system",       label: "System",       short: "System", exact: false, also: [] as string[] },
  { href: "/how-it-works", label: "How it works", short: "How",    exact: false, also: [] as string[] },
] as const;

const NAV_LINKS = [
  { href: "/", label: "Home", short: "Home", exact: true, also: [] as string[] },
  ...PRIMARY_LINKS,
  ...MORE_LINKS,
] as const;

// Theme toggle -- no next-themes needed; CSS class on <html> + localStorage.
function ThemeToggle() {
  const [dark, setDark] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem("cv-theme");
    const isDark = stored !== "light";
    setDark(isDark);
    document.documentElement.classList.toggle("dark", isDark);
  }, []);

  const toggle = useCallback(() => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("cv-theme", next ? "dark" : "light");
  }, [dark]);

  return (
    <button
      onClick={toggle}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      className={cn(
        "flex h-8 w-8 items-center justify-center rounded-md",
        "text-slate-400 transition-colors hover:bg-accent hover:text-foreground",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      )}
    >
      {/* Sun / Moon -- pure ASCII-safe SVG paths, no unicode glyphs */}
      {dark ? (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4" />
          <line x1="12" y1="2"  x2="12" y2="4"  />
          <line x1="12" y1="20" x2="12" y2="22" />
          <line x1="4.22" y1="4.22"   x2="5.64"  y2="5.64"  />
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
          <line x1="2"  y1="12" x2="4"  y2="12" />
          <line x1="20" y1="12" x2="22" y2="12" />
          <line x1="4.22"  y1="19.78" x2="5.64"  y2="18.36" />
          <line x1="18.36" y1="5.64"  x2="19.78" y2="4.22"  />
        </svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      )}
    </button>
  );
}

// MobileMenuButton -- hamburger toggle for narrow screens.
// Accepts a forwarded ref so the Nav can return focus here on Escape close.
const MobileMenuButton = React.forwardRef<
  HTMLButtonElement,
  { open: boolean; onToggle: () => void }
>(function MobileMenuButton({ open, onToggle }, ref) {
  return (
    <button
      ref={ref}
      onClick={onToggle}
      aria-label={open ? "Close menu" : "Open menu"}
      aria-expanded={open}
      className={cn(
        "flex h-8 w-8 items-center justify-center rounded-md sm:hidden",
        "text-slate-400 transition-colors hover:bg-accent hover:text-foreground",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      )}
    >
      {open ? (
        // X icon
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <line x1="18" y1="6" x2="6"  y2="18" />
          <line x1="6"  y1="6" x2="18" y2="18" />
        </svg>
      ) : (
        // Hamburger
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <line x1="3" y1="6"  x2="21" y2="6"  />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      )}
    </button>
  );
});

// NavLink -- single nav item with active-route highlighting.
function NavLink({
  href,
  label,
  short,
  active,
}: {
  href: string;
  label: string;
  short: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "border-b-2 px-3 py-1.5 text-sm font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        active
          ? "border-primary text-foreground"
          : "border-transparent text-muted-foreground hover:text-foreground",
      )}
    >
      {/* Show short label on md, full on lg */}
      <span className="hidden lg:inline">{label}</span>
      <span className="lg:hidden">{short}</span>
    </Link>
  );
}

// Nav -- the persistent top navigation bar.
// Renders: logo | paper-mode badge | nav links | theme toggle | (mobile hamburger).
export function Nav() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  // Ref to the hamburger button so we can return focus on Escape-close.
  const menuBtnRef = useRef<HTMLButtonElement>(null);

  // Close mobile menu on route change.
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  // Escape key closes the mobile menu and returns focus to the hamburger.
  useEffect(() => {
    if (!mobileOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMobileOpen(false);
        menuBtnRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [mobileOpen]);

  // Determine active link (match on base path, not hash).
  // Exact links (/p6, /p6#paper) match only when pathname === "/p6".
  // Prefix links (/p6/history, /p6/system) match on startsWith.
  const basePath = pathname.split("#")[0];
  const activeHref =
    NAV_LINKS.find((l) => {
      const linkBase = l.href.split("#")[0];
      const bases = [linkBase, ...(l.also ?? [])];
      if (l.exact) return basePath === linkBase;
      return bases.some(
        (b) => basePath === b || basePath.startsWith(b + "/"),
      );
    })?.href ?? null;

  return (
    <header
      role="banner"
      className={cn(
        "sticky top-0 z-40 w-full",
        "border-b border-border bg-surface-1/90 backdrop-blur-sm",
      )}
    >
      <div className="mx-auto flex h-12 max-w-7xl items-center gap-3 px-4 sm:px-6">
        {/* Logo + wordmark */}
        <Link
          href="/"
          className={cn(
            "flex shrink-0 items-center gap-2 rounded-md",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          )}
          aria-label="CourtVision home"
          aria-current={basePath === "/" ? "page" : undefined}
        >
          <span className="text-sm font-semibold tracking-tight text-foreground">
            Court<span className="text-primary">Vision</span>
          </span>
          <span className="hidden font-mono text-[10px] uppercase tracking-widest text-muted-foreground sm:inline">
            multi-sport
          </span>
        </Link>

        {/* PAPER MODE badge -- always visible, honesty rail (FD-060) */}
        <span
          aria-label="Paper mode -- no real money"
          className={cn(
            "shrink-0 border px-1.5 py-0.5",
            "border-warning font-mono text-[10px] uppercase tracking-wider text-warning",
          )}
        >
          paper
        </span>

        {/* Desktop nav links */}
        <nav
          role="navigation"
          aria-label="Main"
          className="hidden flex-1 items-center gap-1 sm:flex"
        >
          {PRIMARY_LINKS.map((l) => (
            <NavLink
              key={l.href}
              href={l.href}
              label={l.label}
              short={l.short}
              active={l.href === activeHref}
            />
          ))}
          {/* Everything secondary collapses behind a native details menu. */}
          <details className="group relative" data-testid="nav-more">
            <summary
              className={cn(
                "cursor-pointer list-none border-b-2 px-3 py-1.5 text-sm font-medium",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                MORE_LINKS.some((l) => l.href === activeHref)
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              More
            </summary>
            <div className="absolute left-0 top-full z-50 mt-1 flex min-w-40 flex-col border border-border bg-card py-1">
              {MORE_LINKS.map((l) => (
                <Link
                  key={l.href}
                  href={l.href}
                  onClick={(e) => e.currentTarget.closest("details")?.removeAttribute("open")}
                  className={cn(
                    "px-3 py-2 text-sm",
                    l.href === activeHref
                      ? "text-foreground"
                      : "text-muted-foreground hover:bg-accent hover:text-foreground",
                  )}
                >
                  {l.label}
                </Link>
              ))}
            </div>
          </details>
        </nav>

        {/* Spacer on mobile so toggles push to the right */}
        <div className="flex-1 sm:hidden" />

        {/* Product-status badges moved OFF the bar (user: keep the top simple);
            the Home status row still shows the full set. */}

        {/* Theme toggle */}
        <ThemeToggle />

        {/* Mobile menu button -- ref used for focus-return on Escape close */}
        <MobileMenuButton
          ref={menuBtnRef}
          open={mobileOpen}
          onToggle={() => setMobileOpen((v) => !v)}
        />
      </div>

      {/* Mobile dropdown menu */}
      {mobileOpen && (
        <nav
          role="navigation"
          aria-label="Mobile main"
          className={cn(
            "border-t border-border bg-surface-1 px-4 pb-3 pt-2 sm:hidden",
          )}
        >
          <ul className="flex flex-col gap-1" role="list">
            {NAV_LINKS.map((l) => (
              <li key={l.href}>
                <Link
                  href={l.href}
                  aria-current={l.href === activeHref ? "page" : undefined}
                  className={cn(
                    "block border-l-2 px-3 py-2 text-sm font-medium transition-colors",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    l.href === activeHref
                      ? "border-primary bg-accent text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground",
                  )}
                >
                  {l.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </header>
  );
}

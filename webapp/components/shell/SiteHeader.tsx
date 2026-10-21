"use client";
// components/shell/SiteHeader.tsx -- the ONE site header: wordmark, the six-item nav
// (components/shell/nav.ts), search (opens the CommandPalette; "/" also opens it),
// Ask Scout, theme toggle. Narrow screens get a disclosure menu (aria-expanded,
// Escape closes and returns focus). Every target is at least 44 px. ASCII only.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { SITE_NAV, sectionFor } from "./nav";
import { applyTheme } from "./theme";
import s from "./shell.module.css";

function NavItems({ current, onNavigate }: { current: string | null; onNavigate?: () => void }) {
  return (
    <ul className={s.navList}>
      {SITE_NAV.map((item) => (
        <li key={item.href}>
          <Link
            href={item.href}
            prefetch={false}
            className={s.navLink}
            aria-current={current === item.href ? "page" : undefined}
            onClick={onNavigate}
          >
            {item.label}
          </Link>
        </li>
      ))}
    </ul>
  );
}

function ThemeToggle() {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    setDark(document.documentElement.getAttribute("data-theme") === "dark");
  }, []);
  return (
    <button
      type="button"
      className={s.tool}
      aria-pressed={dark}
      aria-label="Dark theme"
      onClick={() => {
        applyTheme(!dark);
        setDark(!dark);
      }}
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        {dark ? (
          <>
            <circle cx="12" cy="12" r="4" />
            <path strokeLinecap="round" d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1" />
          </>
        ) : (
          <path strokeLinecap="round" strokeLinejoin="round" d="M20 14.5A8 8 0 0 1 9.5 4a7 7 0 1 0 10.5 10.5z" />
        )}
      </svg>
    </button>
  );
}

export function SiteHeader() {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const pathname = usePathname();
  const current = sectionFor(pathname)?.href ?? null;
  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <header className={s.header}>
      <div className={s.row}>
        <Link href="/" prefetch={false} className={s.brand} aria-label="CourtVision home">
          CourtVision
        </Link>
        <nav aria-label="Main">
          <NavItems current={current} />
        </nav>
        <div className={s.tools}>
          <button
            type="button"
            className={s.tool}
            aria-label="Search the site (shortcut /)"
            onClick={() => window.dispatchEvent(new CustomEvent("cv-open-palette"))}
          >
            Search <span className={s.kbd} aria-hidden="true">/</span>
          </button>
          <Link href="/analytics/ask/" prefetch={false} className={`${s.tool} ${s.hideNarrow}`}>
            Ask Scout
          </Link>
          <ThemeToggle />
          <button
            ref={buttonRef}
            type="button"
            className={`${s.tool} ${s.menuButton}`}
            aria-expanded={open}
            aria-controls="site-menu"
            onClick={() => setOpen((o) => !o)}
          >
            Menu
          </button>
        </div>
      </div>
      {open && (
        <nav id="site-menu" aria-label="Main menu" className={s.mobileMenu}>
          <NavItems current={current} onNavigate={() => setOpen(false)} />
          <ul className={s.navList}>
            <li>
              <Link href="/analytics/ask/" prefetch={false} className={s.navLink} onClick={() => setOpen(false)}>
                Ask Scout
              </Link>
            </li>
          </ul>
        </nav>
      )}
    </header>
  );
}

export default SiteHeader;

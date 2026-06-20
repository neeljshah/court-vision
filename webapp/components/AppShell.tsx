"use client";

// AppShell -- wraps every page route with the persistent Nav and a shared
// page container. Renders the theme initializer script BEFORE paint to prevent
// a flash of wrong theme (FOWT). The script reads localStorage "cv-theme" and
// sets the "dark" class on <html> synchronously.
//
// This file is <= 300 LOC. Do not grow beyond that boundary.

import type { ReactNode } from "react";
import { Nav } from "./Nav";
import { OnboardingOverlay } from "./onboarding/OnboardingOverlay";

// SkipLink -- the first focusable element on the page. Hidden until focused,
// then visually appears top-left and jumps keyboard users past the Nav to the
// main content (#main-content). A11y baseline: bypass-blocks (WCAG 2.4.1).
function SkipLink() {
  return (
    <a
      href="#main-content"
      className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-foreground focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-background focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      Skip to main content
    </a>
  );
}

// ThemeScript -- inlined <script> that runs before React hydration to prevent
// the flash-of-wrong-theme. Must be a separate component so we can use
// dangerouslySetInnerHTML in the server layout.
// Exported for use in layout.tsx <head> (Server Component).
export const THEME_INIT_SCRIPT = `
(function(){
  try{
    var t=localStorage.getItem('cv-theme');
    if(t==='light'){document.documentElement.classList.remove('dark');}
    else{document.documentElement.classList.add('dark');}
  }catch(e){}
})();
`;

// AppShell -- client component that renders Nav + page content.
// The outer <div> provides vertical flex so the nav is sticky-top and the
// content area fills the remaining viewport height.
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <SkipLink />
      <Nav />
      <main id="main-content" tabIndex={-1} className="flex-1 focus:outline-none">
        {children}
      </main>
      {/* First-run "what is this & how to read it" overlay + persistent Help
          affordance. Dismissible, non-blocking, reuses the glossary copy. */}
      <OnboardingOverlay />
      <footer className="border-t border-border py-3 text-center font-mono text-[11px] text-muted-foreground">
        Calibrated decision-support only. Markets are efficient; no dollar edge
        claimed. CLV (better-number-than-close) is the only honest yardstick.
        vs-close UNPROVEN where no in-play prices are available. PAPER MODE
        only.
      </footer>
    </div>
  );
}

// app/(terminal)/layout.tsx -- the site group (everything outside /analytics): its
// stylesheet (globals.css + tailwind) and the shared shell. <html>/<body>, the theme
// init and the metadata live in the one root layout (app/layout.tsx).
import "../globals.css";

import type { ReactNode } from "react";
import { SiteHeader } from "@/components/shell/SiteHeader";
import { Breadcrumbs } from "@/components/shell/Breadcrumbs";
import { SiteFooter } from "@/components/shell/SiteFooter";
import { snapshotDates } from "@/components/shell/snapshot.server";
import { OnboardingOverlay } from "@/components/onboarding/OnboardingOverlay";
import s from "@/components/shell/shell.module.css";

export default function SiteGroupLayout({ children }: { children: ReactNode }) {
  return (
    <div className={s.terminalScope}>
      <div className="flex min-h-screen flex-col">
        <SiteHeader />
        <Breadcrumbs />
        <main id="main-content" tabIndex={-1} className="flex-1 focus:outline-none">
          {children}
        </main>
        {/* First-run "how to read this" overlay + Help affordance (dismissible). */}
        <OnboardingOverlay />
        <SiteFooter dates={snapshotDates()} />
      </div>
    </div>
  );
}

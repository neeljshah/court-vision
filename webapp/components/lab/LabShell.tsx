// components/lab/LabShell.tsx -- shared /lab sub-nav (counterfactual / microstructure).
// Server component: plain <Link>s, active state via pathname passed from the
// layout (usePathname needs "use client"; ponytail: keep this a server
// component and let each page mark its own tab active via URL match at render).

import Link from "next/link";

const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";

const TABS = [
  { href: "/lab/counterfactual", label: "Counterfactual" },
  { href: "/lab/microstructure", label: "Microstructure" },
];

export function LabShell({
  active,
  children,
}: {
  active: "counterfactual" | "microstructure" | null;
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto max-w-[1200px] px-4 py-8">
      <div className="mb-6">
        <p className="microlabel text-faint">Lab</p>
        <h1 className="text-xl font-semibold text-foreground">
          Instruments &amp; counterfactuals
        </h1>
        <p className="mt-1 max-w-[68ch] text-sm text-faint">
          Descriptive instruments and counterfactual replays. edge_claimed:false
          throughout -- these surfaces measure, they do not claim.
        </p>
      </div>
      <nav className="mb-6 flex gap-1 border-b border-border" aria-label="Lab sections">
        {TABS.map((tab) => {
          const isActive = tab.href.endsWith(active ?? "\0");
          return (
            <Link
              key={tab.href}
              href={`${BASE_PATH}${tab.href}`}
              className={
                "microlabel px-3 py-2 border-b-2 -mb-px " +
                (isActive
                  ? "border-primary text-foreground"
                  : "border-transparent text-faint hover:text-foreground")
              }
              aria-current={isActive ? "page" : undefined}
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>
      {children}
    </div>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/",           label: "Command Center",  icon: "⚡" },
  { href: "/edges",      label: "Edge Scanner",    icon: "📡" },
  { href: "/positions",  label: "Positions",       icon: "💼" },
  { href: "/analytics",  label: "Analytics Lab",   icon: "📊" },
  { href: "/chat",       label: "AI Research",     icon: "🤖" },
  { href: "/system",     label: "System Status",   icon: "🛠" },
];

export function Sidebar() {
  const path = usePathname();

  return (
    <aside className="w-56 shrink-0 flex flex-col border-r border-[#1e2028] bg-[#0d0f14] h-screen sticky top-0">
      <div className="px-4 py-5 border-b border-[#1e2028]">
        <span className="text-[#f97316] font-mono font-bold text-lg tracking-tight">
          CourtVision
        </span>
        <div className="text-[10px] text-[#6b7280] mt-0.5 font-mono">QUANT TERMINAL</div>
      </div>

      <nav className="flex-1 py-3">
        {NAV.map(({ href, label, icon }) => {
          const active = href === "/" ? path === "/" : path.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-4 py-2.5 text-sm transition-colors",
                active
                  ? "bg-[#1e2028] text-[#f97316] font-medium"
                  : "text-[#9ca3af] hover:text-[#e5e7eb] hover:bg-[#12141a]"
              )}
            >
              <span className="text-base">{icon}</span>
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="px-4 py-3 border-t border-[#1e2028] text-[10px] text-[#4b5563] font-mono">
        NBA AI v2.0 · 75 models
      </div>
    </aside>
  );
}

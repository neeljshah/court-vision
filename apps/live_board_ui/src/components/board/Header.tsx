/** Sticky top header with live-dot branding and a right-side slot for ThemeToggle. */
import React from "react";
import { cn } from "@/lib/utils";

interface HeaderProps {
  children?: React.ReactNode;
}

export function Header({ children }: HeaderProps) {
  return (
    <header className="sticky top-0 z-20 bg-bg/90 backdrop-blur border-b border-line">
      <div className="max-w-5xl mx-auto px-3 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <span
            aria-hidden="true"
            className={cn(
              "inline-block w-2 h-2 rounded-full bg-live animate-live-pulse flex-shrink-0"
            )}
          />
          <div className="min-w-0">
            <h1 className="text-lg font-semibold text-txt leading-none">
              Live Board
            </h1>
            <p className="text-xs text-muted leading-snug mt-0.5 hidden sm:block truncate">
              Calibrated predictions and live market context across MLB, Soccer and Tennis.
            </p>
          </div>
        </div>
        {children != null && (
          <div className="flex items-center flex-shrink-0 ml-3">
            {children}
          </div>
        )}
      </div>
    </header>
  );
}

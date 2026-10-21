"use client";
// CommandPalette -- lazy shell. The analytics root layout renders this on every
// page; the real palette (cmdk + MiniSearch + the dialog) lives in
// CommandPaletteImpl.tsx and is dynamic-imported on the first Cmd/Ctrl+K, "/"
// or Search-button press. Until then nothing but this listener ships, which
// keeps ~60 KB raw (~20 KB gzip) of JS off every analytics page load.
//
// Hand-over contract: the first trigger mounts the impl with initialOpen so the
// press that loaded it also opens it; from then on the impl owns its own
// listeners and this shell stays inert.
import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";

const CommandPaletteImpl = dynamic(
  () => import("./CommandPaletteImpl").then((m) => m.CommandPalette),
  { ssr: false },
);

function isTypingTarget(el: Element | null): boolean {
  if (!el) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (el as HTMLElement).isContentEditable;
}

export function CommandPalette() {
  const [armed, setArmed] = useState(false);
  const openerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (armed) return;
    const arm = () => {
      // The press that loads the impl also opens it: remember what had focus so Escape
      // can hand it back (the impl records every later opener itself).
      const el = document.activeElement;
      openerRef.current = el instanceof HTMLElement && el !== document.body ? el : null;
      setArmed(true);
    };
    const onKeydown = (e: KeyboardEvent) => {
      const isMod = e.metaKey || e.ctrlKey;
      if (isMod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        arm();
        return;
      }
      if (e.key === "/" && !isMod && !e.altKey && !isTypingTarget(document.activeElement)) {
        e.preventDefault();
        arm();
      }
    };
    window.addEventListener("keydown", onKeydown);
    window.addEventListener("cv-open-palette", arm);
    return () => {
      window.removeEventListener("keydown", onKeydown);
      window.removeEventListener("cv-open-palette", arm);
    };
  }, [armed]);

  return armed ? <CommandPaletteImpl initialOpen returnFocusTo={openerRef.current} /> : null;
}

export default CommandPalette;

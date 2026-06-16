/** useTheme -- manages light/dark/system theme, persists to localStorage, applies classes to <html>. */
import { useState, useEffect, useCallback } from "react";

type Theme = "light" | "dark" | "system";
type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "lb-theme";

function getSystemPreference(): ResolvedTheme {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function readStoredTheme(): Theme {
  if (typeof window === "undefined") return "system";
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark" || stored === "system") return stored;
  } catch {
    // localStorage unavailable
  }
  return "system";
}

function resolveTheme(theme: Theme): ResolvedTheme {
  if (theme === "system") return getSystemPreference();
  return theme;
}

function applyThemeClasses(resolved: ResolvedTheme): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  if (resolved === "dark") {
    root.classList.add("dark");
    root.classList.remove("light");
  } else {
    root.classList.add("light");
    root.classList.remove("dark");
  }
}

export interface UseThemeReturn {
  theme: Theme;
  setTheme: (t: Theme) => void;
  resolved: ResolvedTheme;
}

export function useTheme(): UseThemeReturn {
  const [theme, setThemeState] = useState<Theme>(() => readStoredTheme());
  const [resolved, setResolved] = useState<ResolvedTheme>(() =>
    resolveTheme(readStoredTheme())
  );

  const applyAndSync = useCallback((t: Theme) => {
    const r = resolveTheme(t);
    setResolved(r);
    applyThemeClasses(r);
  }, []);

  // On mount, apply stored theme immediately to avoid flash
  useEffect(() => {
    applyAndSync(theme);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Watch system preference changes when theme === 'system'
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (theme !== "system") return;

    const mq = window.matchMedia("(prefers-color-scheme: dark)");

    const handler = (e: MediaQueryListEvent) => {
      const r: ResolvedTheme = e.matches ? "dark" : "light";
      setResolved(r);
      applyThemeClasses(r);
    };

    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [theme]);

  const setTheme = useCallback(
    (t: Theme) => {
      setThemeState(t);
      try {
        if (typeof window !== "undefined") {
          localStorage.setItem(STORAGE_KEY, t);
        }
      } catch {
        // localStorage unavailable
      }
      applyAndSync(t);
    },
    [applyAndSync]
  );

  return { theme, setTheme, resolved };
}

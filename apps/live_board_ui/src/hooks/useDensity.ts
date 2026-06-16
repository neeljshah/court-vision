/** useDensity -- manages comfortable/compact row density, persists to localStorage "lb-density". */
import { useState, useCallback } from "react";

export type Density = "comfortable" | "compact";

const STORAGE_KEY = "lb-density";
const DEFAULT: Density = "comfortable";

function readStoredDensity(): Density {
  if (typeof window === "undefined") return DEFAULT;
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "comfortable" || stored === "compact") return stored;
  } catch {
    // localStorage unavailable
  }
  return DEFAULT;
}

export interface UseDensityReturn {
  density: Density;
  setDensity: (d: Density) => void;
  toggle: () => void;
}

export function useDensity(): UseDensityReturn {
  const [density, setDensityState] = useState<Density>(() => readStoredDensity());

  const setDensity = useCallback((d: Density) => {
    setDensityState(d);
    try {
      if (typeof window !== "undefined") {
        localStorage.setItem(STORAGE_KEY, d);
      }
    } catch {
      // localStorage unavailable
    }
  }, []);

  const toggle = useCallback(() => {
    setDensityState((prev) => {
      const next: Density = prev === "comfortable" ? "compact" : "comfortable";
      try {
        if (typeof window !== "undefined") {
          localStorage.setItem(STORAGE_KEY, next);
        }
      } catch {
        // localStorage unavailable
      }
      return next;
    });
  }, []);

  return { density, setDensity, toggle };
}

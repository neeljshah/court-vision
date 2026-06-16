/**
 * renderHook tests for useTheme: default theme, persistence to localStorage,
 * resolved value derivation, and documentElement class application.
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { useTheme } from "@/hooks/useTheme";

const STORAGE_KEY = "lb-theme";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getRootClasses(): DOMTokenList {
  return document.documentElement.classList;
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  // Start every test from a clean state.
  localStorage.clear();
  document.documentElement.classList.remove("dark", "light");
});

afterEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark", "light");
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useTheme", () => {
  it("returns the correct shape { theme, setTheme, resolved }", () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current).toHaveProperty("theme");
    expect(result.current).toHaveProperty("setTheme");
    expect(result.current).toHaveProperty("resolved");
    expect(typeof result.current.setTheme).toBe("function");
  });

  it("defaults to theme='system' when nothing is persisted in localStorage", () => {
    // localStorage is empty (cleared in beforeEach).
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("system");
  });

  it("resolved defaults to 'light' when matchMedia returns matches:false (polyfill)", () => {
    // The setup.ts polyfill returns matches:false, so system resolves to 'light'.
    const { result } = renderHook(() => useTheme());
    expect(result.current.resolved).toBe("light");
  });

  it("setTheme('dark') persists 'dark' to localStorage under key 'lb-theme'", () => {
    const { result } = renderHook(() => useTheme());

    act(() => {
      result.current.setTheme("dark");
    });

    expect(localStorage.getItem(STORAGE_KEY)).toBe("dark");
  });

  it("setTheme('dark') sets resolved to 'dark'", () => {
    const { result } = renderHook(() => useTheme());

    act(() => {
      result.current.setTheme("dark");
    });

    expect(result.current.resolved).toBe("dark");
  });

  it("setTheme('dark') adds the 'dark' class to documentElement", () => {
    const { result } = renderHook(() => useTheme());

    act(() => {
      result.current.setTheme("dark");
    });

    expect(getRootClasses().contains("dark")).toBe(true);
  });

  it("setTheme('dark') removes the 'light' class from documentElement", () => {
    // Pre-seed the light class to confirm it gets stripped.
    document.documentElement.classList.add("light");

    const { result } = renderHook(() => useTheme());

    act(() => {
      result.current.setTheme("dark");
    });

    expect(getRootClasses().contains("light")).toBe(false);
  });

  it("setTheme('light') persists 'light' to localStorage", () => {
    const { result } = renderHook(() => useTheme());

    act(() => {
      result.current.setTheme("light");
    });

    expect(localStorage.getItem(STORAGE_KEY)).toBe("light");
  });

  it("setTheme('light') sets resolved to 'light'", () => {
    const { result } = renderHook(() => useTheme());

    act(() => {
      result.current.setTheme("light");
    });

    expect(result.current.resolved).toBe("light");
  });

  it("setTheme('light') adds the 'light' class and removes 'dark' from documentElement", () => {
    // Pre-seed dark so we confirm it's removed.
    document.documentElement.classList.add("dark");

    const { result } = renderHook(() => useTheme());

    act(() => {
      result.current.setTheme("light");
    });

    expect(getRootClasses().contains("light")).toBe(true);
    expect(getRootClasses().contains("dark")).toBe(false);
  });

  it("setTheme('dark') then setTheme('light') leaves only the 'light' class", () => {
    const { result } = renderHook(() => useTheme());

    act(() => {
      result.current.setTheme("dark");
    });
    act(() => {
      result.current.setTheme("light");
    });

    expect(getRootClasses().contains("light")).toBe(true);
    expect(getRootClasses().contains("dark")).toBe(false);
    expect(result.current.resolved).toBe("light");
    expect(result.current.theme).toBe("light");
  });

  it("setTheme('system') updates theme state to 'system'", () => {
    const { result } = renderHook(() => useTheme());

    // First set to dark, then back to system.
    act(() => {
      result.current.setTheme("dark");
    });
    act(() => {
      result.current.setTheme("system");
    });

    expect(result.current.theme).toBe("system");
    // Polyfill returns matches:false, so system resolves to 'light'.
    expect(result.current.resolved).toBe("light");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("system");
  });

  it("reads a pre-existing 'dark' value from localStorage on mount", () => {
    localStorage.setItem(STORAGE_KEY, "dark");

    const { result } = renderHook(() => useTheme());

    expect(result.current.theme).toBe("dark");
    expect(result.current.resolved).toBe("dark");
  });

  it("reads a pre-existing 'light' value from localStorage on mount", () => {
    localStorage.setItem(STORAGE_KEY, "light");

    const { result } = renderHook(() => useTheme());

    expect(result.current.theme).toBe("light");
    expect(result.current.resolved).toBe("light");
  });
});

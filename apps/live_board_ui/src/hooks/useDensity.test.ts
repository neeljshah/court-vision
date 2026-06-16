/** useDensity hook tests -- default, toggle, setDensity, and localStorage persistence. */
import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { useDensity } from "@/hooks/useDensity";

const STORAGE_KEY = "lb-density";

beforeEach(() => {
  localStorage.clear();
});

describe("useDensity", () => {
  it("defaults to comfortable when nothing is persisted", () => {
    const { result } = renderHook(() => useDensity());
    expect(result.current.density).toBe("comfortable");
  });

  it("toggle() flips comfortable -> compact and persists to localStorage", () => {
    const { result } = renderHook(() => useDensity());

    act(() => {
      result.current.toggle();
    });

    expect(result.current.density).toBe("compact");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("compact");
  });

  it("toggle() flips compact -> comfortable and persists to localStorage", () => {
    const { result } = renderHook(() => useDensity());

    act(() => {
      result.current.toggle();
    });
    act(() => {
      result.current.toggle();
    });

    expect(result.current.density).toBe("comfortable");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("comfortable");
  });

  it("setDensity('compact') sets density and persists to localStorage", () => {
    const { result } = renderHook(() => useDensity());

    act(() => {
      result.current.setDensity("compact");
    });

    expect(result.current.density).toBe("compact");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("compact");
  });

  it("a fresh renderHook reads the previously persisted value from localStorage", () => {
    // Persist a value via one hook instance.
    const { result: first } = renderHook(() => useDensity());

    act(() => {
      first.current.setDensity("compact");
    });

    expect(localStorage.getItem(STORAGE_KEY)).toBe("compact");

    // A brand-new hook instance should initialise from the persisted value.
    const { result: second } = renderHook(() => useDensity());
    expect(second.current.density).toBe("compact");
  });
});

import "@testing-library/jest-dom/vitest";

// jsdom does not implement window.matchMedia; polyfill so hooks that call
// window.matchMedia('(prefers-color-scheme: dark)') do not throw.
if (typeof window !== "undefined" && typeof window.matchMedia === "undefined") {
  window.matchMedia = function (query: string): MediaQueryList {
    return {
      matches: false,
      media: query,
      onchange: null,
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
      dispatchEvent() { return false; },
    } as unknown as MediaQueryList;
  };
}

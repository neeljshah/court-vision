import "@testing-library/jest-dom/vitest";
import { afterEach, beforeAll, afterAll } from "vitest";
import { cleanup } from "@testing-library/react";

// Unmount React trees between tests so renders don't leak into each other.
afterEach(() => {
  cleanup();
});

// Silence ONLY the benign "not wrapped in act(...)" warning. These panels fetch
// on mount and flush a state update after the test's assertion resolves (or the
// tree unmounts). The data IS asserted via `await waitFor`, so the update is
// already covered -- the warning is noise, not a real un-awaited update. We keep
// EVERY other console.error loud so a genuine React error still surfaces (we
// swallow the one act-environment message and nothing else).
const ACT_WARNING = "not wrapped in act(";
let originalError: typeof console.error;

beforeAll(() => {
  originalError = console.error;
  console.error = (...args: unknown[]) => {
    const first = args[0];
    if (typeof first === "string" && first.includes(ACT_WARNING)) return;
    originalError(...args);
  };
});

afterAll(() => {
  console.error = originalError;
});

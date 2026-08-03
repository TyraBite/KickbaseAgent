import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createDebouncedFunction } from "./useDebouncedCallback";

describe("createDebouncedFunction", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("does not call the function before the delay has elapsed", () => {
    const fn = vi.fn();
    const debounced = createDebouncedFunction(fn, 800);
    debounced("a");
    vi.advanceTimersByTime(799);
    expect(fn).not.toHaveBeenCalled();
  });

  it("calls the function once the delay has elapsed", () => {
    const fn = vi.fn();
    const debounced = createDebouncedFunction(fn, 800);
    debounced("a");
    vi.advanceTimersByTime(800);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith("a");
  });

  it("resets the timer on repeated calls and only fires once with the last arguments", () => {
    const fn = vi.fn();
    const debounced = createDebouncedFunction(fn, 800);
    debounced("first");
    vi.advanceTimersByTime(500);
    debounced("second");
    vi.advanceTimersByTime(500);
    expect(fn).not.toHaveBeenCalled();
    vi.advanceTimersByTime(300);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith("second");
  });

  it("cancel() prevents a pending call from firing", () => {
    const fn = vi.fn();
    const debounced = createDebouncedFunction(fn, 800);
    debounced("a");
    debounced.cancel();
    vi.advanceTimersByTime(1000);
    expect(fn).not.toHaveBeenCalled();
  });
});

import { describe, expect, it } from "vitest";
import {
  URGENT_THRESHOLD_SECONDS,
  WARNING_THRESHOLD_SECONDS,
  computeTimerState,
  createExpiryGuard,
  isWarning,
  remainingSeconds,
} from "./exam-timer";

const now = new Date("2026-08-18T10:00:00.000Z").getTime();
const inSeconds = (secs: number) => new Date(now + secs * 1000).toISOString();

describe("remainingSeconds", () => {
  it("derives remaining whole seconds from endsAt (Req 18.1)", () => {
    expect(remainingSeconds(inSeconds(90), now)).toBe(90);
  });

  it("clamps to zero once the end time has passed", () => {
    expect(remainingSeconds(inSeconds(-30), now)).toBe(0);
  });

  it("returns zero when no end time is set", () => {
    expect(remainingSeconds(undefined, now)).toBe(0);
  });
});

describe("warning threshold crossing (Req 18.3)", () => {
  it("stays normal at or above the 10-minute threshold", () => {
    expect(isWarning(WARNING_THRESHOLD_SECONDS + 1)).toBe(false);
    expect(computeTimerState(inSeconds(WARNING_THRESHOLD_SECONDS + 1), now).warning).toBe(false);
  });

  it("enters warning state at the threshold", () => {
    expect(isWarning(WARNING_THRESHOLD_SECONDS)).toBe(true);
    expect(computeTimerState(inSeconds(WARNING_THRESHOLD_SECONDS), now).warning).toBe(true);
  });

  it("marks urgency inside the final minute", () => {
    const state = computeTimerState(inSeconds(URGENT_THRESHOLD_SECONDS - 1), now);
    expect(state.warning).toBe(true);
    expect(state.urgent).toBe(true);
  });

  it("is neither warning nor urgent once expired", () => {
    const state = computeTimerState(inSeconds(0), now);
    expect(state.remaining).toBe(0);
    expect(state.warning).toBe(false);
    expect(state.urgent).toBe(false);
  });
});

describe("expiry guard (Req 18.4)", () => {
  it("fires the expiry exactly once across repeated zero ticks", () => {
    const guard = createExpiryGuard();
    const endsAt = inSeconds(0);
    const fires = [
      guard.shouldExpire(0, endsAt),
      guard.shouldExpire(0, endsAt),
      guard.shouldExpire(0, endsAt),
    ];
    expect(fires).toEqual([true, false, false]);
  });

  it("does not fire while time remains", () => {
    const guard = createExpiryGuard();
    const endsAt = inSeconds(30);
    expect(guard.shouldExpire(30, endsAt)).toBe(false);
  });

  it("fires again after reset for a new session end time", () => {
    const guard = createExpiryGuard();
    expect(guard.shouldExpire(0, inSeconds(0))).toBe(true);
    guard.reset();
    expect(guard.shouldExpire(0, inSeconds(0))).toBe(true);
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";
import { announceSession } from "./lab-client";

// The desktop lab client cannot look a session up — it authenticates as a
// machine, and the lookup needs the candidate's token. If this global is wrong
// or stale, the client observes a candidate switching away and files the event
// against the wrong paper, or drops it. Neither failure is visible from the
// server, which is why it is worth pinning here.

const GLOBAL = "__EXAM_SESSION_ID__";

function fakeWindow() {
  const w: Record<string, unknown> = {};
  vi.stubGlobal("window", w);
  return w;
}

afterEach(() => vi.unstubAllGlobals());

describe("announceSession", () => {
  it("publishes the session the desktop client reads", () => {
    const w = fakeWindow();
    announceSession("4d100c1f-394b-420b-bd9e-4052403420ab");
    expect(w[GLOBAL]).toBe("4d100c1f-394b-420b-bd9e-4052403420ab");
  });

  it("removes it rather than leaving an empty value", () => {
    // A stale id has the client filing a candidate's focus events against a
    // paper they have already submitted.
    const w = fakeWindow();
    announceSession("session-1");
    announceSession(null);
    expect(GLOBAL in w).toBe(false);
  });

  it("replaces one paper's id with the next", () => {
    const w = fakeWindow();
    announceSession("session-1");
    announceSession("session-2");
    expect(w[GLOBAL]).toBe("session-2");
  });

  it("does nothing during prerender, where there is no window", () => {
    vi.stubGlobal("window", undefined);
    expect(() => announceSession("session-1")).not.toThrow();
  });

  it("uses the exact name the desktop client polls for", () => {
    // Named here and in desktop/src-tauri/src/lockdown.rs. The two drifting
    // means invigilation quietly stops working, with nothing to show for it.
    const w = fakeWindow();
    announceSession("session-1");
    expect(Object.keys(w)).toEqual(["__EXAM_SESSION_ID__"]);
  });
});

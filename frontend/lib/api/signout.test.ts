import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// A real localStorage stand-in, because what is being asserted is that the
// credentials are actually gone rather than that a setter was called.
function storage() {
  const data = new Map<string, string>();
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
    get size() { return data.size; },
  };
}

const SIGNED_IN = {
  "northbridge-access-token": "access-token",
  "northbridge-refresh-token": "refresh-token",
  "northbridge-user": JSON.stringify({ id: "u1", role: "ADMIN", fullName: "Exam Cell" }),
};

async function load(fetchImpl: typeof fetch) {
  vi.resetModules();
  const store = storage();
  for (const [k, v] of Object.entries(SIGNED_IN)) store.setItem(k, v);
  vi.stubGlobal("localStorage", store);
  vi.stubGlobal("fetch", fetchImpl);
  vi.stubGlobal("window", { location: { protocol: "http:", hostname: "192.168.1.39" } });
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://localhost:8010/api/v1";
  const mod = await import("./http");
  return { mod, store };
}

afterEach(() => vi.unstubAllGlobals());
beforeEach(() => { delete process.env.NEXT_PUBLIC_API_BASE_URL; });

describe("signOut", () => {
  it("tells the server to end the session, sending the refresh token", async () => {
    // The refresh token is the part that outlives the tab. Without this call
    // a copy of it stayed usable for its full life after signing out.
    const calls: Array<[string, RequestInit | undefined]> = [];
    const fake = (async (url: string, init?: RequestInit) => {
      calls.push([String(url), init]);
      return new Response(null, { status: 204 });
    }) as unknown as typeof fetch;

    const { mod } = await load(fake);
    mod.signOut();

    expect(calls).toHaveLength(1);
    const [url, init] = calls[0];
    expect(url).toBe("http://localhost:8010/api/v1/auth/logout");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ refreshToken: "refresh-token" });
  });

  it("survives the navigation that follows it", async () => {
    // Sign-out is immediately followed by a redirect, which cancels an
    // ordinary request as the page goes away.
    const calls: RequestInit[] = [];
    const fake = (async (_url: string, init?: RequestInit) => {
      calls.push(init as RequestInit);
      return new Response(null, { status: 204 });
    }) as unknown as typeof fetch;

    const { mod } = await load(fake);
    mod.signOut();
    expect(calls[0].keepalive).toBe(true);
  });

  it("forgets the credentials even when the server cannot be reached", async () => {
    // The one that matters on a shared lab machine: a person who pressed sign
    // out must not still be signed in because the network was down.
    const fake = (() => Promise.reject(new Error("network down"))) as unknown as typeof fetch;

    const { mod, store } = await load(fake);
    mod.signOut();

    expect(store.getItem("northbridge-access-token")).toBeNull();
    expect(store.getItem("northbridge-refresh-token")).toBeNull();
    expect(store.getItem("northbridge-user")).toBeNull();
    expect(mod.readUser()).toBeNull();
  });

  it("does not leave an unhandled rejection behind when the request fails", async () => {
    const fake = (() => Promise.reject(new Error("network down"))) as unknown as typeof fetch;
    const { mod } = await load(fake);
    expect(() => mod.signOut()).not.toThrow();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

  it("clears the credentials before the request, not after it", async () => {
    // If it waited for the server, a hung request would leave somebody signed
    // in on the screen they are trying to leave.
    let clearedWhenCalled: string | null = "not-called";
    const fake = (async () => {
      clearedWhenCalled = localStorage.getItem("northbridge-access-token");
      return new Response(null, { status: 204 });
    }) as unknown as typeof fetch;

    const { mod } = await load(fake);
    mod.signOut();
    expect(clearedWhenCalled).toBeNull();
  });

  it("does not call the server when there is nothing to end", async () => {
    const calls: string[] = [];
    const fake = (async (url: string) => {
      calls.push(String(url));
      return new Response(null, { status: 204 });
    }) as unknown as typeof fetch;

    const { mod, store } = await load(fake);
    store.removeItem("northbridge-refresh-token");
    mod.signOut();
    expect(calls).toHaveLength(0);
  });
});

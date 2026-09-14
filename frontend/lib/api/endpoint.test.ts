import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Each case re-imports the module so the environment is read fresh: these
// values are substituted at build time in production, so a cached module
// would be testing the previous case's configuration.
async function load(env: Record<string, string | undefined>, href?: string) {
  vi.resetModules();
  for (const [key, value] of Object.entries(env)) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
  if (href) {
    const url = new URL(href);
    vi.stubGlobal("window", { location: { protocol: url.protocol, hostname: url.hostname } });
  } else {
    vi.stubGlobal("window", undefined);
  }
  return import("./endpoint");
}

const CLEAN = { NEXT_PUBLIC_API_BASE_URL: undefined, NEXT_PUBLIC_API_PORT: undefined };

afterEach(() => vi.unstubAllGlobals());
beforeEach(() => { delete process.env.NEXT_PUBLIC_API_BASE_URL; delete process.env.NEXT_PUBLIC_API_PORT; });

describe("apiBaseUrl", () => {
  it("follows the host the lab machine actually typed", async () => {
    // The whole point: one build, installed on any college's server.
    const { apiBaseUrl } = await load(CLEAN, "http://192.168.1.39:3000/admin");
    expect(apiBaseUrl()).toBe("http://192.168.1.39:8000/api/v1");
  });

  it("keeps the scheme, so an https console does not call http", async () => {
    const { apiBaseUrl } = await load(CLEAN, "https://exams.college.edu/admin");
    expect(apiBaseUrl()).toBe("https://exams.college.edu:8000/api/v1");
  });

  it("honours an explicit address, which is how development runs", async () => {
    const { apiBaseUrl } = await load(
      { ...CLEAN, NEXT_PUBLIC_API_BASE_URL: "http://localhost:8010/api/v1" },
      "http://localhost:3002/admin",
    );
    expect(apiBaseUrl()).toBe("http://localhost:8010/api/v1");
  });

  it("strips a trailing slash, so paths do not double up", async () => {
    const { apiBaseUrl } = await load(
      { ...CLEAN, NEXT_PUBLIC_API_BASE_URL: "http://localhost:8010/api/v1/" },
      "http://localhost:3002/",
    );
    expect(apiBaseUrl()).toBe("http://localhost:8010/api/v1");
  });

  it("accepts a different API port", async () => {
    const { apiBaseUrl } = await load(
      { ...CLEAN, NEXT_PUBLIC_API_PORT: "9000" },
      "http://192.168.1.39:3000/",
    );
    expect(apiBaseUrl()).toBe("http://192.168.1.39:9000/api/v1");
  });

  it("does not fall over during prerender, when there is no page yet", async () => {
    const { apiBaseUrl } = await load(CLEAN);
    expect(apiBaseUrl()).toBe("http://localhost:8000/api/v1");
  });
});

describe("wsBaseUrl", () => {
  it("points at the same machine as the API", async () => {
    // If these two ever disagree the monitor goes quiet against a server that
    // is working perfectly, which is close to undiagnosable.
    const { apiBaseUrl, wsBaseUrl } = await load(CLEAN, "http://192.168.1.39:3000/");
    expect(wsBaseUrl()).toBe("ws://192.168.1.39:8000");
    expect(apiBaseUrl().startsWith("http://192.168.1.39:8000")).toBe(true);
  });

  it("upgrades to wss when the console is served over https", async () => {
    const { wsBaseUrl } = await load(CLEAN, "https://exams.college.edu/");
    expect(wsBaseUrl()).toBe("wss://exams.college.edu:8000");
  });
});

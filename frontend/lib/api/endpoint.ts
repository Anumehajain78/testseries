// ---------------------------------------------------------------------------
// Where the server is
//
// A lab machine reaches the console by typing the exam server's address. The
// API is on that same machine, so the address is already known at that moment
// — and deriving it from the page is what makes one build serve any college.
//
// The alternative is baking it in. `NEXT_PUBLIC_*` is substituted at build
// time, not read at run time, so an absolute URL would mean rebuilding the
// frontend for every server it is installed on, and a rebuild that silently
// keeps yesterday's address is a room of candidates who cannot sign in.
//
// An explicit NEXT_PUBLIC_API_BASE_URL still wins, because development runs
// the two on different hosts and ports.
// ---------------------------------------------------------------------------

const DEFAULT_API_PORT = "8000";

/** The API root, e.g. `http://192.168.1.39:8000/api/v1`. */
export function apiBaseUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (explicit) return explicit.replace(/\/$/, "");

  // Called during prerender as well as in the browser. There is no page to
  // read on the server, and nothing fetches then, so localhost is a
  // placeholder rather than a guess anyone acts on.
  if (typeof window === "undefined") return `http://localhost:${DEFAULT_API_PORT}/api/v1`;

  const port = process.env.NEXT_PUBLIC_API_PORT ?? DEFAULT_API_PORT;
  return `${window.location.protocol}//${window.location.hostname}:${port}/api/v1`;
}

/** The websocket root for the same server, derived so the two can never
 *  disagree about which machine they are talking to. */
export function wsBaseUrl(): string {
  return apiBaseUrl().replace(/\/api\/v1\/?$/, "").replace(/^http/, "ws");
}

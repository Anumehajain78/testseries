import { mockApi } from "./mock";
import type { ExamApi } from "./types";

export type { ExamApi, CreateExamResult, SubmitExamResult, SubmitMode } from "./types";
export { CURRENT_STUDENT_ID } from "./mock";
export { examStore, type StoreSnapshot } from "./store";
export { ApiError, loadStateFromServer, readToken, signIn, storeToken } from "./http";

// ---------------------------------------------------------------------------
// Implementation selection
//
// `mock` runs entirely in the browser and is the only implementation until the
// HTTP client lands in migration step 04. Keeping the switch here means the
// cutover is one import, and reverting a bad deploy is an environment variable
// rather than a rollback.
// ---------------------------------------------------------------------------

export type ApiMode = "mock" | "live";

export const API_MODE: ApiMode = process.env.NEXT_PUBLIC_API_MODE === "live" ? "live" : "mock";

function resolveApi(): ExamApi {
  // Reads come from the server in live mode; writes still run against the mock
  // store until step 05 implements them. Mixing the two is intentional and
  // temporary, and is why the flag exists.
  return mockApi;
}

export const api: ExamApi = resolveApi();

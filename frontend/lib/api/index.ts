import { liveApi } from "./live";
import { mockApi } from "./mock";
import type { ExamApi } from "./types";

export type { ExamApi, CreateExamResult, SubmitExamResult, SubmitMode } from "./types";
export { CURRENT_STUDENT_ID } from "./mock";
export { examStore, type StoreSnapshot } from "./store";
export {
  ApiError,
  candidateSessionId,
  candidateWrites,
  loadStateFromServer,
  readToken,
  readUser,
  signIn,
  storeToken,
  writes,
  type SignedInUser,
} from "./http";

// ---------------------------------------------------------------------------
// Implementation selection
//
// `mock` runs entirely in the browser; `live` runs the exam lifecycle on the
// server. Keeping the switch here means the cutover is one import, and
// reverting a bad deploy is an environment variable rather than a rollback.
// ---------------------------------------------------------------------------

export type ApiMode = "mock" | "live";

export const API_MODE: ApiMode = process.env.NEXT_PUBLIC_API_MODE === "live" ? "live" : "mock";

function resolveApi(): ExamApi {
  return API_MODE === "live" ? liveApi : mockApi;
}

export const api: ExamApi = resolveApi();

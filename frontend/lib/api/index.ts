import { liveApi } from "./live";
import type { ExamApi } from "./types";

export type { ExamApi, CreateExamResult, SubmitExamResult, SubmitMode } from "./types";
export { examStore, emptyExamState, type StoreSnapshot } from "./store";
export { watchExam, type MonitorSocket } from "./realtime";
export {
  ApiError,
  candidateSessionId,
  candidateWrites,
  loadStateFromServer,
  readToken,
  readUser,
  signIn,
  signOut,
  storeToken,
  writes,
  type SignedInUser,
} from "./http";

// ---------------------------------------------------------------------------
// The API
//
// One implementation. The browser-only mock that carried this application
// through its first phases is gone, along with the flag that chose between
// them: the examination now lives on the server, and a client that could
// invent its own answer would not be worth having.
// ---------------------------------------------------------------------------

export const api: ExamApi = liveApi;

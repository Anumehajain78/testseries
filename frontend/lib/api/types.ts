import type { AnswerValue, NewTestInput } from "@/lib/types";

// ---------------------------------------------------------------------------
// API surface
//
// The command surface the UI is allowed to use. Today the only implementation
// is backed by the in-browser mock store; from migration step 04 an HTTP
// implementation replaces it and nothing above this line changes.
//
// Reads still come from the store snapshot via `useExam().state`. Converting
// reads to requests is a separate step, because every screen that reads gains
// loading and error states when it does.
//
// Each method carries the endpoint it becomes, so the mapping never drifts
// from the contract.
// ---------------------------------------------------------------------------

export interface CreateExamResult {
  examId: string;
}

export interface SubmitExamResult {
  submissionId: string;
}

export type SubmitMode = "manual" | "automatic";

export interface ExamApi {
  /** POST /exams — creates a DRAFT assessment. */
  createExam(input: NewTestInput): Promise<CreateExamResult>;

  /** POST /exams/{id}/schedule — DRAFT → SCHEDULED, seats the roster. */
  scheduleExam(examId: string): Promise<void>;

  /** POST /exams/{id}/start — stamps the authoritative window, releases waiting
   *  candidates. Idempotent: a repeat call must not disturb sessions already
   *  in progress. */
  startExam(examId: string): Promise<void>;

  /** PUT /sessions/{id}/answers/{questionId} — idempotent upsert. */
  saveAnswer(examId: string, questionId: string, value: AnswerValue): Promise<void>;

  /** PUT /sessions/{id}/flags/{questionId} — toggles the review flag. */
  toggleFlag(examId: string, questionId: string): Promise<void>;

  /** POST /sessions/{id}/submit — idempotent; a second call returns the
   *  original receipt rather than recording a new one. */
  submitExam(examId: string, mode?: SubmitMode): Promise<SubmitExamResult | null>;

  /** POST /exams/{id}/results/publish — sets `results.published_at`. Stands in
   *  for the demo's score-visibility switch. */
  setResultsPublished(published: boolean): Promise<void>;

  /** Demo affordance only. Has no server counterpart and disappears with the
   *  mock implementation. */
  resetDemoData(): Promise<void>;
}

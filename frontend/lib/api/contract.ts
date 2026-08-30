import type { components } from "./schema.gen";
import type { ExamStatus, StudentExamStatus, ConnectionStatus } from "@/lib/types";

// ---------------------------------------------------------------------------
// Contract types and enum mapping
//
// `schema.gen.ts` is generated from the backend's OpenAPI document and must not
// be edited. This module gives its types readable names and translates the
// server's vocabulary into the one the screens already speak.
//
// The mapping tables below are exhaustive `Record`s keyed by the *server's*
// enums. Adding a state on the backend therefore breaks this build until it is
// consciously given a presentation, rather than silently rendering as blank.
// ---------------------------------------------------------------------------

type Schemas = components["schemas"];

export type ExamSummaryDto = Schemas["ExamSummary"];
export type ExamDetailDto = Schemas["ExamDetail"];
export type ExamWindowDto = Schemas["ExamWindow"];
export type ExamConfigDto = Schemas["ExamConfig"];
export type SessionRowDto = Schemas["SessionRow"];
export type SessionDetailDto = Schemas["SessionDetail"];
export type SessionPaperDto = Schemas["SessionPaper"];
export type SessionStateDto = Schemas["SessionState"];
export type MonitorSnapshotDto = Schemas["MonitorSnapshot"];
export type MonitorSummaryDto = Schemas["MonitorSummary"];
export type SubmissionReceiptDto = Schemas["SubmissionReceipt"];
export type StudentQuestionDto = Schemas["StudentQuestionOut"];
export type QuestionDto = Schemas["QuestionOut"];
export type StudentDto = Schemas["StudentOut"];
export type LabDto = Schemas["LabOut"];
export type ComputerDto = Schemas["ComputerOut"];
export type ResultsPageDto = Schemas["ResultsPage"];
export type AuditEventDto = Schemas["AuditEventOut"];
export type TokenPairDto = Schemas["TokenPair"];
export type AnswerValueDto = Schemas["SaveAnswerRequest"]["value"];

export type ServerExamStatus = Schemas["ExamStatus"];
export type ServerSessionStatus = Schemas["SessionStatus"];
export type ServerConnectionState = Schemas["ConnectionState"];

// ---------------------------------------------------------------------------
// Exam status
//
// Two of the server's states collapse for presentation, and that is deliberate:
//   READY  — the roster is seated but nothing has started, which faculty read
//            as "Scheduled".
//   ENDING — the deadline passed and the sweep is running; the exam is still
//            on screen as "Live now" until it closes.
// CANCELLED does *not* collapse. It is a distinct outcome, so the frontend
// union carries it rather than mislabelling an abandoned exam as completed.
// ---------------------------------------------------------------------------

export const EXAM_STATUS_FROM_SERVER: Record<ServerExamStatus, ExamStatus> = {
  DRAFT: "draft",
  SCHEDULED: "scheduled",
  READY: "scheduled",
  LIVE: "live",
  ENDING: "live",
  COMPLETED: "completed",
  CANCELLED: "cancelled",
};

// ---------------------------------------------------------------------------
// Session status
//
// WAITING collapses into "not-ready": the candidate has signed in but has not
// passed the readiness checks, which is what the roster is telling an
// invigilator either way.
//
// AUTO_SUBMITTED collapses into "submitted" because the distinction is already
// carried by the submission's `mode` wherever it matters. TERMINATED does not
// collapse — an ejected candidate is not a submitted one.
// ---------------------------------------------------------------------------

export const SESSION_STATUS_FROM_SERVER: Record<ServerSessionStatus, StudentExamStatus> = {
  NOT_STARTED: "not-ready",
  WAITING: "not-ready",
  READY: "ready",
  ACTIVE: "in-progress",
  SUBMITTED: "submitted",
  AUTO_SUBMITTED: "submitted",
  TERMINATED: "terminated",
};

// Liveness is already identical on both sides; the Record still guards against
// the server growing a fourth state without the UI noticing.
export const CONNECTION_FROM_SERVER: Record<ServerConnectionState, ConnectionStatus> = {
  online: "online",
  warning: "warning",
  offline: "offline",
};

export const toExamStatus = (status: ServerExamStatus): ExamStatus => EXAM_STATUS_FROM_SERVER[status];
export const toSessionStatus = (status: ServerSessionStatus): StudentExamStatus => SESSION_STATUS_FROM_SERVER[status];
export const toConnection = (state: ServerConnectionState): ConnectionStatus => CONNECTION_FROM_SERVER[state];

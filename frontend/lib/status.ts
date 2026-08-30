import type { BadgeTone, ExamStatus, StudentExamStatus } from "./types";

// ---------------------------------------------------------------------------
// Shared status presentation
//
// These maps were previously copied into three screen modules, which meant a
// new session or exam state had to be added in three places to render
// consistently. They live here so the label and the colour travel together.
// ---------------------------------------------------------------------------

// Per-candidate session status, as shown on the monitor, roster, and lab grid.
export const EXAM_STATUS_LABEL: Record<StudentExamStatus, string> = {
  "not-ready": "Not ready",
  ready: "Ready",
  "in-progress": "Taking test",
  submitted: "Submitted",
};

export function examStatusTone(status: StudentExamStatus): BadgeTone {
  switch (status) {
    case "submitted":
      return "success";
    case "in-progress":
      return "info";
    case "ready":
      return "neutral";
    case "not-ready":
      return "warning";
  }
}

// Exam lifecycle status, as shown on assessment tables and detail headers.
export function examBadgeTone(status: ExamStatus): BadgeTone {
  switch (status) {
    case "live":
      return "live";
    case "scheduled":
      return "info";
    case "completed":
      return "success";
    case "draft":
      return "neutral";
  }
}

import type { Computer, ExamSession, Test } from "./types";

// ---------------------------------------------------------------------------
// Session materialization
//
// A candidate only appears on the monitor once an ExamSession exists binding
// them to a workstation. Seed data ships sessions for one demo exam, so every
// other test — including anything faculty creates — used to open an empty
// monitor even though its roster was populated.
//
// These helpers are pure so the eventual backend can own session creation
// without changing the shape the UI consumes: the store calls them today, an
// API response replaces them later.
// ---------------------------------------------------------------------------

// Pick the workstation a candidate will sit at for a given test. A machine
// inside the test's assigned lab always wins; otherwise fall back to any
// machine bound to that candidate so the roster still resolves an ID.
export function computerForCandidate(
  studentId: string,
  labId: string,
  computers: Computer[],
): Computer | undefined {
  const bound = computers.filter((computer) => computer.assignedStudentId === studentId);
  return bound.find((computer) => computer.labId === labId) ?? bound[0];
}

// Build a session for a single assigned candidate. Connection state comes from
// the workstation, and a candidate with no reachable machine starts Not ready.
export function createSession(
  test: Test,
  studentId: string,
  computers: Computer[],
  atIso: string,
): ExamSession {
  const computer = computerForCandidate(studentId, test.labId, computers);
  const connection = computer?.connection ?? "offline";
  const reachable = connection !== "offline";
  return {
    testId: test.id,
    studentId,
    computerId: computer?.id ?? "Unassigned",
    connection,
    examStatus: reachable ? "ready" : "not-ready",
    loginAt: reachable ? atIso : undefined,
    lastHeartbeatAt: reachable ? atIso : undefined,
    warnings: 0,
    activity: reachable
      ? [{ at: atIso, label: "Signed in to exam client", severity: "info" as const }]
      : [],
  };
}

// Sessions for every assigned candidate that does not already have one for this
// test. Existing sessions are never rebuilt, so live state survives.
export function missingSessions(
  test: Test,
  computers: Computer[],
  existing: ExamSession[],
  atIso: string,
): ExamSession[] {
  const seated = new Set(
    existing.filter((session) => session.testId === test.id).map((session) => session.studentId),
  );
  return test.assignedStudentIds
    .filter((studentId) => !seated.has(studentId))
    .map((studentId) => createSession(test, studentId, computers, atIso));
}

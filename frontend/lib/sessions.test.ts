import { describe, expect, it } from "vitest";
import { computerForCandidate, createSession, missingSessions } from "./sessions";
import type { Computer, ExamSession, Test } from "./types";

const AT = "2026-08-30T10:00:00.000Z";

const computer = (id: string, labId: string, index: number, assignedStudentId?: string, connection: Computer["connection"] = "online"): Computer =>
  ({ id, labId, index, assignedStudentId, connection });

const test = (overrides: Partial<Test> = {}): Test => ({
  id: "t-1",
  title: "Sample Assessment",
  code: "CSE-000-X1",
  course: "Sample Course",
  department: "Computer Science",
  durationMinutes: 45,
  totalMarks: 10,
  scheduledAt: AT,
  status: "scheduled",
  labId: "lab-a",
  assignedStudentIds: ["st-001", "st-002"],
  instructions: [],
  questions: [],
  config: { questionsPerStudent: 0, randomizeQuestions: false, randomizeOptions: false, allowNavigation: true, autoSubmitOnExpiry: true },
  ...overrides,
});

describe("computerForCandidate", () => {
  it("prefers a workstation inside the test's assigned lab", () => {
    const computers = [
      computer("LAB2-PC-01", "lab-b", 1, "st-001"),
      computer("LAB1-PC-07", "lab-a", 7, "st-001"),
    ];
    expect(computerForCandidate("st-001", "lab-a", computers)?.id).toBe("LAB1-PC-07");
  });

  it("falls back to any bound workstation when the lab has none", () => {
    const computers = [computer("LAB2-PC-01", "lab-b", 1, "st-001")];
    expect(computerForCandidate("st-001", "lab-a", computers)?.id).toBe("LAB2-PC-01");
  });

  it("returns undefined for a candidate with no workstation", () => {
    expect(computerForCandidate("st-999", "lab-a", [])).toBeUndefined();
  });
});

describe("createSession", () => {
  it("marks a candidate on a reachable workstation as ready and logged in", () => {
    const computers = [computer("LAB1-PC-01", "lab-a", 1, "st-001")];
    const session = createSession(test(), "st-001", computers, AT);
    expect(session).toMatchObject({
      testId: "t-1",
      studentId: "st-001",
      computerId: "LAB1-PC-01",
      connection: "online",
      examStatus: "ready",
      loginAt: AT,
      lastHeartbeatAt: AT,
      warnings: 0,
    });
    expect(session.activity).toHaveLength(1);
  });

  it("marks a candidate on an offline workstation as not ready with no login", () => {
    const computers = [computer("LAB1-PC-02", "lab-a", 2, "st-002", "offline")];
    const session = createSession(test(), "st-002", computers, AT);
    expect(session.examStatus).toBe("not-ready");
    expect(session.connection).toBe("offline");
    expect(session.loginAt).toBeUndefined();
    expect(session.lastHeartbeatAt).toBeUndefined();
    expect(session.activity).toEqual([]);
  });

  it("carries a warning workstation's connection through to the session", () => {
    const computers = [computer("LAB1-PC-05", "lab-a", 5, "st-001", "warning")];
    expect(createSession(test(), "st-001", computers, AT).connection).toBe("warning");
  });

  it("still produces a session when the candidate has no workstation", () => {
    const session = createSession(test(), "st-001", [], AT);
    expect(session.computerId).toBe("Unassigned");
    expect(session.examStatus).toBe("not-ready");
  });
});

describe("missingSessions", () => {
  const computers = [
    computer("LAB1-PC-01", "lab-a", 1, "st-001"),
    computer("LAB1-PC-02", "lab-a", 2, "st-002"),
  ];

  it("seats every assigned candidate when none has a session", () => {
    const created = missingSessions(test(), computers, [], AT);
    expect(created.map((s) => s.studentId)).toEqual(["st-001", "st-002"]);
  });

  it("never rebuilds a candidate who already has a session for this test", () => {
    const existing: ExamSession[] = [
      { testId: "t-1", studentId: "st-001", computerId: "LAB1-PC-01", connection: "online", examStatus: "in-progress", warnings: 0, activity: [] },
    ];
    const created = missingSessions(test(), computers, existing, AT);
    expect(created.map((s) => s.studentId)).toEqual(["st-002"]);
  });

  it("ignores sessions belonging to a different test", () => {
    const existing: ExamSession[] = [
      { testId: "other", studentId: "st-001", computerId: "LAB1-PC-01", connection: "online", examStatus: "in-progress", warnings: 0, activity: [] },
    ];
    expect(missingSessions(test(), computers, existing, AT)).toHaveLength(2);
  });

  it("returns nothing for a test with an empty roster", () => {
    expect(missingSessions(test({ assignedStudentIds: [] }), computers, [], AT)).toEqual([]);
  });
});

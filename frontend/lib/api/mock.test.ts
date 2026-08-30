import { beforeEach, describe, expect, it } from "vitest";
import { CURRENT_STUDENT_ID, mockApi } from "./mock";
import { examStore } from "./store";
import type { NewTestInput } from "@/lib/types";

// Behavioural contract for the write path. These assertions describe what the
// server must also do once the HTTP implementation replaces this one, so they
// are the acceptance criteria for that swap rather than tests of the mock.

const state = () => examStore.getSnapshot().state;

const draftInput = (overrides: Partial<NewTestInput> = {}): NewTestInput => ({
  title: "Compilers Mid-Semester",
  code: "CSE-401-M1",
  course: "Compiler Design",
  department: "Computer Science",
  durationMinutes: 45,
  labId: "lab-b",
  assignedStudentIds: ["st-041", "st-042"],
  questions: [
    { prompt: "What does a lexer produce?", options: ["Tokens", "Bytecode", "AST", "IR"], correctOption: 0, marks: 2 },
  ],
  ...overrides,
});

beforeEach(() => {
  examStore.reset();
});

describe("createExam", () => {
  it("resolves to a plain string id, not a promise", async () => {
    const { examId } = await mockApi.createExam(draftInput());
    expect(typeof examId).toBe("string");
    expect(examId).toMatch(/^cse-401-m1-\d+$/);
  });

  it("creates the exam as a draft with derived marks", async () => {
    const { examId } = await mockApi.createExam(draftInput());
    const exam = state().tests.find((item) => item.id === examId);
    expect(exam?.status).toBe("draft");
    expect(exam?.totalMarks).toBe(2);
    expect(exam?.questions).toHaveLength(1);
  });

  it("records an audit event for the creation", async () => {
    const before = state().audits.length;
    await mockApi.createExam(draftInput());
    expect(state().audits.length).toBe(before + 1);
    expect(state().audits[0].action).toBe("Assessment created");
  });
});

describe("scheduleExam", () => {
  it("seats every assigned candidate", async () => {
    const { examId } = await mockApi.createExam(draftInput());
    await mockApi.scheduleExam(examId);
    const sessions = state().sessions.filter((session) => session.testId === examId);
    expect(sessions).toHaveLength(2);
    expect(state().tests.find((item) => item.id === examId)?.status).toBe("scheduled");
  });

  it("does not duplicate sessions when scheduled twice", async () => {
    const { examId } = await mockApi.createExam(draftInput());
    await mockApi.scheduleExam(examId);
    await mockApi.scheduleExam(examId);
    expect(state().sessions.filter((session) => session.testId === examId)).toHaveLength(2);
  });
});

describe("startExam", () => {
  it("stamps a window and releases waiting candidates", async () => {
    const { examId } = await mockApi.createExam(draftInput());
    await mockApi.scheduleExam(examId);
    await mockApi.startExam(examId);

    const exam = state().tests.find((item) => item.id === examId);
    expect(exam?.status).toBe("live");
    expect(exam?.endsAt).toBeTruthy();

    const released = state().sessions.filter((s) => s.testId === examId && s.examStatus === "in-progress");
    expect(released.length).toBeGreaterThan(0);
  });

  it("seats candidates even when the exam was never scheduled", async () => {
    const { examId } = await mockApi.createExam(draftInput());
    await mockApi.startExam(examId);
    expect(state().sessions.filter((session) => session.testId === examId)).toHaveLength(2);
  });

  it("is idempotent — a repeat start adds no duplicate timeline entry", async () => {
    const { examId } = await mockApi.createExam(draftInput());
    await mockApi.scheduleExam(examId);
    await mockApi.startExam(examId);

    const first = state().sessions.find((s) => s.testId === examId && s.examStatus === "in-progress");
    const timelineBefore = first!.activity.length;
    const startedAtBefore = first!.examStartedAt;

    await mockApi.startExam(examId);

    const second = state().sessions.find((s) => s.studentId === first!.studentId && s.testId === examId);
    expect(second!.activity).toHaveLength(timelineBefore);
    expect(second!.examStartedAt).toBe(startedAtBefore);
  });
});

describe("answers and flags", () => {
  it("saves and overwrites an answer for the current candidate", async () => {
    const { examId } = await mockApi.createExam(draftInput());
    const questionId = state().tests.find((item) => item.id === examId)!.questions[0].id;

    await mockApi.saveAnswer(examId, questionId, { kind: "single", option: 2 });
    const key = `${examId}:${CURRENT_STUDENT_ID}`;
    expect(state().answers[key][questionId]).toEqual({ kind: "single", option: 2 });

    await mockApi.saveAnswer(examId, questionId, { kind: "single", option: 0 });
    expect(state().answers[key][questionId]).toEqual({ kind: "single", option: 0 });
  });

  it("toggles a flag on and back off", async () => {
    const { examId } = await mockApi.createExam(draftInput());
    const questionId = state().tests.find((item) => item.id === examId)!.questions[0].id;
    const key = `${examId}:${CURRENT_STUDENT_ID}`;

    await mockApi.toggleFlag(examId, questionId);
    expect(state().flags[key]).toContain(questionId);

    await mockApi.toggleFlag(examId, questionId);
    expect(state().flags[key]).not.toContain(questionId);
  });
});

describe("submitExam", () => {
  it("returns a receipt and grades the paper", async () => {
    const { examId } = await mockApi.createExam(draftInput());
    const questionId = state().tests.find((item) => item.id === examId)!.questions[0].id;
    await mockApi.saveAnswer(examId, questionId, { kind: "single", option: 0 });

    const receipt = await mockApi.submitExam(examId);
    expect(receipt?.submissionId).toMatch(/^sub-/);

    const result = state().results.find((item) => item.testId === examId);
    expect(result?.score).toBe(2);
    expect(result?.total).toBe(2);
  });

  it("is idempotent — a second submit returns the original receipt", async () => {
    const { examId } = await mockApi.createExam(draftInput());
    const first = await mockApi.submitExam(examId);
    const second = await mockApi.submitExam(examId);

    expect(second?.submissionId).toBe(first?.submissionId);
    expect(state().submissions.filter((item) => item.testId === examId)).toHaveLength(1);
    expect(state().results.filter((item) => item.testId === examId)).toHaveLength(1);
  });

  it("marks an automatic submission as a warning in the audit trail", async () => {
    const { examId } = await mockApi.createExam(draftInput());
    await mockApi.submitExam(examId, "automatic");
    expect(state().audits[0].action).toBe("Exam auto-submitted");
    expect(state().audits[0].severity).toBe("warning");
  });
});

describe("setResultsPublished", () => {
  it("toggles score visibility", async () => {
    await mockApi.setResultsPublished(true);
    expect(state().mockResultMode).toBe(true);
    await mockApi.setResultsPublished(false);
    expect(state().mockResultMode).toBe(false);
  });
});

describe("store", () => {
  it("notifies subscribers when state changes", async () => {
    let notifications = 0;
    const unsubscribe = examStore.subscribe(() => { notifications += 1; });
    await mockApi.createExam(draftInput());
    unsubscribe();
    expect(notifications).toBeGreaterThan(0);
  });

  it("returns a stable snapshot reference when nothing changed", () => {
    const first = examStore.getSnapshot();
    examStore.mutate((previous) => previous);
    expect(examStore.getSnapshot()).toBe(first);
  });
});

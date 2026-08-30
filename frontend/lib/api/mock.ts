import { scoreExam } from "@/lib/scoring";
import { missingSessions } from "@/lib/sessions";
import type { AnswerValue, ExamConfig, NewTestInput } from "@/lib/types";
import { examStore } from "./store";
import type { CreateExamResult, ExamApi, SubmitExamResult, SubmitMode } from "./types";

// ---------------------------------------------------------------------------
// Mock implementation of ExamApi
//
// The transitions the server will own, executed against the in-browser store.
// Audit events are written here for the same reason the server will write
// them: they are a consequence of the transition, not something the UI decides
// to record.
//
// Everything is async even though nothing awaits, so call sites already have
// the shape an HTTP client needs.
// ---------------------------------------------------------------------------

// The demo authenticates nobody; this stands in for the token subject.
export const CURRENT_STUDENT_ID = "st-001";

const answerKey = (examId: string) => `${examId}:${CURRENT_STUDENT_ID}`;
const uid = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

const DEFAULT_CONFIG: ExamConfig = {
  questionsPerStudent: 0,
  randomizeQuestions: false,
  randomizeOptions: false,
  allowNavigation: true,
  autoSubmitOnExpiry: true,
};

export const mockApi: ExamApi = {
  async createExam(input: NewTestInput): Promise<CreateExamResult> {
    const examId = `${input.code.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${Date.now()}`;
    const questions = input.questions.map((question, index) => ({
      ...question,
      id: `${examId}-q${index + 1}`,
      type: "mcq" as const,
    }));
    const config: ExamConfig = {
      ...DEFAULT_CONFIG,
      ...input.config,
      questionsPerStudent: input.config?.questionsPerStudent || questions.length,
    };

    examStore.mutate((previous) => ({
      ...previous,
      tests: [
        {
          id: examId,
          title: input.title,
          code: input.code,
          course: input.course,
          department: input.department,
          description: input.description,
          durationMinutes: input.durationMinutes,
          totalMarks: questions.reduce((sum, question) => sum + question.marks, 0),
          scheduledAt: input.scheduledAt ?? new Date(Date.now() + 86_400_000).toISOString(),
          status: "draft",
          labId: input.labId,
          assignedStudentIds: input.assignedStudentIds ?? [],
          config,
          instructions: input.instructions?.length
            ? input.instructions
            : ["Answer all questions.", "Review flagged questions before final submission."],
          questions,
        },
        ...previous.tests,
      ],
      audits: [
        { id: uid("audit"), at: new Date().toISOString(), actor: "Exam Cell · Anita Rao", action: "Assessment created", detail: `${input.title} saved as a draft.`, category: "system", severity: "info" },
        ...previous.audits,
      ],
      toasts: [{ id: uid("toast"), title: "Draft created", message: `${input.title} is ready for review.`, tone: "success" }],
    }));

    return { examId };
  },

  async scheduleExam(examId: string) {
    examStore.mutate((previous) => {
      const exam = previous.tests.find((item) => item.id === examId);
      if (!exam) return previous;
      // Seat the roster on scheduling so faculty can review candidate readiness
      // on the detail page before starting the examination.
      const at = new Date().toISOString();
      return {
        ...previous,
        tests: previous.tests.map((item) => (item.id === examId ? { ...item, status: "scheduled" as const } : item)),
        sessions: [...previous.sessions, ...missingSessions(exam, previous.computers, previous.sessions, at)],
        audits: [
          { id: uid("audit"), at, actor: "Exam Cell · Anita Rao", action: "Exam scheduled", detail: `${exam.title} moved to the scheduled queue.`, category: "exam", severity: "info" },
          ...previous.audits,
        ],
        toasts: [{ id: uid("toast"), title: "Exam scheduled", message: "Students will see it in their upcoming assessments.", tone: "success" }],
      };
    });
  },

  async startExam(examId: string) {
    examStore.mutate((previous) => {
      const exam = previous.tests.find((item) => item.id === examId);
      if (!exam || exam.status === "completed") return previous;
      const startedAt = new Date();
      const startedAtIso = startedAt.toISOString();
      const endsAt = new Date(startedAt.getTime() + exam.durationMinutes * 60_000).toISOString();
      // Seat any assigned candidate who has no session yet, so a test that was
      // never pre-seeded still opens a populated monitor (the backend will own
      // this once lab clients check in for real).
      const seated = [...previous.sessions, ...missingSessions(exam, previous.computers, previous.sessions, startedAtIso)];
      return {
        ...previous,
        tests: previous.tests.map((item) => (item.id === examId ? { ...item, status: "live" as const, endsAt } : item)),
        // Release connected candidates into the examination. Only sessions
        // still waiting are transitioned, so a repeat start cannot duplicate
        // timeline entries or reset a candidate already answering.
        sessions: seated.map((session) =>
          session.testId === examId && session.connection !== "offline" && (session.examStatus === "ready" || session.examStatus === "not-ready")
            ? {
                ...session,
                examStatus: "in-progress" as const,
                examStartedAt: session.examStartedAt ?? startedAtIso,
                activity: [...session.activity, { at: startedAtIso, label: "Exam started", severity: "info" as const }],
              }
            : session,
        ),
        audits: [
          { id: uid("audit"), at: startedAtIso, actor: "Exam Cell · Anita Rao", action: "Exam started", detail: `${exam.title} is live; the student entry gate has opened.`, category: "exam", severity: "info" },
          ...previous.audits,
        ],
        toasts: [{ id: uid("toast"), title: "Exam is live", message: "Student waiting rooms have been released.", tone: "success" }],
      };
    });
  },

  async saveAnswer(examId: string, questionId: string, value: AnswerValue) {
    examStore.mutate((previous) => {
      const key = answerKey(examId);
      return {
        ...previous,
        answers: { ...previous.answers, [key]: { ...(previous.answers[key] ?? {}), [questionId]: value } },
      };
    });
  },

  async toggleFlag(examId: string, questionId: string) {
    examStore.mutate((previous) => {
      const key = answerKey(examId);
      const flagged = previous.flags[key] ?? [];
      return {
        ...previous,
        flags: {
          ...previous.flags,
          [key]: flagged.includes(questionId) ? flagged.filter((id) => id !== questionId) : [...flagged, questionId],
        },
      };
    });
  },

  async submitExam(examId: string, mode: SubmitMode = "manual"): Promise<SubmitExamResult | null> {
    let receipt: SubmitExamResult | null = null;
    examStore.mutate((previous) => {
      // Idempotent: a second submit returns the original receipt rather than
      // recording another one.
      const existing = previous.submissions.find((item) => item.testId === examId && item.studentId === CURRENT_STUDENT_ID);
      if (existing) {
        receipt = { submissionId: existing.id };
        return previous;
      }
      const exam = previous.tests.find((item) => item.id === examId);
      if (!exam) return previous;

      const key = answerKey(examId);
      const answers = previous.answers[key] ?? {};
      const score = scoreExam(exam.questions, answers);
      const submittedAt = new Date().toISOString();
      const submissionId = uid("sub");
      receipt = { submissionId };

      return {
        ...previous,
        submissions: [
          { id: submissionId, testId: examId, studentId: CURRENT_STUDENT_ID, answers, flagged: previous.flags[key] ?? [], submittedAt, mode },
          ...previous.submissions,
        ],
        results: [
          { id: uid("res"), testId: examId, studentId: CURRENT_STUDENT_ID, score, total: exam.totalMarks, submittedAt, mode },
          ...previous.results,
        ],
        sessions: previous.sessions.map((session) =>
          session.testId === examId && session.studentId === CURRENT_STUDENT_ID
            ? { ...session, examStatus: "submitted" as const }
            : session,
        ),
        audits: [
          { id: uid("audit"), at: submittedAt, actor: "Aarav Mehta · 23CSE1042", action: mode === "automatic" ? "Exam auto-submitted" : "Exam submitted", detail: `${exam.title} received with ${Object.keys(answers).length} of ${exam.questions.length} responses.`, category: "exam", severity: mode === "automatic" ? "warning" : "info" },
          ...previous.audits,
        ],
        toasts: [{ id: uid("toast"), title: "Submission received", message: "Your response receipt is now available.", tone: "success" }],
      };
    });
    return receipt;
  },

  async setResultsPublished(published: boolean) {
    examStore.mutate((previous) => ({ ...previous, mockResultMode: published }));
  },

  async resetDemoData() {
    examStore.reset();
  },
};

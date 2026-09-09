import type { AnswerValue, NewTestInput } from "@/lib/types";
import { examStore } from "./store";
import { candidateSessionId, candidateWrites, loadStateFromServer, readUser, writes } from "./http";
import type { CreateExamResult, ExamApi, SubmitExamResult } from "./types";

// ---------------------------------------------------------------------------
// Live ExamApi
//
// The exam lifecycle now runs on the server. Each write posts, then reloads the
// snapshot the screens read, so a transition the server refuses never appears
// to have happened locally — the UI can only show state the database agreed to.
//
// Reloading the whole snapshot after every write is the same bridge the reads
// use: correct, and heavier than it needs to be. It goes away when each screen
// owns its query and can invalidate just what changed.
//
// The candidate path — answers, flags, submission — is deliberately still
// unimplemented. It needs check-in, per-session papers and the write guards
// that go with them, which is its own step.
// ---------------------------------------------------------------------------

async function refresh(): Promise<void> {
  examStore.adoptServerState((await loadStateFromServer()) as Parameters<typeof examStore.adoptServerState>[0]);
}

/** The session behind the candidate's current paper. */
function sessionFor(examId: string): string {
  const snapshot = examStore.getSnapshot().state;
  const studentId = readUser()?.id ?? "";
  const sessionId = candidateSessionId(snapshot, examId, studentId);
  if (!sessionId) throw new Error("No examination session is open for you.");
  return sessionId;
}

// Monotonic per answer, so a write that arrives late after a reconnect is
// recognised as stale by the server rather than overwriting a newer one.
const seqs = new Map<string, number>();
const nextSeq = (key: string) => {
  const next = (seqs.get(key) ?? 0) + 1;
  seqs.set(key, next);
  return next;
};

/**
 * The wire shape of an exam.
 *
 * Shared by create and edit so the two cannot drift: an editor that quietly
 * dropped a field the create form sends would corrupt drafts silently.
 */
function examPayload(input: NewTestInput) {
  return {
      title: input.title,
      code: input.code,
      course: input.course,
      department: input.department,
      description: input.description,
      instructions: input.instructions ?? [],
      durationMinutes: input.durationMinutes,
      scheduledAt: input.scheduledAt ?? new Date(Date.now() + 86_400_000).toISOString(),
      labId: input.labId,
      studentIds: input.assignedStudentIds ?? [],
      // Authored inline; the server files them in the question bank so the
      // paper is reusable rather than trapped in this one exam. The type is
      // carried through rather than assumed — sending everything as
      // multiple-choice would rewrite written questions on every edit.
      questions: input.questions.map((question) => ({
        type: question.type,
        prompt: question.prompt,
        marks: question.marks,
        options: question.options.map((body, index) => ({
          body,
          isCorrect: question.correctOptions.includes(index),
        })),
      })),
      config: {
        questionsPerStudent: input.config?.questionsPerStudent ?? 0,
        randomizeQuestions: input.config?.randomizeQuestions ?? false,
        randomizeOptions: input.config?.randomizeOptions ?? false,
        allowNavigation: input.config?.allowNavigation ?? true,
        autoSubmitOnExpiry: input.config?.autoSubmitOnExpiry ?? true,
      },
    
  };
}

export const liveApi: ExamApi = {
  async createExam(input: NewTestInput): Promise<CreateExamResult> {
    const created = await writes.createExam(examPayload(input));
    await refresh();
    return { examId: created.id };
  },

  async updateExam(examId: string, input: NewTestInput) {
    await writes.updateExam(examId, examPayload(input));
    await refresh();
  },


  async scheduleExam(examId: string) {
    await writes.scheduleExam(examId);
    await refresh();
  },

  async startExam(examId: string) {
    // A stable key per exam means a retried or double-clicked start is
    // recognised as the same attempt, so the window never moves under a room
    // full of candidates.
    await writes.startExam(examId, `start:${examId}`);
    await refresh();
  },

  async setResultsPublished(examId: string, published: boolean) {
    // One assessment at a time. Releasing every completed exam at once, as
    // this used to, would publish papers still being marked alongside the one
    // the exam cell actually meant to release.
    await writes.publishResults(examId, published);
    await refresh();
  },

  async saveAnswer(examId: string, questionId: string, value: AnswerValue) {
    const sessionId = sessionFor(examId);
    await candidateWrites.saveAnswer(sessionId, questionId, value, nextSeq(`${sessionId}:${questionId}`));
    // Optimistic locally: the answer is already on screen, and refetching the
    // whole paper on every keystroke would be absurd. The server is
    // authoritative on reconnect via /state.
    examStore.mutate((previous) => {
      const key = `${examId}:${readUser()?.id ?? ""}`;
      return { ...previous, answers: { ...previous.answers, [key]: { ...(previous.answers[key] ?? {}), [questionId]: value } } };
    });
  },

  async toggleFlag(examId: string, questionId: string) {
    const sessionId = sessionFor(examId);
    await candidateWrites.toggleFlag(sessionId, questionId);
    examStore.mutate((previous) => {
      const key = `${examId}:${readUser()?.id ?? ""}`;
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

  async submitExam(examId: string): Promise<SubmitExamResult | null> {
    const sessionId = sessionFor(examId);
    const receipt = await candidateWrites.submit(sessionId);
    await refresh();
    return { submissionId: receipt.submissionId };
  },

  async resetDemoData() {
    // There is no server counterpart: re-seeding is a backend command, not
    // something the console should be able to do to a real database.
    throw new Error("Reset is only available in mock mode. Re-run the backend seed instead.");
  },
};

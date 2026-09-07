import type { NewTestInput } from "@/lib/types";
import { examStore } from "./store";
import { loadStateFromServer, writes } from "./http";
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

function notYet(action: string): never {
  throw new Error(
    `${action} is not available against the server yet — the candidate exam path lands in a later step.`,
  );
}

export const liveApi: ExamApi = {
  async createExam(input: NewTestInput): Promise<CreateExamResult> {
    const created = await writes.createExam({
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
      // paper is reusable rather than trapped in this one exam.
      questions: input.questions.map((question) => ({
        type: "mcq" as const,
        prompt: question.prompt,
        marks: question.marks,
        options: question.options.map((body, index) => ({
          body,
          isCorrect: index === question.correctOption,
        })),
      })),
      config: {
        questionsPerStudent: input.config?.questionsPerStudent ?? 0,
        randomizeQuestions: input.config?.randomizeQuestions ?? false,
        randomizeOptions: input.config?.randomizeOptions ?? false,
        allowNavigation: input.config?.allowNavigation ?? true,
        autoSubmitOnExpiry: input.config?.autoSubmitOnExpiry ?? true,
      },
    });
    await refresh();
    return { examId: created.id };
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

  async setResultsPublished(published: boolean) {
    // Publication is per exam on the server; the demo's single switch maps to
    // every completed exam, which is the closest honest reading of it.
    const completed = examStore
      .getSnapshot()
      .state.tests.filter((test) => test.status === "completed");
    for (const test of completed) {
      await writes.publishResults(test.id, published);
    }
    await refresh();
  },

  async saveAnswer(): Promise<void> { notYet("Saving an answer"); },
  async toggleFlag(): Promise<void> { notYet("Flagging a question"); },
  async submitExam(): Promise<SubmitExamResult | null> {
    notYet("Submitting an examination");
  },

  async resetDemoData() {
    // There is no server counterpart: re-seeding is a backend command, not
    // something the console should be able to do to a real database.
    throw new Error("Reset is only available in mock mode. Re-run the backend seed instead.");
  },
};

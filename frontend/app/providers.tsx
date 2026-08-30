"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { createSeedState } from "@/lib/mock-data";
import { scoreExam } from "@/lib/scoring";
import { missingSessions } from "@/lib/sessions";
import type { AnswerValue, ExamConfig, ExamState, NewTestInput } from "@/lib/types";

const STORAGE_KEY = "northbridge-exam-control-v2";
const CURRENT_STUDENT = "st-001";

type ExamContextValue = {
  state: ExamState;
  hydrated: boolean;
  currentStudentId: string;
  createTest: (input: NewTestInput) => string;
  scheduleExam: (testId: string) => void;
  startExam: (testId: string) => void;
  answerQuestion: (testId: string, questionId: string, value: AnswerValue) => void;
  flagQuestion: (testId: string, questionId: string) => void;
  submitExam: (testId: string, mode?: "manual" | "automatic") => void;
  setMockResultMode: (enabled: boolean) => void;
  dismissToast: (id: string) => void;
  resetDemo: () => void;
};

const ExamContext = createContext<ExamContextValue | null>(null);
const examKey = (testId: string) => `${testId}:${CURRENT_STUDENT}`;
const uid = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

const DEFAULT_CONFIG: ExamConfig = {
  questionsPerStudent: 0,
  randomizeQuestions: false,
  randomizeOptions: false,
  allowNavigation: true,
  autoSubmitOnExpiry: true,
};

function safeState(raw: string | null): ExamState | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as ExamState;
    return parsed.version === 2 && Array.isArray(parsed.tests) ? parsed : null;
  } catch { return null; }
}

export function ExamProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ExamState>(createSeedState);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    // localStorage is an external store that cannot be read during render or
    // on the server, so adopting it on mount is the intended one-shot sync.
    // Components gate on `hydrated` and render LoadingState until this lands,
    // which is what keeps the server and client markup identical. This whole
    // effect is replaced by the API client in the backend integration phase.
    const stored = safeState(localStorage.getItem(STORAGE_KEY));
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (stored) setState(stored);
    setHydrated(true);
    const sync = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY) {
        const next = safeState(event.newValue);
        if (next) setState(next);
      }
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);

  useEffect(() => {
    if (hydrated) localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...state, toasts: [] }));
  }, [state, hydrated]);

  const createTest = useCallback((input: NewTestInput) => {
    const id = `${input.code.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${Date.now()}`;
    const questions = input.questions.map((q, index) => ({ ...q, id: `${id}-q${index + 1}`, type: "mcq" as const }));
    const config: ExamConfig = { ...DEFAULT_CONFIG, ...input.config, questionsPerStudent: input.config?.questionsPerStudent || questions.length };
    setState((prev) => ({
      ...prev,
      tests: [
        {
          id,
          title: input.title,
          code: input.code,
          course: input.course,
          department: input.department,
          description: input.description,
          durationMinutes: input.durationMinutes,
          totalMarks: questions.reduce((sum, q) => sum + q.marks, 0),
          scheduledAt: input.scheduledAt ?? new Date(Date.now() + 86400000).toISOString(),
          status: "draft",
          labId: input.labId,
          assignedStudentIds: input.assignedStudentIds ?? [],
          config,
          instructions: input.instructions?.length ? input.instructions : ["Answer all questions.", "Review flagged questions before final submission."],
          questions,
        },
        ...prev.tests,
      ],
      audits: [
        { id: uid("audit"), at: new Date().toISOString(), actor: "Exam Cell · Anita Rao", action: "Assessment created", detail: `${input.title} saved as a draft.`, category: "system", severity: "info" },
        ...prev.audits,
      ],
      toasts: [{ id: uid("toast"), title: "Draft created", message: `${input.title} is ready for review.`, tone: "success" }],
    }));
    return id;
  }, []);

  const scheduleExam = useCallback((testId: string) => setState((prev) => {
    const test = prev.tests.find((item) => item.id === testId);
    if (!test) return prev;
    // Seat the roster on scheduling so faculty can review candidate readiness
    // on the detail page before starting the examination.
    const scheduledAtIso = new Date().toISOString();
    return {
      ...prev,
      tests: prev.tests.map((item) => item.id === testId ? { ...item, status: "scheduled" as const } : item),
      sessions: [...prev.sessions, ...missingSessions(test, prev.computers, prev.sessions, scheduledAtIso)],
      audits: [
        { id: uid("audit"), at: new Date().toISOString(), actor: "Exam Cell · Anita Rao", action: "Exam scheduled", detail: `${test.title} moved to the scheduled queue.`, category: "exam", severity: "info" },
        ...prev.audits,
      ],
      toasts: [{ id: uid("toast"), title: "Exam scheduled", message: "Students will see it in their upcoming assessments.", tone: "success" }],
    };
  }), []);

  const startExam = useCallback((testId: string) => setState((prev) => {
    const test = prev.tests.find((item) => item.id === testId);
    if (!test || test.status === "completed") return prev;
    const startedAt = new Date();
    const endsAt = new Date(startedAt.getTime() + test.durationMinutes * 60_000).toISOString();
    const startedAtIso = startedAt.toISOString();
    // Seat any assigned candidate who has no session yet, so a test that was
    // never pre-seeded still opens a populated monitor (the backend will own
    // this once lab clients check in for real).
    const seated = [...prev.sessions, ...missingSessions(test, prev.computers, prev.sessions, startedAtIso)];
    return {
      ...prev,
      tests: prev.tests.map((item) => item.id === testId ? { ...item, status: "live" as const, endsAt } : item),
      // Release connected candidates into the examination for this test. Only
      // sessions still waiting are transitioned, so a repeat start cannot
      // duplicate timeline entries or reset a candidate already answering.
      sessions: seated.map((session) =>
        session.testId === testId && session.connection !== "offline" && (session.examStatus === "ready" || session.examStatus === "not-ready")
          ? {
              ...session,
              examStatus: "in-progress" as const,
              examStartedAt: session.examStartedAt ?? startedAtIso,
              activity: [...session.activity, { at: startedAtIso, label: "Exam started", severity: "info" as const }],
            }
          : session,
      ),
      audits: [
        { id: uid("audit"), at: startedAtIso, actor: "Exam Cell · Anita Rao", action: "Exam started", detail: `${test.title} is live; the student entry gate has opened.`, category: "exam", severity: "info" },
        ...prev.audits,
      ],
      toasts: [{ id: uid("toast"), title: "Exam is live", message: "Student waiting rooms have been released.", tone: "success" }],
    };
  }), []);

  const answerQuestion = useCallback((testId: string, questionId: string, value: AnswerValue) => setState((prev) => {
    const key = examKey(testId);
    return { ...prev, answers: { ...prev.answers, [key]: { ...(prev.answers[key] ?? {}), [questionId]: value } } };
  }), []);

  const flagQuestion = useCallback((testId: string, questionId: string) => setState((prev) => {
    const key = examKey(testId); const old = prev.flags[key] ?? [];
    return { ...prev, flags: { ...prev.flags, [key]: old.includes(questionId) ? old.filter((id) => id !== questionId) : [...old, questionId] } };
  }), []);

  const submitExam = useCallback((testId: string, mode: "manual" | "automatic" = "manual") => setState((prev) => {
    if (prev.submissions.some((item) => item.testId === testId && item.studentId === CURRENT_STUDENT)) return prev;
    const test = prev.tests.find((item) => item.id === testId);
    if (!test) return prev;
    const key = examKey(testId); const answers = prev.answers[key] ?? {};
    const score = scoreExam(test.questions, answers);
    const submittedAt = new Date().toISOString();
    return {
      ...prev,
      submissions: [{ id: uid("sub"), testId, studentId: CURRENT_STUDENT, answers, flagged: prev.flags[key] ?? [], submittedAt, mode }, ...prev.submissions],
      results: [{ id: uid("res"), testId, studentId: CURRENT_STUDENT, score, total: test.totalMarks, submittedAt, mode }, ...prev.results],
      sessions: prev.sessions.map((session) =>
        session.testId === testId && session.studentId === CURRENT_STUDENT
          ? { ...session, examStatus: "submitted" as const }
          : session,
      ),
      audits: [
        { id: uid("audit"), at: submittedAt, actor: "Aarav Mehta · 23CSE1042", action: mode === "automatic" ? "Exam auto-submitted" : "Exam submitted", detail: `${test.title} received with ${Object.keys(answers).length} of ${test.questions.length} responses.`, category: "exam", severity: mode === "automatic" ? "warning" : "info" },
        ...prev.audits,
      ],
      toasts: [{ id: uid("toast"), title: "Submission received", message: "Your response receipt is now available.", tone: "success" }],
    };
  }), []);

  const setMockResultMode = useCallback((enabled: boolean) => setState((prev) => ({ ...prev, mockResultMode: enabled })), []);
  const dismissToast = useCallback((id: string) => setState((prev) => ({ ...prev, toasts: prev.toasts.filter((toast) => toast.id !== id) })), []);
  const resetDemo = useCallback(() => { const fresh = createSeedState(); setState(fresh); localStorage.removeItem(STORAGE_KEY); }, []);
  const value = useMemo(() => ({ state, hydrated, currentStudentId: CURRENT_STUDENT, createTest, scheduleExam, startExam, answerQuestion, flagQuestion, submitExam, setMockResultMode, dismissToast, resetDemo }), [state, hydrated, createTest, scheduleExam, startExam, answerQuestion, flagQuestion, submitExam, setMockResultMode, dismissToast, resetDemo]);
  return <ExamContext.Provider value={value}>{children}</ExamContext.Provider>;
}

export function useExam() {
  const value = useContext(ExamContext);
  if (!value) throw new Error("useExam must be used within ExamProvider");
  return value;
}

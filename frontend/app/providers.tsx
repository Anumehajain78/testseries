"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useSyncExternalStore, type ReactNode } from "react";
import { CURRENT_STUDENT_ID, api, examStore } from "@/lib/api";
import type { AnswerValue, ExamState, NewTestInput } from "@/lib/types";

// ---------------------------------------------------------------------------
// Exam provider
//
// Reads come from the store snapshot; writes go through the API client. The
// provider itself holds no state and performs no mutation, which is what makes
// the backend cutover a change of implementation rather than a rewrite here.
//
// Toast dismissal is the one exception: it is client-side UI chrome with no
// server counterpart, so it talks to the store directly.
// ---------------------------------------------------------------------------

type ExamContextValue = {
  state: ExamState;
  hydrated: boolean;
  currentStudentId: string;
  createTest: (input: NewTestInput) => Promise<string>;
  scheduleExam: (testId: string) => Promise<void>;
  startExam: (testId: string) => Promise<void>;
  answerQuestion: (testId: string, questionId: string, value: AnswerValue) => Promise<void>;
  flagQuestion: (testId: string, questionId: string) => Promise<void>;
  submitExam: (testId: string, mode?: "manual" | "automatic") => Promise<void>;
  setMockResultMode: (enabled: boolean) => Promise<void>;
  dismissToast: (id: string) => void;
  resetDemo: () => Promise<void>;
};

const ExamContext = createContext<ExamContextValue | null>(null);

export function ExamProvider({ children }: { children: ReactNode }) {
  const snapshot = useSyncExternalStore(
    examStore.subscribe,
    examStore.getSnapshot,
    examStore.getServerSnapshot,
  );

  // Adopting persisted state is a subscription to an external store, not a
  // render-time concern, so it happens once on mount. The store notifies its
  // subscribers when it lands.
  useEffect(() => { examStore.hydrate(); }, []);

  const createTest = useCallback(async (input: NewTestInput) => (await api.createExam(input)).examId, []);
  const scheduleExam = useCallback((testId: string) => api.scheduleExam(testId), []);
  const startExam = useCallback((testId: string) => api.startExam(testId), []);
  const answerQuestion = useCallback((testId: string, questionId: string, value: AnswerValue) => api.saveAnswer(testId, questionId, value), []);
  const flagQuestion = useCallback((testId: string, questionId: string) => api.toggleFlag(testId, questionId), []);
  const submitExam = useCallback(async (testId: string, mode: "manual" | "automatic" = "manual") => { await api.submitExam(testId, mode); }, []);
  const setMockResultMode = useCallback((enabled: boolean) => api.setResultsPublished(enabled), []);
  const resetDemo = useCallback(() => api.resetDemoData(), []);

  const dismissToast = useCallback((id: string) => {
    examStore.mutate((previous) => ({ ...previous, toasts: previous.toasts.filter((toast) => toast.id !== id) }));
  }, []);

  const value = useMemo<ExamContextValue>(() => ({
    state: snapshot.state,
    hydrated: snapshot.hydrated,
    currentStudentId: CURRENT_STUDENT_ID,
    createTest,
    scheduleExam,
    startExam,
    answerQuestion,
    flagQuestion,
    submitExam,
    setMockResultMode,
    dismissToast,
    resetDemo,
  }), [snapshot, createTest, scheduleExam, startExam, answerQuestion, flagQuestion, submitExam, setMockResultMode, dismissToast, resetDemo]);

  return <ExamContext.Provider value={value}>{children}</ExamContext.Provider>;
}

export function useExam() {
  const value = useContext(ExamContext);
  if (!value) throw new Error("useExam must be used within ExamProvider");
  return value;
}

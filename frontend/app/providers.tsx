"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import { API_MODE, ApiError, CURRENT_STUDENT_ID, api, examStore, loadStateFromServer, storeToken } from "@/lib/api";
import { ConnectionError, SignInGate } from "@/components/sign-in";
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

  // `mock` adopts browser-persisted state; `live` assembles the same shape from
  // the API. Either way the store notifies its subscribers when it lands, so
  // the screens below never learn which one they are reading.
  // Four distinct states, because collapsing them shows a sign-in form to
  // someone who is already signed in and merely waiting for a response.
  type Phase = "loading" | "ready" | "signed-out" | "error";
  const [phase, setPhase] = useState<Phase>(() => (API_MODE === "mock" ? "ready" : "loading"));
  const [loadError, setLoadError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (API_MODE === "mock") {
      examStore.hydrate();
      return;
    }
    let cancelled = false;
    loadStateFromServer()
      .then((state) => {
        if (cancelled) return;
        examStore.adoptServerState(state as ExamState);
        setPhase("ready");
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        // An expired or rejected token means sign in again rather than retry
        // into a loop; anything else is a reachability problem worth naming.
        if (cause instanceof ApiError && cause.status === 401) {
          storeToken(null);
          setPhase("signed-out");
          return;
        }
        setLoadError(
          cause instanceof ApiError
            ? `The examination server returned ${cause.status}.`
            : "The examination server is unreachable.",
        );
        setPhase("error");
      });
    return () => { cancelled = true; };
  }, [attempt]);

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

  if (API_MODE === "live") {
    if (phase === "error") {
      return <ConnectionError message={loadError ?? "Unknown error"} onRetry={() => { setPhase("loading"); setAttempt((n) => n + 1); }} />;
    }
    if (phase === "signed-out") {
      return <SignInGate onSignedIn={() => { setPhase("loading"); setAttempt((n) => n + 1); }} />;
    }
    if (phase === "loading") {
      return <div className="loading-state"><span className="spinner"/><p>Synchronizing with the examination server…</p></div>;
    }
  }

  return <ExamContext.Provider value={value}>{children}</ExamContext.Provider>;
}

export function useExam() {
  const value = useContext(ExamContext);
  if (!value) throw new Error("useExam must be used within ExamProvider");
  return value;
}

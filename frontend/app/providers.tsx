"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import { API_MODE, ApiError, CURRENT_STUDENT_ID, api, examStore, loadStateFromServer, readUser, storeToken } from "@/lib/api";
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
  /** Re-read the server snapshot. No-op in mock mode. */
  refreshFromServer: () => Promise<void>;
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

  // A write the server refuses must say so. Silently doing nothing is the
  // worst possible behaviour in an exam hall: an invigilator presses Start,
  // sees no change, and has no idea whether the room is running.
  const guard = useCallback(async <T,>(action: () => Promise<T>): Promise<T> => {
    try {
      return await action();
    } catch (cause) {
      examStore.mutate((previous) => ({
        ...previous,
        toasts: [{
          id: `err-${Date.now()}`,
          title: "That did not go through",
          message: cause instanceof Error ? cause.message : "The examination server refused the request.",
          tone: "warning" as const,
        }],
      }));
      throw cause;
    }
  }, []);

  const createTest = useCallback(async (input: NewTestInput) => (await guard(() => api.createExam(input))).examId, [guard]);
  const scheduleExam = useCallback((testId: string) => guard(() => api.scheduleExam(testId)), [guard]);
  const startExam = useCallback((testId: string) => guard(() => api.startExam(testId)), [guard]);
  const answerQuestion = useCallback((testId: string, questionId: string, value: AnswerValue) => guard(() => api.saveAnswer(testId, questionId, value)), [guard]);
  const flagQuestion = useCallback((testId: string, questionId: string) => guard(() => api.toggleFlag(testId, questionId)), [guard]);
  const submitExam = useCallback(async (testId: string, mode: "manual" | "automatic" = "manual") => { await guard(() => api.submitExam(testId, mode)); }, [guard]);
  const setMockResultMode = useCallback((enabled: boolean) => guard(() => api.setResultsPublished(enabled)), [guard]);
  const resetDemo = useCallback(() => guard(() => api.resetDemoData()), [guard]);

  // Adopt a fresh server snapshot without disturbing the sign-in flow. Used by
  // the live monitor when the socket says something changed.
  const refreshFromServer = useCallback(async () => {
    if (API_MODE !== "live") return;
    try {
      examStore.adoptServerState((await loadStateFromServer()) as ExamState);
    } catch {
      // A failed refresh leaves the last good snapshot on screen, which beats
      // blanking a monitor mid-examination.
    }
  }, []);

  const dismissToast = useCallback((id: string) => {
    examStore.mutate((previous) => ({ ...previous, toasts: previous.toasts.filter((toast) => toast.id !== id) }));
  }, []);

  const value = useMemo<ExamContextValue>(() => ({
    state: snapshot.state,
    hydrated: snapshot.hydrated,
    // In live mode this is whoever signed in; the mock's fixed candidate only
    // applies when there is no server to ask.
    currentStudentId: API_MODE === "live" ? (readUser()?.id ?? CURRENT_STUDENT_ID) : CURRENT_STUDENT_ID,
    createTest,
    scheduleExam,
    startExam,
    answerQuestion,
    flagQuestion,
    submitExam,
    setMockResultMode,
    dismissToast,
    resetDemo,
    refreshFromServer,
  }), [snapshot, createTest, scheduleExam, startExam, answerQuestion, flagQuestion, submitExam, setMockResultMode, dismissToast, resetDemo, refreshFromServer]);

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

import type { ExamState } from "@/lib/types";

// ---------------------------------------------------------------------------
// Snapshot store
//
// A thin external store the screens read synchronously via
// `useSyncExternalStore`. It holds whatever the API last returned and nothing
// else: there is no seed, and nothing is written to browser storage.
//
// That last point is deliberate. Persisting exam state locally would mean a
// candidate's machine holding a copy of a paper, and a stale copy at that —
// the server is the only place exam state lives, and a reload re-reads it.
// ---------------------------------------------------------------------------

export interface StoreSnapshot {
  state: ExamState;
  /** False until the first server snapshot has been adopted. */
  hydrated: boolean;
}

type Listener = () => void;

/** Nothing is known until the server says otherwise. */
export function emptyExamState(): ExamState {
  return {
    version: 2,
    tests: [],
    students: [],
    labs: [],
    computers: [],
    sessions: [],
    results: [],
    audits: [],
    submissions: [],
    answers: {},
    flags: {},
    toasts: [],
    resultsPublished: false,
  };
}

// Held as a stable reference: getServerSnapshot must never return a new object
// or React re-renders forever.
const initial: StoreSnapshot = { state: emptyExamState(), hydrated: false };

let snapshot: StoreSnapshot = initial;
let listeners: Listener[] = [];

function commit(state: ExamState, hydrated: boolean) {
  snapshot = { state, hydrated };
  for (const listener of listeners) listener();
}

export const examStore = {
  subscribe(listener: Listener) {
    listeners.push(listener);
    return () => {
      listeners = listeners.filter((item) => item !== listener);
    };
  },

  getSnapshot(): StoreSnapshot {
    return snapshot;
  },

  getServerSnapshot(): StoreSnapshot {
    return initial;
  },

  /** Adopt a snapshot assembled from the API. */
  adoptServerState(state: ExamState) {
    commit(state, true);
  },

  /** Local-only changes: toasts, and the optimistic echo of a saved answer. */
  mutate(recipe: (previous: ExamState) => ExamState): ExamState {
    const next = recipe(snapshot.state);
    if (next === snapshot.state) return next;
    commit(next, snapshot.hydrated);
    return next;
  },

  /** Drop everything on sign-out, so the next account starts clean. */
  clear() {
    snapshot = initial;
    for (const listener of listeners) listener();
  },
};

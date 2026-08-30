import { createSeedState } from "@/lib/mock-data";
import type { ExamState } from "@/lib/types";

// ---------------------------------------------------------------------------
// Mock store
//
// The demo's state container, lifted out of React so it can be driven by the
// API client rather than by components. It is an external store in the precise
// sense React means: `useSyncExternalStore` subscribes to it, which is why the
// provider no longer calls setState from an effect.
//
// When the HTTP client lands (migration step 04) this file's job shrinks to
// nothing — the server becomes the store and this is deleted along with
// `mock-data.ts`.
// ---------------------------------------------------------------------------

const STORAGE_KEY = "northbridge-exam-control-v2";

export interface StoreSnapshot {
  state: ExamState;
  /** False until the browser's persisted state has been adopted. Components
   *  render a loading state meanwhile, which is what keeps the server and
   *  client markup identical on first paint. */
  hydrated: boolean;
}

type Listener = () => void;

function readPersisted(raw: string | null): ExamState | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as ExamState;
    return parsed.version === 2 && Array.isArray(parsed.tests) ? parsed : null;
  } catch {
    return null;
  }
}

// Seeded once per process, mirroring the previous `useState(createSeedState)`.
// Held as a stable reference because getServerSnapshot must never return a new
// object — React re-renders forever if it does.
const seedSnapshot: StoreSnapshot = { state: createSeedState(), hydrated: false };

let snapshot: StoreSnapshot = seedSnapshot;
let listeners: Listener[] = [];
let hydrating = false;

function emit() {
  for (const listener of listeners) listener();
}

// Replace the snapshot wholesale so identity changes exactly when content does.
function commit(state: ExamState, hydrated: boolean) {
  snapshot = { state, hydrated };
  emit();
}

function persist(state: ExamState) {
  try {
    // Toasts are transient UI, never restored across reloads.
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...state, toasts: [] }));
  } catch {
    // A full or unavailable quota must not take the exam down.
  }
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
    return seedSnapshot;
  },

  // Adopt persisted state and begin listening for changes made in other tabs.
  // Idempotent, so React's double-invoked effects in development are harmless.
  hydrate() {
    if (hydrating) return;
    hydrating = true;
    const stored = readPersisted(localStorage.getItem(STORAGE_KEY));
    commit(stored ?? snapshot.state, true);
    window.addEventListener("storage", (event) => {
      if (event.key !== STORAGE_KEY) return;
      const next = readPersisted(event.newValue);
      if (next) commit(next, true);
    });
  },

  // The single write path. Every mutation persists and notifies, so callers
  // never have to remember to do either.
  mutate(recipe: (previous: ExamState) => ExamState): ExamState {
    const next = recipe(snapshot.state);
    if (next === snapshot.state) return next;
    commit(next, snapshot.hydrated);
    if (snapshot.hydrated) persist(next);
    return next;
  },

  reset() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Ignore — the in-memory reset below is what the user actually sees.
    }
    commit(createSeedState(), true);
  },
};

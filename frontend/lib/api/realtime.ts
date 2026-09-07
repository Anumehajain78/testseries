import { readToken } from "./http";

// ---------------------------------------------------------------------------
// Monitor socket
//
// An accelerator, never the source of truth. Frames say *that* something
// changed; the snapshot endpoint says *what* it changed to. Acting on a frame
// therefore means refetching, which keeps one reducer for both paths and means
// a dropped frame costs latency rather than correctness.
//
// The server drops frames to slow consumers on purpose, so a gap in `seq` is
// expected rather than exceptional — and is handled the same way as everything
// else: refetch.
// ---------------------------------------------------------------------------

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

function socketUrl(examId: string, token: string): string {
  const http = BASE_URL.replace(/\/api\/v1\/?$/, "");
  const ws = http.replace(/^http/, "ws");
  return `${ws}/ws/exams/${examId}/monitor?token=${encodeURIComponent(token)}`;
}

export interface MonitorSocketOptions {
  /** Called when the server says something changed. */
  onChange: () => void;
  /** Connection state, for the "live" vs "polling" indicator. */
  onStatus?: (connected: boolean) => void;
}

export interface MonitorSocket {
  close: () => void;
}

/**
 * Watch one exam.
 *
 * Reconnects with backoff, and while disconnected the caller's polling
 * interval carries the load — which is why losing the socket degrades the
 * refresh rate rather than the correctness of what is shown.
 */
export function watchExam(examId: string, options: MonitorSocketOptions): MonitorSocket {
  let socket: WebSocket | null = null;
  let closed = false;
  let attempt = 0;
  let retry: ReturnType<typeof setTimeout> | null = null;
  let lastSeq: number | null = null;

  const open = () => {
    if (closed) return;
    const token = readToken();
    if (!token) return;

    try {
      socket = new WebSocket(socketUrl(examId, token));
    } catch {
      schedule();
      return;
    }

    socket.onopen = () => {
      attempt = 0;
      options.onStatus?.(true);
    };

    socket.onmessage = (message) => {
      let frame: { event?: string; seq?: number };
      try {
        frame = JSON.parse(message.data as string);
      } catch {
        return;
      }
      // Keepalives prove the socket is alive and mean nothing changed.
      if (frame.event === "HEARTBEAT") return;

      if (typeof frame.seq === "number") {
        if (lastSeq !== null && frame.seq <= lastSeq) return; // already seen
        lastSeq = frame.seq;
      }
      options.onChange();
    };

    socket.onclose = () => {
      options.onStatus?.(false);
      socket = null;
      schedule();
    };

    // `onerror` is always followed by `onclose`, so reconnection is handled
    // in one place rather than twice.
    socket.onerror = () => {};
  };

  const schedule = () => {
    if (closed || retry) return;
    // Backoff to 10s: a lab of sixty machines must not stampede a server that
    // has just come back up.
    const delay = Math.min(1000 * 2 ** attempt, 10_000);
    attempt += 1;
    retry = setTimeout(() => {
      retry = null;
      open();
    }, delay);
  };

  open();

  return {
    close() {
      closed = true;
      if (retry) clearTimeout(retry);
      socket?.close();
      socket = null;
    },
  };
}

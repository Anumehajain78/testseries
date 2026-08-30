// Pure, server-replaceable exam timer math (Req 18).
// Remaining time is always derived from a shared session end time (`endsAt`)
// rather than a per-client countdown origin, so it can later be driven by
// server time without changing consumers.

// Warning Threshold is 10 minutes; Urgent is the final minute (Req 18.3).
export const WARNING_THRESHOLD_SECONDS = 600;
export const URGENT_THRESHOLD_SECONDS = 60;

// Remaining whole seconds from `endsAt`, clamped at zero (Req 18.1).
export function remainingSeconds(endsAt: string | undefined, nowMs: number = Date.now()): number {
  if (!endsAt) return 0;
  return Math.max(0, Math.ceil((new Date(endsAt).getTime() - nowMs) / 1000));
}

// Timer is in warning state once remaining time falls below the threshold (Req 18.3).
export function isWarning(remaining: number): boolean {
  return remaining > 0 && remaining <= WARNING_THRESHOLD_SECONDS;
}

export function isUrgent(remaining: number): boolean {
  return remaining > 0 && remaining <= URGENT_THRESHOLD_SECONDS;
}

export interface TimerState {
  remaining: number;
  warning: boolean;
  urgent: boolean;
}

export function computeTimerState(endsAt: string | undefined, nowMs: number = Date.now()): TimerState {
  const remaining = remainingSeconds(endsAt, nowMs);
  return { remaining, warning: isWarning(remaining), urgent: isUrgent(remaining) };
}

// Guards expiry so the handler fires exactly once even though the timer ticks
// repeatedly at zero (Req 18.4). Reset when the session end time changes.
export function createExpiryGuard() {
  let fired = false;
  return {
    reset() {
      fired = false;
    },
    // Returns true only on the first tick where remaining reaches zero.
    shouldExpire(remaining: number, endsAt: string | undefined): boolean {
      if (remaining === 0 && endsAt && !fired) {
        fired = true;
        return true;
      }
      return false;
    },
  };
}

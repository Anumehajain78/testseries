// ---------------------------------------------------------------------------
// Password rules, and the words used to refuse
//
// Policy kept away from the components that enforce it, in the same spirit as
// access.ts: the form decides what to render, this decides what is acceptable
// and what a person is told when it is not.
//
// The checks here are a courtesy, not the rule. The server applies its own and
// is the one that counts; doing them locally only saves somebody a round trip
// to be told their two new passwords differ.
// ---------------------------------------------------------------------------

/**
 * What the sign-in screen says when it refuses a credential.
 *
 * Exported so that changing your own password can refuse with the identical
 * sentence. A wrong current password and a wrong new one must be
 * indistinguishable from outside: anything more specific tells whoever is at a
 * shared lab machine that the password they guessed was almost right, which is
 * exactly the fact worth withholding.
 */
export const SIGN_IN_REFUSAL = "Incorrect email or password";

/** Matches the server's minimum. Stated in the form rather than discovered
 *  from a 422, because being told the rule after failing it is worse. */
export const MIN_PASSWORD_LENGTH = 8;

/**
 * Whatever is wrong with a change-password form, or null when nothing is.
 *
 * Length is reported before the mismatch: two identical four-character
 * passwords match each other perfectly, and "they do not match" would send
 * somebody looking for a typo that is not there.
 */
export function checkNewPassword(current: string, next: string, confirm: string): string | null {
  if (!current) return "Enter your current password.";
  if (next.length < MIN_PASSWORD_LENGTH) {
    return `The new password needs to be at least ${MIN_PASSWORD_LENGTH} characters long.`;
  }
  if (next === current) return "The new password has to be different from the current one.";
  if (next !== confirm) return "The two new passwords do not match.";
  return null;
}

/**
 * What to tell somebody about the sign-ins a password change has just ended.
 *
 * One function for both screens so the self-service change and a reset done at
 * a counter report the same fact the same way — leading with the count, then
 * what it means. They are the same event seen from two sides, and two
 * wordings would drift into disagreeing about what the number counts.
 *
 * Zero is said out loud rather than skipped. "They were not signed in
 * anywhere" is the reassurance an exam cell wants after resetting the password
 * of somebody they hope was not mid-paper; silence leaves them wondering.
 *
 * Above one the count is the point. It is how somebody finds out their own
 * account was open on machines they had forgotten about, and how an exam cell
 * finds out a reset just ejected four live sign-ins — which is either exactly
 * what they meant or a sign they picked the wrong row.
 */
export function sessionsEndedNote(sessionsEnded: number, whose: "yours" | "theirs"): string {
  if (whose === "theirs") {
    if (sessionsEnded > 1) {
      return `${sessionsEnded} sign-ins were ended — every device this candidate was signed in on. If one of them was an examination in progress, they are out of it now.`;
    }
    if (sessionsEnded === 1) {
      return "One sign-in was ended: the single device this candidate was signed in on. If that was an examination in progress, they are out of it now.";
    }
    return "No sign-ins were ended — this candidate was not signed in anywhere, so nothing was interrupted.";
  }

  if (sessionsEnded > 1) {
    return `${sessionsEnded} sign-ins were ended, this screen among them. Anywhere else this account was signed in has been signed out too.`;
  }
  if (sessionsEnded === 1) return "One sign-in was ended: this screen.";
  return "No sign-ins were ended — there was nothing left open anywhere.";
}

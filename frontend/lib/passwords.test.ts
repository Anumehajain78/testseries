import { describe, expect, it } from "vitest";
import { MIN_PASSWORD_LENGTH, checkNewPassword, sessionsEndedNote } from "./passwords";

describe("checkNewPassword", () => {
  it("accepts a different password of a usable length", () => {
    expect(checkNewPassword("old-password", "new-password", "new-password")).toBeNull();
  });

  it("asks for the current password first", () => {
    // The field the server needs and the one people skip, having just proved
    // to themselves that they are signed in.
    expect(checkNewPassword("", "new-password", "new-password")).toMatch(/current password/i);
  });

  it("reports a short password as short, not as a mismatch", () => {
    // Two identical four-character passwords match each other perfectly.
    // "They do not match" would send somebody hunting for a typo that is not
    // there, which is the failure this ordering exists to prevent.
    const problem = checkNewPassword("old-password", "abcd", "abcd");
    expect(problem).toMatch(new RegExp(`${MIN_PASSWORD_LENGTH} characters`));
  });

  it("refuses a new password identical to the current one", () => {
    expect(checkNewPassword("same-password", "same-password", "same-password"))
      .toMatch(/different/i);
  });

  it("catches a mistyped confirmation", () => {
    expect(checkNewPassword("old-password", "new-password", "new-passwrod"))
      .toMatch(/do not match/i);
  });
});

describe("sessionsEndedNote", () => {
  it("names the count when several sessions went", () => {
    // The number is the only way somebody learns their account was open on
    // machines they had forgotten about.
    expect(sessionsEndedNote(4, "yours")).toContain("4 sign-ins");
    expect(sessionsEndedNote(4, "theirs")).toContain("4 sign-ins");
  });

  it("does not say 1 sign-ins", () => {
    expect(sessionsEndedNote(1, "yours")).toBe("One sign-in was ended: this screen.");
    expect(sessionsEndedNote(1, "theirs")).toMatch(/^One sign-in was ended/);
  });

  it("says plainly that nobody was signed in anywhere", () => {
    // Reassurance after a reset, and silence is not reassuring: an exam cell
    // that has just reset a password wants to know nothing was interrupted.
    expect(sessionsEndedNote(0, "theirs")).toMatch(/not signed in anywhere/i);
    expect(sessionsEndedNote(0, "yours")).toMatch(/^No sign-ins were ended/);
  });

  it("leads with the count on both sides, so the two screens read alike", () => {
    // The self-service change and a reset at the counter report the same event
    // seen from two ends. Separate wordings would drift into disagreeing about
    // what the number counts.
    for (const count of [0, 1, 5]) {
      expect(sessionsEndedNote(count, "yours")).toMatch(/^(No|One|\d+) sign-ins? (was|were) ended/);
      expect(sessionsEndedNote(count, "theirs")).toMatch(/^(No|One|\d+) sign-ins? (was|were) ended/);
    }
  });

  it("speaks about the candidate, not the person at the keyboard, on a reset", () => {
    // Said the "yours" way, a reset would tell an administrator that their own
    // screen had just been signed out.
    expect(sessionsEndedNote(3, "theirs")).not.toMatch(/this screen/i);
    expect(sessionsEndedNote(3, "theirs")).toContain("candidate");
  });
});

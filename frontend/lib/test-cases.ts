import type { AuthoredCodingTestCase, CodingTestCase } from "./types";

// ---------------------------------------------------------------------------
// Authoring a coding question's test cases
//
// Shared by the two places a test case is written: the assessment builder,
// where the paper is being composed, and the correction editor, where a case
// that marked a whole cohort wrongly is being repaired after the exam. They
// are different screens doing the same dangerous thing, and a rule that held
// in one and not the other — "an empty expected output has to be chosen" above
// all — would make the repair the way to smuggle in a broken key.
//
// `expectsNoOutput` is form state and never leaves the browser. The server
// requires `expectedStdout` and takes an empty string at face value, so "this
// program should print nothing" and "nobody has filled this in yet" are the
// same bytes on the wire. This flag is how an author says which one they
// meant; without it, a half-written case saves as one that awards full marks
// to a program that prints nothing at all.
// ---------------------------------------------------------------------------

export type BuilderTestCase = AuthoredCodingTestCase & { expectsNoOutput: boolean };

/**
 * A fresh case.
 *
 * The first is the worked example the candidate is shown; everything after it
 * is hidden unless someone deliberately reveals it. A paper whose every case
 * is visible tells a candidate exactly what their program will be judged on,
 * and that default should never be reached by accident.
 */
export const blankTestCase = (index: number): BuilderTestCase => ({
  stdin: "", expectedStdout: "", hidden: index > 0, weight: 1, expectsNoOutput: false,
});

/**
 * An existing case, opened for editing.
 *
 * The three optional fields are narrowed rather than defaulted, because on a
 * candidate's paper they were never sent at all. Filling a missing one in
 * would quietly publish a hidden case or blank an answer key on the next save,
 * so an absent expected output reads as "nobody has written this yet" and an
 * absent visibility reads as hidden until someone says otherwise.
 */
export const builderTestCase = (test: CodingTestCase): BuilderTestCase => ({
  stdin: test.stdin,
  expectedStdout: test.expectedStdout ?? "",
  hidden: test.hidden ?? true,
  weight: test.weight ?? 1,
  expectsNoOutput: (test.expectedStdout ?? "") === "",
});

/** What goes on the wire. `expectsNoOutput` is the author's answer to the
 *  ambiguity, not a field the server has ever heard of. */
export const authoredTestCase = ({ expectsNoOutput, ...test }: BuilderTestCase): AuthoredCodingTestCase => ({
  ...test,
  expectedStdout: expectsNoOutput ? "" : test.expectedStdout,
  weight: Number(test.weight),
});

/**
 * The first thing wrong with a set of cases, said to the person writing them,
 * or null when there is nothing wrong.
 *
 * One message at a time on purpose: these are fixed one case at a time, and a
 * list of three complaints about a form of six cases is harder to act on than
 * the next thing to do.
 */
export function testCaseProblem(tests: BuilderTestCase[]): string | null {
  // A question with no cases cannot be scored at all — the runner has nothing
  // to compare a program against, so every program is as good as every other.
  if (!tests.length) return "Add at least one test case — the tests are how this question is marked.";
  // Whitespace-only counts as empty because the runner normalises it away
  // before comparing, so it would pass every program that printed nothing —
  // exactly the trap the flag exists to make explicit.
  if (tests.some((test) => !test.expectsNoOutput && !test.expectedStdout.trim())) {
    return "Give every test case the output it should produce, or tick that it expects none.";
  }
  if (tests.some((test) => !(Number(test.weight) > 0))) return "Every test case needs a weight above zero.";
  return null;
}

/** The server's bounds on a correction's reason, checked here so somebody who
 *  has just rewritten six cases is told before the request rather than after
 *  it is refused. */
export const REASON_MIN = 3;
export const REASON_MAX = 500;

/** Why the reason is not yet acceptable, or null. The wording avoids "field"
 *  and "valid": this goes in front of a faculty member who is explaining
 *  themselves to whoever reads the audit trail next year. */
export function reasonProblem(reason: string): string | null {
  const written = reason.trim();
  if (!written) return "Say why these cases are being corrected. It goes on the record against your name.";
  if (written.length < REASON_MIN) return `That is too short to mean anything later — at least ${REASON_MIN} characters.`;
  if (written.length > REASON_MAX) return `Keep it under ${REASON_MAX} characters; this one is ${written.length}.`;
  return null;
}

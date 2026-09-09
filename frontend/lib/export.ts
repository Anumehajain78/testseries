import type { ExamState, Result, Test } from "./types";
import { formatDateTime, percentage } from "./format";

// ---------------------------------------------------------------------------
// Results export
//
// The assembly lives here rather than in the screen so it can be tested: a
// results file goes into a department's records, and a quoting mistake that
// shifts one candidate's marks into another's row is not something to discover
// after the marks have been entered somewhere else.
// ---------------------------------------------------------------------------

export const RESULT_COLUMNS = [
  "Rank", "Roll number", "Candidate", "Assessment",
  "Score", "Out of", "Percentage", "Submitted", "Status",
] as const;

/** Quote a field whenever it could otherwise break the file. A candidate named
 *  "Rao, Anita" splits into two columns unless it is quoted. */
export function csvField(value: string | number): string {
  const text = String(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** Released marks as CSV.
 *
 * Released marks only. A withheld score is not a number, and writing it out as
 * a blank or a nought is how a mark nobody published ends up in a register.
 */
export function resultsToCsv(
  ranked: Array<{ result: Result; score: number; rank: number }>,
  state: Pick<ExamState, "students" | "tests">,
): string {
  const lines = ranked.map(({ result, score, rank }) => {
    const student = state.students.find((s) => s.id === result.studentId);
    const test = state.tests.find((t) => t.id === result.testId);
    return [
      rank,
      student?.registrationNo ?? "",
      student?.name ?? "",
      test?.title ?? "",
      score,
      result.total,
      percentage(score, result.total),
      formatDateTime(result.submittedAt),
      result.mode === "automatic" ? "Auto-submitted" : "Submitted",
    ].map(csvField).join(",");
  });
  return [RESULT_COLUMNS.join(","), ...lines].join("\n");
}

export const resultsFileName = (chosen?: Test) =>
  `${chosen?.code ?? "all-assessments"}-results.csv`;

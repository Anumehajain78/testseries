import { describe, expect, it } from "vitest";
import { csvField, resultsFileName, resultsToCsv } from "./export";
import type { Result, Student, Test } from "./types";

const student = (id: string, name: string, registrationNo: string) =>
  ({ id, name, registrationNo, email: `${id}@northbridge.edu`, program: "B.Tech CSE", semester: 3, section: "A", status: "eligible" } as unknown as Student);

const test = (id: string, title: string, code = "CS201") =>
  ({ id, title, code } as unknown as Test);

const result = (over: Partial<Result> = {}): Result => ({
  id: "r1",
  testId: "t1",
  studentId: "s1",
  score: 14,
  total: 20,
  submittedAt: "2026-09-09T10:30:00Z",
  mode: "manual",
  ...over,
});

const state = {
  students: [student("s1", "Aarav Mehta", "23CSE1001"), student("s2", "Rao, Anita", "23CSE1002")],
  tests: [test("t1", "Data Structures")],
};

describe("csvField", () => {
  it("leaves an ordinary value alone", () => {
    expect(csvField("Aarav Mehta")).toBe("Aarav Mehta");
    expect(csvField(14)).toBe("14");
  });

  it("quotes a value containing a comma", () => {
    // Otherwise this candidate's name becomes two columns and every mark
    // after it shifts one place to the right.
    expect(csvField("Rao, Anita")).toBe('"Rao, Anita"');
  });

  it("doubles an embedded quote", () => {
    expect(csvField('She said "hello"')).toBe('"She said ""hello"""');
  });

  it("quotes a value containing a newline", () => {
    expect(csvField("line one\nline two")).toBe('"line one\nline two"');
  });
});

describe("resultsToCsv", () => {
  it("writes a header and one line per candidate", () => {
    const csv = resultsToCsv(
      [{ result: result(), score: 14, rank: 1 }],
      state,
    );
    const [header, row] = csv.split("\n");
    expect(header.startsWith("Rank,Roll number,Candidate")).toBe(true);
    expect(row).toContain("23CSE1001");
    expect(row).toContain("Aarav Mehta");
    expect(row).toContain("14,20,70");
  });

  it("keeps a comma in a name inside one column", () => {
    const csv = resultsToCsv(
      [{ result: result({ studentId: "s2" }), score: 10, rank: 1 }],
      state,
    );
    expect(csv).toContain('"Rao, Anita"');
  });

  it("writes only a header when nothing has been released", () => {
    expect(resultsToCsv([], state).split("\n")).toHaveLength(1);
  });

  it("names the file after the assessment, or says it is all of them", () => {
    expect(resultsFileName(test("t1", "Data Structures", "CS201"))).toBe("CS201-results.csv");
    expect(resultsFileName()).toBe("all-assessments-results.csv");
  });
});

import { describe, expect, it } from "vitest";
import { authoredTestCase, blankTestCase, builderTestCase, reasonProblem, testCaseProblem, type BuilderTestCase } from "./test-cases";

const written = (overrides: Partial<BuilderTestCase> = {}): BuilderTestCase => ({
  stdin: "4",
  expectedStdout: "10",
  hidden: true,
  weight: 1,
  expectsNoOutput: false,
  ...overrides,
});

describe("blankTestCase", () => {
  it("shows the first case to candidates and hides the rest", () => {
    expect(blankTestCase(0).hidden).toBe(false);
    expect(blankTestCase(1).hidden).toBe(true);
    expect(blankTestCase(7).hidden).toBe(true);
  });
});

describe("builderTestCase", () => {
  it("reads back a stored case as written", () => {
    expect(builderTestCase({ position: 1, stdin: "4", expectedStdout: "10", hidden: false, weight: 3 })).toEqual({
      stdin: "4", expectedStdout: "10", hidden: false, weight: 3, expectsNoOutput: false,
    });
  });

  it("treats a stored empty expected output as the deliberate kind", () => {
    expect(builderTestCase({ position: 1, stdin: "", expectedStdout: "", hidden: true, weight: 1 }).expectsNoOutput).toBe(true);
  });

  // A candidate's paper carries neither the key nor the visibility flag. Both
  // fallbacks have to be the cautious reading: nothing written yet, and hidden.
  it("defaults a withheld case to unwritten and hidden", () => {
    const test = builderTestCase({ position: 1, stdin: "4" });
    expect(test.hidden).toBe(true);
    expect(test.expectedStdout).toBe("");
    expect(test.weight).toBe(1);
  });
});

describe("authoredTestCase", () => {
  it("drops the form-only flag and keeps the written output", () => {
    expect(authoredTestCase(written())).toEqual({ stdin: "4", expectedStdout: "10", hidden: true, weight: 1 });
  });

  // The flag is the author's answer to "prints nothing" versus "not filled in",
  // so ticking it has to win over whatever is still sitting in the box.
  it("sends an empty expected output when the case expects none", () => {
    expect(authoredTestCase(written({ expectsNoOutput: true, expectedStdout: "leftover" })).expectedStdout).toBe("");
  });

  it("sends the weight as a number even when the input handed back a string", () => {
    expect(authoredTestCase(written({ weight: "3" as unknown as number })).weight).toBe(3);
  });
});

describe("testCaseProblem", () => {
  it("accepts a written set of cases", () => {
    expect(testCaseProblem([written(), written({ expectsNoOutput: true, expectedStdout: "" })])).toBeNull();
  });

  it("refuses a question with no cases at all", () => {
    expect(testCaseProblem([])).toMatch(/at least one test case/);
  });

  // Whitespace is normalised away before comparing, so a case expecting only
  // spaces would pass every program that printed nothing.
  it("refuses an expected output that is blank but not declared blank", () => {
    expect(testCaseProblem([written({ expectedStdout: "   " })])).toMatch(/output it should produce/);
    expect(testCaseProblem([written({ expectedStdout: "" })])).toMatch(/output it should produce/);
  });

  it("refuses a weight that cannot carry marks", () => {
    expect(testCaseProblem([written({ weight: 0 })])).toMatch(/above zero/);
    expect(testCaseProblem([written({ weight: -1 })])).toMatch(/above zero/);
    expect(testCaseProblem([written({ weight: Number.NaN })])).toMatch(/above zero/);
  });
});

describe("reasonProblem", () => {
  it("accepts a reason somebody could act on later", () => {
    expect(reasonProblem("Case 3 expected the wrong padding.")).toBeNull();
  });

  it("refuses a reason that is only whitespace", () => {
    expect(reasonProblem("   ")).toMatch(/on the record/);
  });

  it("refuses one too short to mean anything", () => {
    expect(reasonProblem("ok")).toMatch(/too short/);
  });

  it("refuses one longer than the server will take", () => {
    expect(reasonProblem("x".repeat(501))).toMatch(/501/);
    expect(reasonProblem("x".repeat(500))).toBeNull();
  });
});

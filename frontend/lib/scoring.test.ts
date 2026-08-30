import { describe, expect, it } from "vitest";
import { scoreAnswer, scoreExam } from "./scoring";
import type { Question } from "./types";

const mcq: Question = {
  id: "q1",
  type: "mcq",
  prompt: "Single choice",
  options: ["A", "B", "C"],
  correctOption: 1,
  marks: 4,
};

const multi: Question = {
  id: "q2",
  type: "multiple",
  prompt: "Multi select",
  options: ["A", "B", "C", "D"],
  correctOptions: [0, 2],
  marks: 5,
};

const text: Question = {
  id: "q3",
  type: "text",
  prompt: "Explain",
  options: [],
  marks: 3,
};

describe("scoreAnswer (Req 13.4, 14.2)", () => {
  it("awards MCQ marks for the correct single option", () => {
    expect(scoreAnswer(mcq, { kind: "single", option: 1 })).toBe(4);
  });

  it("awards nothing for a wrong MCQ option", () => {
    expect(scoreAnswer(mcq, { kind: "single", option: 0 })).toBe(0);
  });

  it("awards multi-select marks only on an exact set match, order independent", () => {
    expect(scoreAnswer(multi, { kind: "multiple", options: [2, 0] })).toBe(5);
  });

  it("awards nothing for a partial multi-select match", () => {
    expect(scoreAnswer(multi, { kind: "multiple", options: [0] })).toBe(0);
  });

  it("awards nothing for a superset multi-select answer", () => {
    expect(scoreAnswer(multi, { kind: "multiple", options: [0, 1, 2] })).toBe(0);
  });

  it("leaves text answers ungraded", () => {
    expect(scoreAnswer(text, { kind: "text", text: "anything" })).toBe(0);
  });

  it("awards nothing when no answer is present", () => {
    expect(scoreAnswer(mcq, undefined)).toBe(0);
  });
});

describe("scoreExam", () => {
  it("sums per-question scores across mixed question types", () => {
    const score = scoreExam([mcq, multi, text], {
      q1: { kind: "single", option: 1 },
      q2: { kind: "multiple", options: [0, 2] },
      q3: { kind: "text", text: "essay" },
    });
    expect(score).toBe(9);
  });
});

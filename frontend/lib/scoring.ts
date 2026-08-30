import type { AnswerValue, Question } from "./types";

// Score a single question against a normalized answer, supporting every type
// (Req 13.4, 14.2). MCQ matches a single option, multi-select requires an exact
// set match, and text answers are ungraded in this phase.
export function scoreAnswer(question: Question, answer: AnswerValue | undefined): number {
  if (!answer) return 0;
  if (question.type === "mcq" && answer.kind === "single") {
    return answer.option === question.correctOption ? question.marks : 0;
  }
  if (question.type === "multiple" && answer.kind === "multiple") {
    const correct = [...(question.correctOptions ?? [])].sort((a, b) => a - b);
    const given = [...answer.options].sort((a, b) => a - b);
    const matches = correct.length === given.length && correct.every((value, i) => value === given[i]);
    return matches ? question.marks : 0;
  }
  // Text answers are ungraded in this phase.
  return 0;
}

// Total score for a test given a per-question answer map (mirrors submitExam).
export function scoreExam(questions: Question[], answers: Record<string, AnswerValue>): number {
  return questions.reduce((sum, question) => sum + scoreAnswer(question, answers[question.id]), 0);
}

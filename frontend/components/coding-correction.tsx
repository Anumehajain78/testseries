"use client";

import { useMemo, useState } from "react";
import { ApiError, coding, type CodingReportDto, type TestCaseCorrectionResultDto } from "@/lib/api";
import { authoredTestCase, blankTestCase, builderTestCase, reasonProblem, REASON_MAX, testCaseProblem, type BuilderTestCase } from "@/lib/test-cases";
import type { Question, Test } from "@/lib/types";
import { Icon } from "./icons";
import { HiddenCaseCount, TestCaseFields } from "./test-cases";
import { Badge, Button, Card, Modal } from "./ui";

// ---------------------------------------------------------------------------
// Correcting a coding question's test cases
//
// The repair for the worst thing that can go wrong with a coding question. A
// case with the wrong expected output does not mark one paper wrongly; it
// marks every paper wrongly, in the same direction, and the marks look exactly
// like marks that were arrived at properly. Before this existed the only
// answers were to leave them standing or to re-mark by hand.
//
// Three things make it survivable rather than merely possible:
//
//   It is only offered once the examination is over. The server refuses it
//   with a 409 otherwise, and it is right to: moving the answer key while
//   candidates are still typing is the same fault committed live.
//
//   It clears every mark on the question instead of recomputing them, and the
//   person doing it is told how many before they confirm. Those marks came
//   from a key that no longer exists. Some of them have been read.
//
//   The reason is required and is shown as what it is — a line in the audit
//   trail, next to a name, read by whoever asks about this in a year.
//
// Afterwards the papers sit unmarked for about a minute while the runner
// redoes them. That gap is the dangerous moment for this screen: a column of
// blanks where marks used to be reads as data loss unless it says otherwise,
// so `remarking` carries the corrected questions back into the report list.
// ---------------------------------------------------------------------------

/** Questions whose marks are currently being redone, and how many were cleared. */
export type Remarking = Record<string, number>;

const marksFor = (reports: CodingReportDto[] | null, questionId: string) =>
  reports === null ? null : reports.filter((report) => report.questionId === questionId && typeof report.awardedMarks === "number").length;

const submissionsFor = (reports: CodingReportDto[] | null, questionId: string) =>
  reports === null ? null : reports.filter((report) => report.questionId === questionId).length;

/**
 * What went wrong, in terms of the thing the person was doing.
 *
 * The refusals mean genuinely different things and need different answers, so
 * none of them is allowed to collapse into "that failed".
 *
 * More than one thing answers 409 — an assessment that is not over, and a
 * question the bank shares with another paper — and only the server knows
 * which was hit. So its message leads, and nothing is added here that is not
 * true of both: guessing the cause in the client is how a faculty member ends
 * up waiting for an exam to end that ended last week.
 */
function refusalMessage(cause: unknown): string {
  if (!(cause instanceof ApiError)) {
    return "The correction never reached the exam server, so nothing was changed and the marks stand as they were. Check the connection and try again.";
  }
  switch (cause.status) {
    case 409:
      return `${cause.message} Nothing was changed — the question keeps the cases it had, and every mark on it stands. If this screen has fallen behind what the server knows, reload it and look again.`;
    case 422:
      return `${cause.message} Nothing was changed.`;
    case 403:
      return "Your account is not allowed to correct test cases. It is a staff action and it is recorded against whoever performs it, so it cannot be done on someone else's behalf — ask the exam cell to make the correction.";
    default:
      return `The exam server refused the correction (${cause.status}). Nothing was changed and every mark on this question is as it was.`;
  }
}

/** One coding question in the list, with what correcting it would cost. */
function QuestionRow({ question, reports, remarking, onCorrect, offered }: {
  question: Question;
  reports: CodingReportDto[] | null;
  remarking: number | undefined;
  onCorrect: () => void;
  offered: boolean;
}) {
  const tests = question.tests ?? [];
  const hidden = tests.filter((test) => test.hidden).length;
  const marked = marksFor(reports, question.id);
  const submitted = submissionsFor(reports, question.id);

  return <div className={`key-row ${remarking !== undefined ? "is-remarking" : ""}`}>
    <div className="key-row-main">
      <p className="key-row-prompt">{question.prompt}</p>
      <small>
        {tests.length} test {tests.length === 1 ? "case" : "cases"}, {hidden} hidden · {question.marks} marks
        {/* Written as a fraction of what was submitted, because "4 marked" on
            its own cannot be told apart from "4 marked out of 40". */}
        {marked !== null && submitted !== null && <> · {marked} of {submitted} marked</>}
      </small>
    </div>
    {remarking !== undefined
      ? <Badge tone="info">Re-marking</Badge>
      : offered && <Button type="button" tone="secondary" icon="reset" onClick={onCorrect}>Correct test cases</Button>}
  </div>;
}

/**
 * The editor for one question's cases, and the confirmation in front of the
 * save. Kept as its own component so it is remounted per question — carrying a
 * half-written reason from one question's correction onto another's is how the
 * audit trail ends up explaining the wrong repair.
 */
function CorrectionEditor({ exam, question, reports, onClose, onCorrected }: {
  exam: Test;
  question: Question;
  reports: CodingReportDto[] | null;
  onClose: () => void;
  onCorrected: (questionId: string, result: TestCaseCorrectionResultDto) => void;
}) {
  const [tests, setTests] = useState<BuilderTestCase[]>(() => {
    const existing = (question.tests ?? []).map(builderTestCase);
    return existing.length ? existing : [blankTestCase(0)];
  });
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);

  const atRisk = marksFor(reports, question.id);
  const hidden = tests.filter((test) => test.hidden).length;
  const written = reason.trim().length;

  const update = (index: number, patch: Partial<BuilderTestCase>) =>
    setTests((old) => old.map((test, i) => (i === index ? { ...test, ...patch } : test)));

  const review = () => {
    // Checked here rather than only at the server so the refusal arrives while
    // the form is still on screen and can still be fixed — a 422 after the
    // confirmation reads as though the correction half happened.
    const wrong = testCaseProblem(tests) ?? reasonProblem(reason);
    setProblem(wrong);
    if (!wrong) setConfirming(true);
  };

  const save = async () => {
    setSaving(true);
    setProblem(null);
    try {
      const result = await coding.correctTests(exam.id, question.id, {
        reason: reason.trim(),
        tests: tests.map(authoredTestCase),
      });
      onCorrected(question.id, result);
    } catch (cause) {
      setProblem(refusalMessage(cause));
      setConfirming(false);
    } finally {
      setSaving(false);
    }
  };

  return <div className="correction-editor coding-builder">
    <div className="correction-head">
      <div>
        <p className="eyebrow">Correcting</p>
        <p className="key-row-prompt">{question.prompt}</p>
      </div>
      <Button type="button" tone="ghost" onClick={onClose} disabled={saving}>Cancel</Button>
    </div>

    {/* Said before the form rather than in the confirmation alone. Somebody who
        learns the cost only after rewriting six cases has already decided. */}
    <p className="coding-panel-note is-caution">
      <Icon name="alert" size={17}/>
      <span>
        <strong>Saving this clears every mark on this question.</strong>{" "}
        {atRisk === null
          ? "The programs on this assessment could not be read, so how many marks that is cannot be counted here. Every one of them goes back to unmarked, including any a candidate has already been shown, because they were worked out from a key that will no longer exist. The runner re-marks them against the corrected cases within about a minute."
          : atRisk === 0
          ? "Nothing has been marked on it yet, so today there is nothing to lose. That stops being true the moment the runner reaches these papers."
          : `${atRisk} ${atRisk === 1 ? "paper has" : "papers have"} a mark for it, and ${atRisk === 1 ? "it goes" : "they go"} back to unmarked — including any a candidate has already been shown. ${atRisk === 1 ? "It was" : "They were"} worked out from a key that will no longer exist. The runner re-marks ${atRisk === 1 ? "it" : "them"} against the corrected cases within about a minute.`}
      </span>
    </p>

    <div className="test-builder-head">
      <div>
        <strong>Test cases</strong>
        <small>These replace the question&rsquo;s cases outright &mdash; anything you remove here is gone, and anything left unchanged is kept only because it is still written down. A hidden case is the answer key; a visible one was printed on the paper as a worked example.</small>
      </div>
      <HiddenCaseCount tests={tests}/>
    </div>

    <div className="test-builder">{tests.map((test, index) => <TestCaseFields
      key={index}
      label={`Test ${index + 1}`}
      test={test}
      onChange={(patch) => update(index, patch)}
      // A question with no cases cannot be marked at all, which would be a
      // worse state than the wrong case this is repairing.
      onRemove={tests.length > 1 ? () => setTests((old) => old.filter((_, i) => i !== index)) : undefined}
    />)}</div>
    <Button type="button" tone="secondary" icon="plus" onClick={() => setTests((old) => [...old, blankTestCase(old.length)])}>Add test case</Button>

    <label className="field correction-reason">
      <span>Why these cases are being corrected</span>
      <textarea
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        maxLength={REASON_MAX}
        rows={3}
        placeholder="Case 3 expected 7 spaces of padding; the question asked for one. Every submission failed it."
      />
      <small>
        {/* Careful not to promise more than the system does: the audit trail is
            staff-only, so this is the explanation whoever looks into a changed
            mark will find — not something a candidate is shown automatically. */}
        This goes into the audit trail against your name and this question. It is the
        explanation anyone looking into a changed mark will find, and the one a
        candidate who asks will be read, so write what was wrong with the old case
        rather than that something was. {written} of {REASON_MAX} characters.
      </small>
    </label>

    {problem && <p className="coding-panel-result is-problem" role="alert"><Icon name="alert" size={16}/> {problem}</p>}

    <div className="coding-panel-actions">
      <Button type="button" tone="danger" onClick={review} disabled={saving}>Review the correction</Button>
      <Button type="button" tone="ghost" onClick={onClose} disabled={saving}>Leave it alone</Button>
    </div>

    <Modal
      open={confirming}
      onClose={() => { if (!saving) setConfirming(false); }}
      title={atRisk ? `Replace these test cases and clear ${atRisk} ${atRisk === 1 ? "mark" : "marks"}?` : "Replace these test cases?"}
      description="The question's test cases are replaced with the ones you have written, and every mark on it is cleared for the runner to redo. Marks that have already been released to candidates are cleared too, and will change when they come back."
      actions={<>
        <Button tone="secondary" onClick={() => setConfirming(false)} disabled={saving}>Cancel</Button>
        <Button tone="danger" onClick={() => { void save(); }} disabled={saving}>{saving ? "Correcting…" : "Correct and clear marks"}</Button>
      </>}
    >
      <div className="launch-summary">
        <strong>{exam.title}</strong>
        <span>{exam.code} · {tests.length} {tests.length === 1 ? "case" : "cases"}, {hidden} hidden</span>
        <span>
          {atRisk === null
            ? "The marks on this question could not be counted, so how many are cleared will only be known afterwards."
            : atRisk === 0
            ? "No marks have been given on this question yet, so none are cleared."
            : `${atRisk} ${atRisk === 1 ? "mark" : "marks"} cleared, re-marked within about a minute.`}
        </span>
      </div>
    </Modal>
  </div>;
}

/**
 * The panel: which coding questions this assessment has, and the way in to
 * correcting one of them.
 *
 * The control is withheld outside a completed assessment rather than shown
 * and rejected, but the reason is still on screen. A faculty member who came
 * here because a case is wrong needs to know that the repair exists and when
 * they can use it — an absent button tells them neither.
 */
export function CorrectTestCasesPanel({ exam, reports, remarking, onCorrected }: {
  exam: Test;
  /** Null when the programs could not be read, which is different from none
   *  having been submitted: it means the mark counts here are unknowable. */
  reports: CodingReportDto[] | null;
  remarking: Remarking;
  onCorrected: (questionId: string, result: TestCaseCorrectionResultDto) => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<string | null>(null);

  const questions = useMemo(() => exam.questions.filter((question) => question.type === "coding"), [exam.questions]);
  const offered = exam.status === "completed";
  const question = questions.find((item) => item.id === editing);
  const pending = Object.keys(remarking).length;

  if (!questions.length) return null;

  const corrected = (questionId: string, result: TestCaseCorrectionResultDto) => {
    // Both numbers, always. "3 cases, 0 cleared" on a question forty people
    // sat means the runner had not reached it — which is worth knowing, and
    // reads identically to a correction that did nothing if only one is shown.
    setOutcome(result.cleared
      ? `Corrected. The question now has ${result.cases} test ${result.cases === 1 ? "case" : "cases"}, and ${result.cleared} ${result.cleared === 1 ? "mark was" : "marks were"} cleared. The runner is re-marking those papers now; they come back within about a minute.`
      : `Corrected. The question now has ${result.cases} test ${result.cases === 1 ? "case" : "cases"}. No marks had been given for it yet, so none were cleared.`);
    setEditing(null);
    onCorrected(questionId, result);
  };

  return <Card className="coding-panel">
    <div className="section-heading">
      <div><p className="eyebrow">Answer keys</p><h2>Test cases</h2></div>
      {pending > 0
        ? <Badge tone="info">{pending === 1 ? "1 question re-marking" : `${pending} questions re-marking`}</Badge>
        : <Badge tone="neutral">{questions.length} coding {questions.length === 1 ? "question" : "questions"}</Badge>}
    </div>
    <div className="coding-panel-body">
      {question
        ? <CorrectionEditor
            exam={exam}
            question={question}
            reports={reports}
            onClose={() => setEditing(null)}
            onCorrected={corrected}
          />
        : <>
            <p className={`coding-panel-note ${offered ? "" : "is-caution"}`}>
              <Icon name={offered ? "shield" : "clock"} size={17}/>
              <span>{offered
                ? <>A test case with the wrong expected output marks everyone against an answer that was never right. Correcting one replaces the question&rsquo;s cases, clears its marks, and has the runner work them out again &mdash; with your reason on the record.</>
                : <><strong>Test cases cannot be corrected until this assessment is over.</strong> The paper is still open, and moving an answer key under candidates who are answering is the same fault as the wrong case itself. Once the examination has finished, the repair appears here.</>}</span>
            </p>
            {outcome && <p className="coding-panel-result" role="status"><Icon name="check" size={16}/> {outcome}</p>}
            <div className="key-list">{questions.map((item) => <QuestionRow
              key={item.id}
              question={item}
              reports={reports}
              remarking={remarking[item.id]}
              offered={offered}
              onCorrect={() => { setOutcome(null); setEditing(item.id); }}
            />)}</div>
          </>}
    </div>
  </Card>;
}

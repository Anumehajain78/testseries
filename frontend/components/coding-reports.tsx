"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { ApiError, coding, type CodingCaseReportDto, type CodingReportDto } from "@/lib/api";
import { useExam } from "@/app/providers";
import type { Test } from "@/lib/types";
import { Icon } from "./icons";
import { Badge, Button, ButtonLink, Card, EmptyState, LoadingState, Modal, PageHeader } from "./ui";

// ---------------------------------------------------------------------------
// Reviewing marked programs
//
// The counterpart of the written-answer marking queue, and needed for the same
// reason turned inside out. A written answer is unreviewable until a person
// reads it; a program is marked the moment the runner reaches it, and then
// "6 out of 10" is unreviewable — a faculty member asked to justify it has
// nothing to look at. This screen is the evidence: which case failed, what the
// program printed, and how long it took.
//
// What it cannot do is change a mark. A program's mark comes from running it,
// so the repair for a wrong one is to correct the question and run it again,
// not to type a different number over the top.
// ---------------------------------------------------------------------------

const key = (report: CodingReportDto) => `${report.sessionId}:${report.questionId}`;

// A mark of null has not been given yet — deliberately distinct from a mark of
// zero, which is a judgement something made.
const isMarked = (report: CodingReportDto) => typeof report.awardedMarks === "number";

/**
 * What happened when the case ran, said in a marker's words rather than the
 * runner's. `outcome` is typed as a free string on the wire because the server
 * can grow a sixth one, so an unrecognised value falls through to something
 * honest instead of rendering a raw enum at a faculty member.
 */
function caseVerdict(report: CodingCaseReportDto): { label: string; tone: "success" | "danger" | "warning" | "neutral" } {
  if (report.passed) return { label: "Passed", tone: "success" };
  switch (report.outcome) {
    // Ran cleanly and still did not pass: the program works, the answer is wrong.
    case "ok": return { label: "Wrong output", tone: "danger" };
    case "failed": return { label: "Crashed", tone: "danger" };
    case "timed_out": return { label: "Timed out", tone: "warning" };
    case "out_of_memory": return { label: "Ran out of memory", tone: "warning" };
    // Never the candidate's fault, and never scored as a wrong answer — so it
    // is not dressed up as one here either.
    case "unavailable": return { label: "Could not be run", tone: "neutral" };
    default: return { label: report.outcome, tone: "neutral" };
  }
}

/** One case, and — only where the candidate was allowed to see it — its output. */
function CaseRow({ report, index }: { report: CodingCaseReportDto; index: number }) {
  const verdict = caseVerdict(report);
  return <li className={`case-row ${report.passed ? "is-passed" : "is-failed"} ${report.hidden ? "is-hidden" : ""}`}>
    <div className="case-head">
      <strong>Case {index + 1}</strong>
      <Badge tone={report.hidden ? "neutral" : "info"}>{report.hidden ? "Hidden" : "Shown to candidate"}</Badge>
      <Badge tone={verdict.tone}>{verdict.label}</Badge>
      <span className="case-timing">{report.durationMs} ms</span>
    </div>
    {report.hidden
      // The emptiness is withholding, not silence. An empty output box here
      // would tell a marker the program printed nothing, when in fact this is
      // the answer key and nobody is being shown what it printed.
      ? <p className="case-withheld"><Icon name="shield" size={15}/> Output withheld. This case is part of the answer key, so what the program printed is not shown — only whether it was right.</p>
      : report.outcome === "unavailable"
      // The third kind of emptiness: the sandbox never ran the program, so
      // there is no output to have. Showing "printed nothing" would put that
      // at the candidate's door, and it is not theirs.
      ? <p className="case-withheld"><Icon name="alert" size={15}/> The sandbox could not run this case, so the program produced no output. That is a problem with the machine, not with the program.</p>
      : <div className="case-io">
          <div><small>Printed</small><pre>{report.stdout || <em>Nothing at all.</em>}</pre></div>
          {report.stderr && <div><small>Errors</small><pre className="is-stderr">{report.stderr}</pre></div>}
        </div>}
  </li>;
}

/**
 * Marking the programs on one assessment, and saying when nothing ever will.
 *
 * Two runs rather than one button, because they are different acts. The plain
 * run marks what has never been marked — idempotent, and the same thing the
 * server does by itself within a minute of a submission. The forced run
 * re-marks the whole cohort, which is how a broken test case gets repaired,
 * and it overwrites marks candidates may already have been shown. Only one of
 * those should be reachable without stopping to think about it.
 *
 * The capability check is what separates "not marked yet" from "will never be
 * marked here". Without it a console on a host with no sandbox shows a queue
 * of pending programs that nothing is ever coming to collect, and it looks
 * exactly like one that is simply busy.
 */
export function CodingRunPanel({ exam, pending, onRan }: { exam: Test; pending: number; onRan: () => void }) {
  // Null until the server has answered. Neither claim is safe to make before
  // then, so the panel says nothing about the sandbox rather than guessing.
  const [sandbox, setSandbox] = useState<boolean | null>(null);
  const [busy, setBusy] = useState<"pending" | "all" | null>(null);
  const [outcome, setOutcome] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    let cancelled = false;
    coding
      .capabilities()
      .then((capabilities) => { if (!cancelled) setSandbox(capabilities.codingSandbox); })
      // A console that cannot ask still works; it simply does not get to warn
      // anybody, which is the state it was in before this call existed.
      .catch(() => { if (!cancelled) setSandbox(null); });
    return () => { cancelled = true; };
  }, []);

  const run = async (force: boolean) => {
    setBusy(force ? "all" : "pending");
    setOutcome(null);
    setProblem(null);
    try {
      const summary = await coding.run(exam.id, force);
      // Both numbers are reported. "0 marked, 30 skipped" is an assessment
      // that was already finished; "0 marked, 0 skipped" is one where nothing
      // has been submitted — the same headline meaning opposite things.
      setOutcome(summary.graded || summary.skipped
        ? `Marked ${summary.graded} ${summary.graded === 1 ? "program" : "programs"}. ${summary.skipped} already had marks and ${force ? "were re-marked" : "were left alone"}.`
        : "There were no submitted programs to mark.");
      onRan();
    } catch (cause) {
      const unavailable = cause instanceof ApiError && cause.status === 503;
      // A 503 here is the machine, not the request. Saying "marking failed"
      // would send a faculty member hunting for a bad test case when the truth
      // is that this host cannot run candidate code at all.
      setProblem(unavailable
        ? "This machine cannot run candidate code, so no marks were changed. The programs stay unmarked until the exam server runs on a host with the sandbox enabled."
        : "The run did not start, and nothing was marked. Try again, or check that the exam server is reachable.");
      if (unavailable) setSandbox(false);
    } finally {
      setBusy(null);
      setConfirming(false);
    }
  };

  const codingQuestions = exam.questions.filter((question) => question.type === "coding").length;

  return <Card className="coding-panel">
    <div className="section-heading">
      <div><p className="eyebrow">Programs</p><h2>Code marking</h2></div>
      {sandbox === false
        ? <Badge tone="danger">Sandbox unavailable</Badge>
        : pending > 0 ? <Badge tone="warning">{pending} awaiting marking</Badge> : <Badge tone="success">Nothing pending</Badge>}
    </div>
    <div className="coding-panel-body">
      {sandbox === false
        ? <p className="coding-panel-note is-blocked"><Icon name="alert" size={17}/><span><strong>This machine cannot run candidate code.</strong> Coding answers on this assessment will never be marked here, however long they are left. They are waiting on a server with the sandbox enabled, not in a queue.</span></p>
        : <p className="coding-panel-note"><Icon name="code" size={17}/><span>Programs are marked by running them against each question&rsquo;s test cases, within about a minute of a candidate submitting. Run them now rather than waiting, or re-mark everyone after correcting a test case that was wrong.</span></p>}
      {outcome && <p className="coding-panel-result" role="status"><Icon name="check" size={16}/> {outcome}</p>}
      {problem && <p className="coding-panel-result is-problem" role="alert"><Icon name="alert" size={16}/> {problem}</p>}
      <div className="coding-panel-actions">
        <Button type="button" tone="secondary" icon="reset" disabled={busy !== null || sandbox === false} onClick={() => run(false)}>
          {busy === "pending" ? "Running…" : "Mark pending programs"}
        </Button>
        {/* Behind a confirmation, because it replaces marks that have already
            been given and may already have been read. */}
        <Button type="button" tone="danger" disabled={busy !== null || sandbox === false} onClick={() => setConfirming(true)}>
          {busy === "all" ? "Re-marking…" : "Re-mark every candidate"}
        </Button>
      </div>
    </div>
    <Modal
      open={confirming}
      onClose={() => setConfirming(false)}
      title={"Re-mark every candidate’s program?"}
      description="Every submitted program on this assessment is run again and its mark replaced, including marks already given and released. Do this after correcting a test case that was wrong — not to check on a run that is simply still going."
      actions={<><Button tone="secondary" onClick={() => setConfirming(false)}>Cancel</Button><Button tone="danger" onClick={() => run(true)}>Re-mark everyone</Button></>}
    >
      <div className="launch-summary"><strong>{exam.title}</strong><span>{exam.code} · {codingQuestions} coding {codingQuestions === 1 ? "question" : "questions"}</span></div>
    </Modal>
  </Card>;
}

export function CodingReportScreen() {
  const params = useParams<{ id: string }>();
  const { state, hydrated, refreshExam } = useExam();
  const [reports, setReports] = useState<CodingReportDto[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    () =>
      coding
        .reports(params.id)
        .then((rows) => { setReports(rows); setError(null); })
        .catch(() => setError("Could not load the submitted programs for this assessment.")),
    [params.id],
  );

  useEffect(() => {
    let cancelled = false;
    coding
      .reports(params.id)
      .then((rows) => { if (!cancelled) setReports(rows); })
      .catch(() => { if (!cancelled) setError("Could not load the submitted programs for this assessment."); });
    return () => { cancelled = true; };
  }, [params.id]);

  const exam = state.tests.find((test) => test.id === params.id);

  // Unmarked first, then by candidate — the same order as the written-answer
  // queue, because the question being asked is the same one: what is not done.
  const ordered = useMemo(() => {
    if (!reports) return [];
    return [...reports].sort((a, b) => {
      const unmarked = Number(isMarked(a)) - Number(isMarked(b));
      return unmarked !== 0 ? unmarked : a.studentName.localeCompare(b.studentName);
    });
  }, [reports]);

  const unmarked = ordered.filter((report) => !isMarked(report)).length;

  if (!hydrated || reports === null) return <LoadingState/>;

  return <>
    <PageHeader
      eyebrow="Programs"
      title={exam ? exam.title : "Submitted programs"}
      description="Every candidate's program and what running it did — which cases passed, and what the program printed."
      actions={<>
        <Badge tone={unmarked ? "warning" : "success"}>
          {unmarked ? `${unmarked} not marked yet` : "All marked"}
        </Badge>
        {exam && <ButtonLink href={`/admin/tests/${exam.id}`} tone="secondary">Assessment</ButtonLink>}
        <ButtonLink href="/admin/results" tone="ghost">Results</ButtonLink>
      </>}
    />

    {error && <div className="marking-error" role="alert"><Icon name="alert" size={17}/> {error}</div>}

    {/* Re-running is the only way a mark here changes, so the control belongs
        on the screen showing the evidence that it needs to. */}
    {exam && <CodingRunPanel exam={exam} pending={unmarked} onRan={() => { void load(); void refreshExam(exam.id); }}/>}

    {ordered.length === 0
      ? <EmptyState
          icon="code"
          title="No programs to review"
          description="Nobody has submitted a program for this assessment. Coding answers appear here once candidates submit and the runner has been round."
          action={<ButtonLink href="/admin/results">See results</ButtonLink>}
        />
      : <div className="marking-list">
          {ordered.map((report) => {
            const marked = isMarked(report);
            const cases = report.cases ?? [];
            return (
              <Card key={key(report)} className={`marking-card ${marked ? "is-marked" : ""}`}>
                <div className="marking-head">
                  <div>
                    <strong>{report.studentName}</strong>
                    <small>{report.registrationNo}</small>
                  </div>
                  {/* Never a nought while it is unmarked: that would say the
                      candidate failed, when nothing has run their program. */}
                  <Badge tone={marked ? "success" : "warning"}>
                    {marked ? `${report.awardedMarks} of ${report.marks}` : `Awaiting marking · ${report.marks} marks`}
                  </Badge>
                </div>

                <p className="marking-prompt">{report.prompt}</p>

                {marked && <p className="case-summary">
                  <Icon name="check" size={15}/> {report.passed} of {report.total} {report.total === 1 ? "case" : "cases"} passed
                </p>}

                {/* Indentation is the syntax in Python, so the program is shown
                    exactly as submitted rather than reflowed to fit. */}
                <pre className="marking-response marking-code">{report.source.trim() || <em>No program was submitted.</em>}</pre>

                {cases.length > 0
                  ? <ol className="case-list">{cases.map((item, index) => <CaseRow key={item.position} report={item} index={index}/>)}</ol>
                  : <p className="case-summary is-pending"><Icon name="clock" size={15}/> This program has not been run yet, so there is nothing to show. Use the controls above to run it now.</p>}
              </Card>
            );
          })}
        </div>}
  </>;
}

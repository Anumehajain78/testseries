"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useExam } from "@/app/providers";
import { formatDateTime, formatScore, initials, percentage } from "@/lib/format";
import { Icon } from "./icons";
import { ExamTimer, QuestionCard, QuestionPalette, SubmitDialog, SystemCheck, isAnswered, type ReadinessCheck } from "./exam";
import { Badge, Button, ButtonLink, Card, EmptyState, LoadingState, Progress, StatusDot } from "./ui";

export function StudentDashboard() {
  const { state, hydrated, currentStudentId } = useExam(); if (!hydrated) return <LoadingState/>; const student = state.students.find((s) => s.id === currentStudentId)!; const live = state.tests.find((t) => t.status === "live" && !state.submissions.some((s) => s.testId === t.id && s.studentId === currentStudentId)); const next = live ?? state.tests.find((t) => t.status === "scheduled"); const submitted = next ? state.submissions.some((s) => s.testId === next.id && s.studentId === currentStudentId) : false; const lab = state.labs.find((l) => l.id === next?.labId);
  return <div className="student-page"><section className="student-welcome"><div><p className="eyebrow">Student examination portal</p><h1>Welcome, {student.name.split(" ")[0]}</h1><p>Verify your assignment and complete the readiness checks before entering.</p></div><div className="identity-chip"><span className="avatar">{initials(student.name)}</span><div><small>Candidate ID</small><strong>{student.registrationNo}</strong></div><Icon name="check"/></div></section>{next ? <Card className={`assigned-exam ${live ? "is-live" : ""}`}><div className="assigned-top"><Badge tone={live ? "live" : "info"}>{live ? "ENTRY GATE OPEN" : "UPCOMING ASSESSMENT"}</Badge><span><Icon name="shield" size={16}/> Proctored session</span></div><div className="assigned-content"><div className="course-mark">{next.code.split("-")[0]}</div><div><p>{next.code}</p><h2>{next.title}</h2><span>{next.course}</span></div></div><div className="assignment-facts"><div><Icon name="calendar"/><span><small>Date & time</small><strong>{formatDateTime(next.scheduledAt)}</strong></span></div><div><Icon name="clock"/><span><small>Duration</small><strong>{next.durationMinutes} minutes</strong></span></div><div><Icon name="monitor"/><span><small>Assigned venue</small><strong>{lab?.name}</strong></span></div><div><Icon name="user"/><span><small>Seat</small><strong>{student.seat}</strong></span></div></div><div className="assigned-footer"><p><Icon name="alert" size={17}/> Arrive at the assigned workstation at least 10 minutes early.</p>{submitted ? <ButtonLink href="/student/submitted">View submission receipt</ButtonLink> : <ButtonLink href={live ? `/student/exam/${next.id}` : "/student/waiting"} icon={live ? "arrow" : "clock"}>{live ? "Enter examination" : "Enter waiting room"}</ButtonLink>}</div></Card> : <EmptyState title="No assessment assigned" description="There are no upcoming examinations linked to your registration."/>}<div className="student-info-grid"><Card><div className="info-title"><span><Icon name="monitor"/></span><div><h2>Device readiness</h2><p>Required before entry</p></div><Badge tone="success">READY</Badge></div><div className="device-checks"><p><Icon name="check"/> Browser compatibility <strong>Passed</strong></p><p><Icon name="check"/> Network connection <strong>Stable</strong></p><p><Icon name="check"/> Secure storage <strong>Available</strong></p></div></Card><Card><div className="info-title"><span><Icon name="shield"/></span><div><h2>Before you begin</h2><p>Important examination rules</p></div></div><ol className="student-rules"><li>Keep your college ID card visible.</li><li>Do not leave or refresh the exam window.</li><li>Contact the invigilator for technical help.</li></ol></Card></div></div>;
}

export function WaitingRoomScreen() {
  const { state, hydrated, currentStudentId } = useExam();
  const router = useRouter();
  // Prefer a test the student is assigned to; fall back to any live/scheduled test for the demo.
  const assignedTo = useCallback((test: { assignedStudentIds: string[] }) => test.assignedStudentIds.includes(currentStudentId), [currentStudentId]);
  const live = state.tests.find((t) => t.status === "live" && assignedTo(t) && !state.submissions.some((s) => s.testId === t.id && s.studentId === currentStudentId))
    ?? state.tests.find((t) => t.status === "live" && !state.submissions.some((s) => s.testId === t.id && s.studentId === currentStudentId));
  const scheduled = state.tests.find((t) => t.status === "scheduled" && assignedTo(t)) ?? state.tests.find((t) => t.status === "scheduled");
  const test = live ?? scheduled;

  // When the assigned test goes Live, release the student into the examination (Req 12.4).
  useEffect(() => {
    if (live) router.replace(`/student/exam/${live.id}`);
  }, [live, router]);

  if (!hydrated) return <LoadingState/>;
  if (!test) return <div className="centered-student"><EmptyState icon="calendar" title="No examination assigned" description="There are no examinations linked to your registration. Check back when your exam cell schedules one." action={<ButtonLink href="/student">Return to portal</ButtonLink>}/></div>;

  const student = state.students.find((s) => s.id === currentStudentId)!;
  const lab = state.labs.find((l) => l.id === test.labId);
  const session = state.sessions.find((s) => s.testId === test.id && s.studentId === currentStudentId);
  const computer = state.computers.find((c) => c.id === session?.computerId) ?? state.computers.find((c) => c.assignedStudentId === currentStudentId);
  const connection = session?.connection ?? computer?.connection ?? "online";
  const connected = connection !== "offline";
  const checks: ReadinessCheck[] = [
    { label: "Student verified", detail: `${student.name} · ${student.registrationNo}`, ok: student.status === "active" },
    { label: "Computer verified", detail: computer ? `${computer.id} · ${lab?.name ?? "Assigned lab"}` : "Awaiting workstation assignment", ok: !!computer },
    { label: "Connection stable", detail: connected ? "Heartbeat active with exam control" : "No heartbeat detected", ok: connected },
    { label: "Exam client ready", detail: "Secure browser session initialized", ok: true },
  ];

  return <div className="waiting-page">
    <div className={`waiting-orb ${live ? "released" : ""}`}><span><Icon name={live ? "check" : "clock"} size={34}/></span><i/><i/></div>
    <p className="eyebrow">Northbridge Exam Control Platform</p>
    <Badge tone="info">SECURE WAITING ROOM</Badge>
    <h1>Waiting for the exam controller</h1>
    <p>You are checked in and connected. Keep this page open—it will move you into the examination automatically when the controller starts the session.</p>
    <Card className="waiting-card">
      <div><span className="course-mark">{test.code.split("-")[0]}</span><div><small>{test.code}</small><h2>{test.title}</h2><p>{test.course}</p></div></div>
      <div className="waiting-identity">
        <div><small>Candidate</small><strong>{student.name}</strong></div>
        <div><small>Roll number</small><strong>{student.registrationNo}</strong></div>
        <div><small>Assigned computer</small><strong>{computer?.id ?? "—"}</strong></div>
        <div><small>Connection</small><StatusDot status={connected ? "online" : "offline"} label={connected ? "Connected" : "Disconnected"}/></div>
      </div>
      <div className="waiting-meta"><span><Icon name="clock"/> {test.durationMinutes} minutes</span><span><Icon name="file"/> {test.questions.length} questions</span><span><Icon name="monitor"/> {lab?.name ?? "Assigned lab"}</span></div>
    </Card>
    <SystemCheck checks={checks}/>
    <div className="waiting-status"><span className="spinner small"/><div><strong>Connected to exam control</strong><small>The examination has not begun. Listening for session release…</small></div></div>
    <Link href="/student" className="back-link">← Return to student portal</Link>
  </div>;
}

export function StudentExamScreen() {
  const params = useParams<{ id: string }>(); const router = useRouter(); const { state, hydrated, currentStudentId, answerQuestion, flagQuestion, submitExam } = useExam(); const [current, setCurrent] = useState(0); const [dialog, setDialog] = useState(false); const test = state.tests.find((t) => t.id === params.id); const submission = state.submissions.find((s) => s.testId === params.id && s.studentId === currentStudentId); const finish = useCallback(async (mode: "manual" | "automatic") => { await submitExam(params.id, mode); router.replace("/student/submitted"); }, [params.id, submitExam, router]); const autoSubmit = useCallback(() => finish("automatic"), [finish]);
  if (!hydrated) return <LoadingState/>; if (submission) return <div className="centered-student"><EmptyState icon="check" title="Assessment already submitted" description="Your answers have been received and cannot be changed." action={<ButtonLink href="/student/submitted">View receipt</ButtonLink>}/></div>; if (!test || test.status !== "live") return <div className="centered-student"><EmptyState icon="shield" title="Entry gate is closed" description="This assessment has not been released by the exam controller." action={<ButtonLink href="/student/waiting">Return to waiting room</ButtonLink>}/></div>;
  const key = `${test.id}:${currentStudentId}`; const answers = state.answers[key] ?? {}; const flags = state.flags[key] ?? []; const question = test.questions[current];
  const student = state.students.find((s) => s.id === currentStudentId);
  const answeredCount = test.questions.filter((q) => isAnswered(answers[q.id])).length;
  const allowNavigation = test.config.allowNavigation;
  return <div className="exam-workspace"><header className="exam-bar"><div><Badge tone="live">EXAM IN PROGRESS</Badge><span><strong>{test.title}</strong><small>{test.code}</small></span></div><ExamTimer endsAt={test.endsAt} onExpire={autoSubmit}/><Button tone="secondary" icon="send" onClick={() => setDialog(true)}>Submit exam</Button></header><div className="save-strip" aria-live="polite"><span><Icon name="check" size={15}/> Responses save automatically on this device</span><span>Candidate: {student?.name ?? "Candidate"} · Seat {student?.seat ?? "—"}</span></div><main className="exam-main"><QuestionPalette questions={test.questions} current={current} answers={answers} flags={flags} allowNavigation={allowNavigation} onSelect={setCurrent}/><QuestionCard question={question} index={current} total={test.questions.length} answer={answers[question.id]} flagged={flags.includes(question.id)} allowNavigation={allowNavigation} onAnswer={(value) => answerQuestion(test.id, question.id, value)} onFlag={() => flagQuestion(test.id, question.id)} onPrevious={() => setCurrent((value) => Math.max(0, value - 1))} onNext={() => setCurrent((value) => Math.min(test.questions.length - 1, value + 1))}/></main><SubmitDialog open={dialog} onClose={() => setDialog(false)} onConfirm={() => finish("manual")} answered={answeredCount} total={test.questions.length}/></div>;
}

export function SubmittedScreen() {
  const { state, hydrated, currentStudentId } = useExam(); if (!hydrated) return <LoadingState/>; const submission = state.submissions.find((s) => s.studentId === currentStudentId); if (!submission) return <div className="centered-student"><EmptyState icon="file" title="No submission receipt" description="Complete an assessment to generate a verified receipt." action={<ButtonLink href="/student">Return to portal</ButtonLink>}/></div>; const test = state.tests.find((t) => t.id === submission.testId)!; const student = state.students.find((s) => s.id === currentStudentId)!; const result = state.results.find((r) => r.testId === test.id && r.studentId === currentStudentId); const showScore = state.mockResultMode && result;
  return <div className="submitted-page"><div className="success-seal"><Icon name="check" size={38}/><i/></div><p className="eyebrow">Submission complete</p><h1>Your examination was submitted successfully</h1><p className="submitted-lead">You may now leave the examination workstation after notifying your invigilator.</p><Card className="receipt"><div className="receipt-head"><div><span className="brand-mark"><Icon name="book"/></span><div><strong>Northbridge Institute of Technology</strong><small>Official examination submission receipt</small></div></div><Badge tone="success">SUBMITTED</Badge></div><div className="receipt-title"><small>{test.code}</small><h2>{test.title}</h2><p>{test.course}</p></div><dl className="receipt-grid"><div><dt>Candidate</dt><dd>{student.name}</dd><small>{student.registrationNo}</small></div><div><dt>Submitted at</dt><dd>{formatDateTime(submission.submittedAt)}</dd><small>Institution time (IST)</small></div><div><dt>Status</dt><dd>Submitted</dd><small>Response locked for review</small></div><div><dt>Responses recorded</dt><dd>{Object.keys(submission.answers).length} of {test.questions.length}</dd><small>{submission.flagged.length} flagged at submission</small></div></dl><div className="receipt-code"><span>Receipt ID</span><code>{submission.id.toUpperCase()}</code><Icon name="shield"/></div>{showScore ? <div className="receipt-score"><div><span>Demo evaluation</span><strong>{formatScore(result.score,result.total)}</strong></div><Progress value={percentage(result.score,result.total)}/><small>Mock result mode is enabled for this demo. Scores stay withheld in a live deployment until faculty publication.</small></div> : <div className="receipt-withheld"><Icon name="shield" size={17}/><div><strong>Scores withheld</strong><small>Your results will be published by the exam cell after evaluation.</small></div></div>}</Card><div className="submitted-actions"><Button tone="secondary" onClick={() => window.print()} icon="file">Print receipt</Button><ButtonLink href="/student" icon="arrow">Return to portal</ButtonLink></div><p className="receipt-note"><Icon name="shield" size={15}/> A matching result and audit event are now visible in the administration console.</p></div>;
}

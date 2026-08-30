"use client";

import { useMemo, useState, type FormEvent, type KeyboardEvent } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useExam } from "@/app/providers";
import { formatDate, formatDateTime, formatDuration, formatScore, formatTime, initials, percentage, statusLabel } from "@/lib/format";
import type { AuditSeverity, Computer, ConnectionStatus, ExamSession, ExamStatus, Lab, NewTestInput, Student, StudentExamStatus, Test } from "@/lib/types";
import { buildMonitorRows, computeLabOccupancy, filterAuditEvents, summarizeMonitorRows, type AuditFilter } from "@/lib/selectors";
import { EXAM_STATUS_LABEL, examBadgeTone, examStatusTone } from "@/lib/status";
import { Icon } from "./icons";
import { Badge, Button, ButtonLink, Card, EmptyState, Field, LoadingState, Modal, PageHeader, Progress, Select, StatCard, StatusDot, TableShell } from "./ui";

const sameDay = (a: Date, b: Date) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

// Derive a single Online/Warning/Offline status for a lab from its computers.
function labLiveStatus(online: number, warning: number) {
  if (online === 0) return "offline" as const;
  if (warning > 0) return "warning" as const;
  return "online" as const;
}

export function AdminDashboard() {
  const { state, hydrated } = useExam();
  const today = useMemo(() => {
    if (!hydrated) return null;
    const now = new Date();
    const liveTests = state.tests.filter((test) => test.status === "live");
    const scheduledTests = state.tests.filter((test) => test.status === "scheduled");
    // Aggregate presence across every live test to surface online/assigned and warnings.
    const liveSummary = liveTests
      .map((test) => summarizeMonitorRows(buildMonitorRows(test.id, state.sessions, state.computers, state.students)))
      .reduce((acc, sum) => ({ assigned: acc.assigned + sum.assigned, online: acc.online + sum.online, warnings: acc.warnings + sum.warnings }), { assigned: 0, online: 0, warnings: 0 });
    const todaysExams = state.tests.filter((test) => sameDay(new Date(test.scheduledAt), now));
    return { now, liveTests, scheduledTests, liveSummary, todaysExams };
  }, [hydrated, state.tests, state.sessions, state.computers, state.students]);

  if (!hydrated || !today) return <LoadingState/>;
  const { now, liveTests, scheduledTests, liveSummary, todaysExams } = today;
  const greeting = now.getHours() < 12 ? "Good morning" : now.getHours() < 17 ? "Good afternoon" : "Good evening";
  const dateLabel = new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "2-digit", month: "long" }).format(now);

  return <>
    <PageHeader eyebrow={dateLabel} title={`${greeting}, Anita`} description="Here’s the current state of examinations across campus." actions={<ButtonLink href="/admin/tests/create" icon="plus">Create assessment</ButtonLink>}/>
    <div className="stats-grid">
      <StatCard label="Live examinations" value={liveTests.length} detail={liveTests.length ? "In session now" : "None running"} icon="monitor" tone="teal"/>
      <StatCard label="Scheduled exams" value={scheduledTests.length} detail="Awaiting launch" icon="calendar" tone="blue"/>
      <StatCard label="Students online" value={`${liveSummary.online}/${liveSummary.assigned}`} detail="Connected of assigned" icon="users" tone="navy"/>
      <StatCard label="Active warnings" value={liveSummary.warnings} detail={liveSummary.warnings ? "Require attention" : "All clear"} icon="alert" tone="amber"/>
    </div>
    <Card className="table-card">
      <div className="section-heading">
        <div><p className="eyebrow">Today · {dateLabel}</p><h2>Today’s examinations</h2></div>
        <Link href="/admin/tests">View all <Icon name="arrow" size={15}/></Link>
      </div>
      {todaysExams.length ? <TableShell caption="Today's examinations">
        <thead><tr><th>Subject</th><th>Lab</th><th>Start time</th><th>Duration</th><th>Students</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{todaysExams.map((test) => { const lab = state.labs.find((l) => l.id === test.labId); return <tr key={test.id}>
          <td><Link className="table-title" href={`/admin/tests/${test.id}`}>{test.course}</Link><small>{test.title} · {test.code}</small></td>
          <td>{lab?.name ?? "Unassigned"}</td>
          <td>{formatDateTime(test.scheduledAt)}</td>
          <td>{test.durationMinutes} minutes</td>
          <td>{test.assignedStudentIds.length}</td>
          <td><Badge tone={examBadgeTone(test.status)}>{statusLabel(test.status)}</Badge></td>
          <td><div className="row-actions"><ButtonLink href={`/admin/tests/${test.id}`} tone="ghost">View</ButtonLink>{test.status === "live" && <ButtonLink href={`/admin/tests/${test.id}/monitor`} tone="ghost">Monitor <Icon name="chevron" size={15}/></ButtonLink>}</div></td>
        </tr>; })}</tbody>
      </TableShell> : <EmptyState title="No examinations today" description="Scheduled assessments for other days appear under Assessments." action={<ButtonLink href="/admin/tests">Open assessments</ButtonLink>}/>}
    </Card>
    <div className="section-heading" style={{ padding: "24px 2px 12px" }}>
      <div><p className="eyebrow">Operations</p><h2>Live lab status</h2></div>
      <Link href="/admin/labs">Manage labs <Icon name="arrow" size={15}/></Link>
    </div>
    <div className="lab-grid">{state.labs.map((lab) => { const occ = computeLabOccupancy(lab.id, state.computers); const status = labLiveStatus(occ.online, occ.warning); return <Card className="lab-card" key={lab.id}>
      <div className="lab-top"><span className={`lab-icon ${lab.status}`}><Icon name="monitor"/></span><StatusDot status={status}/></div>
      <h2>{lab.name}</h2>
      <p><Icon name="building" size={16}/>{lab.building}</p>
      <div className="capacity-row"><span><strong>{occ.online}</strong> online</span><span>{occ.total} workstations</span></div>
      <Progress value={occ.total ? Math.round(occ.online / occ.total * 100) : 0}/>
      <p className="lab-exam-note">{occ.hasActiveExam ? <><Icon name="wifi" size={14}/> Active exam in progress</> : <><Icon name="clock" size={14}/> No active exam</>}</p>
    </Card>; })}</div>
  </>;
}

// Reusable table listing every test with lifecycle-aware row actions (Req 3.1, 19.1).
export function TestTable({ tests, labs }: { tests: Test[]; labs: Lab[] }) {
  const router = useRouter();
  // Row activation navigates to detail; live rows expose an extra Monitor shortcut (Req 3.4, 2.5).
  const openDetail = (test: Test) => router.push(`/admin/tests/${test.id}`);
  const rowKey = (test: Test) => (event: KeyboardEvent<HTMLTableRowElement>) => { if (event.key === "Enter") { event.preventDefault(); openDetail(test); } };
  return <TableShell caption="Assessments"><thead><tr><th>Subject</th><th>Date</th><th>Start time</th><th>Duration</th><th>Lab</th><th>Students</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{tests.map((test) => { const lab = labs.find((l) => l.id === test.labId); return <tr key={test.id} className="clickable-row" tabIndex={0} role="link" aria-label={`Open ${test.title}`} onClick={() => openDetail(test)} onKeyDown={rowKey(test)}>
    <td><span className="table-title">{test.course}</span><small>{test.title} · {test.code}</small></td>
    <td>{formatDate(test.scheduledAt)}</td>
    <td>{formatTime(test.scheduledAt)}</td>
    <td>{test.durationMinutes} minutes</td>
    <td>{lab?.name ?? "Unassigned"}</td>
    <td>{test.assignedStudentIds.length}</td>
    <td><Badge tone={examBadgeTone(test.status)}>{statusLabel(test.status)}</Badge></td>
    <td onClick={(event) => event.stopPropagation()}><div className="row-actions"><ButtonLink href={`/admin/tests/${test.id}`} tone="ghost">View</ButtonLink>{test.status === "live" && <ButtonLink href={`/admin/tests/${test.id}/monitor`} tone="ghost">Monitor <Icon name="chevron" size={15}/></ButtonLink>}</div></td>
  </tr>; })}</tbody></TableShell>;
}

export function TestsScreen() {
  const { state, hydrated } = useExam(); const [filter, setFilter] = useState<"all" | ExamStatus>("all"); if (!hydrated) return <LoadingState/>;
  const tests = filter === "all" ? state.tests : state.tests.filter((t) => t.status === filter);
  return <><PageHeader eyebrow="Assessment management" title="Assessments" description="Create, schedule, and supervise institutional examinations." actions={<ButtonLink href="/admin/tests/create" icon="plus">Create Test</ButtonLink>}/><div className="toolbar"><div className="tabs" role="group" aria-label="Filter assessments">{(["all","scheduled","live","completed","draft"] as const).map((item) => <button key={item} className={filter === item ? "active" : ""} onClick={() => setFilter(item)}>{item === "all" ? "All" : statusLabel(item)} <span>{item === "all" ? state.tests.length : state.tests.filter((t) => t.status === item).length}</span></button>)}</div></div><Card className="table-card">{tests.length ? <TestTable tests={tests} labs={state.labs}/> : <EmptyState title="No assessments in this view" description="Choose another status or create a new assessment." action={<ButtonLink href="/admin/tests/create" icon="plus">Create Test</ButtonLink>}/>}</Card></>;
}

type CreateQuestion = { prompt: string; options: string[]; correctOption: number; marks: number };
const blankQuestion = (): CreateQuestion => ({ prompt: "", options: ["", "", "", ""], correctOption: 0, marks: 2 });

export function CreateTestScreen() {
  const { state, createTest } = useExam();
  const router = useRouter();
  const [errors, setErrors] = useState<Record<string, string>>({});
  // Basic Information (Req 4.2)
  const [title, setTitle] = useState("");
  const [code, setCode] = useState("");
  const [course, setCourse] = useState("");
  const [department, setDepartment] = useState("Computer Science");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  // Schedule (Req 4.3)
  const [date, setDate] = useState("");
  const [startTime, setStartTime] = useState("");
  const [duration, setDuration] = useState(45);
  // Lab Assignment (Req 4.4)
  const [labId, setLabId] = useState(state.labs[0]?.id ?? "");
  // Students (Req 4.5)
  const [selectedStudents, setSelectedStudents] = useState<string[]>([]);
  // Exam Configuration (Req 4.6)
  const [questionsPerStudent, setQuestionsPerStudent] = useState(0);
  const [randomizeQuestions, setRandomizeQuestions] = useState(false);
  const [randomizeOptions, setRandomizeOptions] = useState(false);
  const [allowNavigation, setAllowNavigation] = useState(true);
  const [autoSubmitOnExpiry, setAutoSubmitOnExpiry] = useState(true);
  // Questions
  const [questions, setQuestions] = useState<CreateQuestion[]>([blankQuestion()]);

  const lab = state.labs.find((l) => l.id === labId);
  const totalMarks = questions.reduce((sum, q) => sum + (Number(q.marks) || 0), 0);
  const updateQuestion = (index: number, patch: Partial<CreateQuestion>) => setQuestions((old) => old.map((q, i) => (i === index ? { ...q, ...patch } : q)));
  const toggleStudent = (id: string) => setSelectedStudents((old) => (old.includes(id) ? old.filter((s) => s !== id) : [...old, id]));

  // Combine date + start time into an ISO timestamp for the scheduled slot (Req 4.3).
  const buildScheduledAt = () => (date && startTime ? new Date(`${date}T${startTime}`).toISOString() : undefined);

  const buildInput = (): NewTestInput => ({
    title: title.trim(),
    code: code.trim(),
    course: course.trim(),
    department,
    description: description.trim() || undefined,
    durationMinutes: Number(duration),
    labId,
    scheduledAt: buildScheduledAt(),
    assignedStudentIds: selectedStudents,
    instructions: instructions.split("\n").map((line) => line.trim()).filter(Boolean),
    config: { questionsPerStudent: Number(questionsPerStudent) || 0, randomizeQuestions, randomizeOptions, allowNavigation, autoSubmitOnExpiry },
    questions,
  });

  // Validate required Basic Information and Schedule fields (Req 4.10).
  const validate = () => {
    const next: Record<string, string> = {};
    if (!title.trim()) next.title = "Enter an assessment title.";
    if (!code.trim()) next.code = "Enter a unique exam code.";
    if (!course.trim()) next.course = "Enter the course name.";
    if (!date) next.date = "Choose an examination date.";
    if (!startTime) next.startTime = "Choose a start time.";
    if (!duration || Number(duration) < 5) next.duration = "Set a duration of at least 5 minutes.";
    // A candidate without a seat cannot sit the exam, so the roster may not
    // exceed the assigned venue's workstation count.
    if (!selectedStudents.length) next.students = "Assign at least one candidate.";
    else if (lab && selectedStudents.length > lab.capacity) next.students = `${lab.name} seats ${lab.capacity} candidates; ${selectedStudents.length} are selected.`;
    questions.forEach((q, i) => { if (!q.prompt.trim() || q.options.some((o) => !o.trim())) next[`q${i}`] = "Complete the question and all four options."; });
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  // Create Test: validate, persist as draft, and navigate to the detail page (Req 4.8).
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!validate()) return;
    const id = createTest(buildInput());
    router.push(`/admin/tests/${id}`);
  };

  // Save Draft: persist without navigating away (Req 4.9).
  const saveDraft = () => {
    if (!validate()) return;
    createTest(buildInput());
    router.push("/admin/tests");
  };

  return <><PageHeader eyebrow="Assessments / New" title="Create assessment" description="Set up exam details, schedule, roster, and questions. The assessment will be saved as a draft."/><form className="create-form" onSubmit={submit} noValidate>
    <Card>
      <div className="form-section-heading"><span>01</span><div><h2>Basic information</h2><p>Core details shown to candidates and invigilators.</p></div></div>
      <div className="form-grid">
        <Field name="title" label="Assessment title" placeholder="e.g. Algorithms Mid-Semester" value={title} onChange={(e) => setTitle(e.target.value)} error={errors.title}/>
        <Field name="code" label="Exam code" placeholder="CSE-204-M1" value={code} onChange={(e) => setCode(e.target.value)} error={errors.code}/>
        <Field name="course" label="Course" placeholder="Design and Analysis of Algorithms" value={course} onChange={(e) => setCourse(e.target.value)} error={errors.course}/>
        <Select name="department" label="Department" value={department} onChange={(e) => setDepartment(e.target.value)}><option>Computer Science</option><option>Electronics</option><option>Information Technology</option></Select>
      </div>
      <label className="field" style={{ marginTop: 18 }}><span>Description</span><textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Short summary of the assessment scope"/></label>
      <label className="field" style={{ marginTop: 18 }}><span>Instructions (one per line)</span><textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} placeholder={"Answer all questions.\nDo not refresh the exam window."}/></label>
    </Card>

    <Card>
      <div className="form-section-heading"><span>02</span><div><h2>Schedule</h2><p>When the examination begins and how long it runs.</p></div></div>
      <div className="form-grid">
        <Field name="date" label="Date" type="date" value={date} onChange={(e) => setDate(e.target.value)} error={errors.date}/>
        <Field name="startTime" label="Start time" type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} error={errors.startTime}/>
        <Field name="duration" label="Duration (minutes)" type="number" min={5} max={180} value={duration} onChange={(e) => setDuration(Number(e.target.value))} error={errors.duration}/>
      </div>
    </Card>

    <Card>
      <div className="form-section-heading"><span>03</span><div><h2>Lab assignment</h2><p>Choose the venue hosting this examination.</p></div></div>
      <div className="form-grid">
        <Select name="lab" label="Assigned laboratory" value={labId} onChange={(e) => setLabId(e.target.value)}>{state.labs.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</Select>
        {lab && <div className="field"><span>Venue capacity</span><p style={{ margin: 0, color: "var(--muted)", fontSize: 12, fontWeight: 400 }}>{lab.building} · {lab.capacity} workstations · {lab.available} available</p></div>}
      </div>
    </Card>

    <Card>
      <div className="form-section-heading"><span>04</span><div><h2>Students</h2><p>Select the candidates assigned to this examination.</p></div></div>
      <div className="toolbar split" style={{ marginBottom: 14 }}>
        <Badge tone={errors.students ? "danger" : "info"}>{selectedStudents.length} selected{lab ? ` / ${lab.capacity} seats` : ""}</Badge>
        <div className="row-actions"><Button type="button" tone="ghost" onClick={() => setSelectedStudents(state.students.filter((s) => s.status === "active").map((s) => s.id))}>Select all eligible</Button><Button type="button" tone="ghost" onClick={() => setSelectedStudents([])}>Clear</Button></div>
      </div>
      {errors.students && <p className="field-error" style={{ marginTop: 0, marginBottom: 12 }}>{errors.students}</p>}
      <div className="student-picker">{state.students.map((student) => <label key={student.id} className={`picker-option ${selectedStudents.includes(student.id) ? "selected" : ""}`}><input type="checkbox" checked={selectedStudents.includes(student.id)} disabled={student.status === "blocked"} onChange={() => toggleStudent(student.id)}/><span><strong>{student.name}</strong><small>{student.registrationNo} · {student.program}</small></span></label>)}</div>
    </Card>

    <Card>
      <div className="form-section-heading"><span>05</span><div><h2>Exam configuration</h2><p>Delivery rules applied to each candidate session.</p></div></div>
      <div className="form-grid">
        <Field name="questionsPerStudent" label="Questions per student" type="number" min={0} value={questionsPerStudent} onChange={(e) => setQuestionsPerStudent(Number(e.target.value))} hint="0 uses every question in the paper"/>
      </div>
      <div className="config-toggles">
        <label className="toggle-option"><input type="checkbox" checked={randomizeQuestions} onChange={(e) => setRandomizeQuestions(e.target.checked)}/><span><strong>Randomize questions</strong><small>Shuffle question order per candidate</small></span></label>
        <label className="toggle-option"><input type="checkbox" checked={randomizeOptions} onChange={(e) => setRandomizeOptions(e.target.checked)}/><span><strong>Randomize options</strong><small>Shuffle answer choices per question</small></span></label>
        <label className="toggle-option"><input type="checkbox" checked={allowNavigation} onChange={(e) => setAllowNavigation(e.target.checked)}/><span><strong>Allow navigation</strong><small>Let candidates revisit earlier questions</small></span></label>
        <label className="toggle-option"><input type="checkbox" checked={autoSubmitOnExpiry} onChange={(e) => setAutoSubmitOnExpiry(e.target.checked)}/><span><strong>Auto-submit on expiry</strong><small>Submit automatically when time runs out</small></span></label>
      </div>
    </Card>

    <Card>
      <div className="form-section-heading"><span>06</span><div><h2>Questions</h2><p>Add objective questions, answer choices, and the correct response.</p></div></div>
      <div className="question-builder">{questions.map((q, index) => <fieldset key={index} className="builder-item"><legend>Question {index + 1}</legend><label className="field"><span>Question prompt</span><textarea value={q.prompt} onChange={(e) => updateQuestion(index, { prompt: e.target.value })} placeholder="Enter a clear, unambiguous question"/></label><div className="option-builder">{q.options.map((option, optionIndex) => <label key={optionIndex} className="builder-option"><input type="radio" name={`correct-${index}`} checked={q.correctOption === optionIndex} onChange={() => updateQuestion(index, { correctOption: optionIndex })}/><input aria-label={`Option ${optionIndex + 1}`} value={option} onChange={(e) => updateQuestion(index, { options: q.options.map((old, i) => i === optionIndex ? e.target.value : old) })} placeholder={`Option ${String.fromCharCode(65 + optionIndex)}`}/></label>)}</div><Field label="Marks" type="number" min={1} value={q.marks} onChange={(e) => updateQuestion(index, { marks: Number(e.target.value) })}/>{errors[`q${index}`] && <p className="field-error">{errors[`q${index}`]}</p>}{questions.length > 1 && <Button type="button" tone="ghost" onClick={() => setQuestions((old) => old.filter((_, i) => i !== index))}>Remove question</Button>}</fieldset>)}</div>
      <Button type="button" tone="secondary" icon="plus" onClick={() => setQuestions((old) => [...old, blankQuestion()])}>Add another question</Button>
    </Card>

    <Card>
      <div className="form-section-heading"><span>07</span><div><h2>Review</h2><p>Confirm the assessment summary before creating.</p></div></div>
      <dl className="review-grid">
        <div><dt>Title</dt><dd>{title || "—"}</dd></div>
        <div><dt>Exam code</dt><dd>{code || "—"}</dd></div>
        <div><dt>Course</dt><dd>{course || "—"}</dd></div>
        <div><dt>Department</dt><dd>{department}</dd></div>
        <div><dt>Schedule</dt><dd>{date && startTime ? formatDateTime(buildScheduledAt()!) : "Not scheduled"}</dd></div>
        <div><dt>Duration</dt><dd>{duration} minutes</dd></div>
        <div><dt>Laboratory</dt><dd>{lab?.name ?? "—"}</dd></div>
        <div><dt>Students assigned</dt><dd>{selectedStudents.length}</dd></div>
        <div><dt>Questions / marks</dt><dd>{questions.length} / {totalMarks}</dd></div>
        <div><dt>Delivery rules</dt><dd>{[randomizeQuestions && "Randomize questions", randomizeOptions && "Randomize options", allowNavigation && "Navigation allowed", autoSubmitOnExpiry && "Auto-submit"].filter(Boolean).join(" · ") || "Defaults"}</dd></div>
      </dl>
    </Card>

    <div className="form-footer"><Button type="button" tone="ghost" onClick={() => router.back()}>Cancel</Button><Button type="button" tone="secondary" onClick={saveDraft}>Save draft</Button><Button type="submit" icon="check">Create test</Button></div>
  </form></>;
}



// Join the assigned roster with each candidate's computer and live session so
// the detail page renders roll, name, computer, connection, and exam status
// consistently across every lifecycle state.
function buildRosterRows(test: Test, sessions: ExamSession[], computers: Computer[], students: Student[]): DetailRosterRow[] {
  const studentById = new Map(students.map((s) => [s.id, s]));
  return test.assignedStudentIds.map((sid) => {
    const student = studentById.get(sid);
    const session = sessions.find((item) => item.testId === test.id && item.studentId === sid);
    const computer = computers.find((c) => c.id === session?.computerId) ?? computers.find((c) => c.assignedStudentId === sid);
    return {
      studentId: sid,
      name: student?.name ?? "Unassigned candidate",
      registrationNo: student?.registrationNo ?? "—",
      computerId: computer?.id ?? "Unassigned",
      connection: session?.connection ?? "offline",
      examStatus: session?.examStatus ?? "not-ready",
    };
  });
}

interface DetailRosterRow {
  studentId: string;
  name: string;
  registrationNo: string;
  computerId: string;
  connection: ConnectionStatus;
  examStatus: StudentExamStatus;
}

export function TestDetailScreen() {
  const params = useParams<{ id: string }>(); const router = useRouter(); const { state, hydrated, scheduleExam, startExam } = useExam(); const [confirm, setConfirm] = useState(false);
  const roster = useMemo(() => {
    const test = state.tests.find((item) => item.id === params.id);
    return test ? buildRosterRows(test, state.sessions, state.computers, state.students) : [];
  }, [state.tests, state.sessions, state.computers, state.students, params.id]);
  if (!hydrated) return <LoadingState/>;
  const test = state.tests.find((item) => item.id === params.id);
  if (!test) return <EmptyState title="Assessment not found" description="This assessment may have been removed from local demo data." action={<ButtonLink href="/admin/tests">Back to assessments</ButtonLink>}/>;
  const lab = state.labs.find((l) => l.id === test.labId);
  const launch = () => { startExam(test.id); setConfirm(false); router.push(`/admin/tests/${test.id}/monitor`); };
  return <><div className="breadcrumb"><Link href="/admin/tests">Assessments</Link><Icon name="chevron" size={14}/><span>{test.code}</span></div><PageHeader title={test.title} description={`${test.course} · ${test.department}`} actions={<>{test.status === "draft" && <Button icon="calendar" onClick={() => scheduleExam(test.id)}>Schedule assessment</Button>}{test.status === "scheduled" && <><Button icon="send" onClick={() => setConfirm(true)}>Start examination</Button><Button tone="secondary" icon="file" title="Editing opens in a later phase">Edit test</Button><ButtonLink href={`/admin/tests/${test.id}/monitor`} tone="ghost" icon="monitor">Monitor exam</ButtonLink></>}{test.status === "live" && <ButtonLink href={`/admin/tests/${test.id}/monitor`} icon="monitor">Open live monitor</ButtonLink>}</>}/><div className="detail-grid"><div className="detail-main"><Card className="detail-hero"><div><Badge tone={examBadgeTone(test.status)}>{statusLabel(test.status)}</Badge><span className="exam-code">{test.code}</span></div><div className="detail-facts"><div><Icon name="calendar"/><span><small>Start time</small><strong>{formatDateTime(test.scheduledAt)}</strong></span></div><div><Icon name="clock"/><span><small>Duration</small><strong>{test.durationMinutes} minutes</strong></span></div><div><Icon name="users"/><span><small>Students</small><strong>{test.assignedStudentIds.length} assigned</strong></span></div><div><Icon name="monitor"/><span><small>Lab</small><strong>{lab?.name ?? "Unassigned"}</strong></span></div><div><Icon name="file"/><span><small>Questions / marks</small><strong>{test.questions.length} / {test.totalMarks}</strong></span></div></div></Card><Card className="table-card"><div className="section-heading"><div><p className="eyebrow">Candidate roster</p><h2>Assigned students</h2></div><Badge tone="info">{roster.length} students</Badge></div>{roster.length ? <TableShell caption="Assigned candidates"><thead><tr><th>Roll number</th><th>Student</th><th>Computer</th><th>Connection</th><th>Exam status</th></tr></thead><tbody>{roster.map((row) => <tr key={row.studentId}><td>{row.registrationNo}</td><td className="table-title">{row.name}</td><td>{row.computerId}</td><td><StatusDot status={row.connection}/></td><td><Badge tone={examStatusTone(row.examStatus)}>{EXAM_STATUS_LABEL[row.examStatus]}</Badge></td></tr>)}</tbody></TableShell> : <EmptyState title="No students assigned" description="Edit the assessment to assign candidates before starting."/>}</Card><Card><div className="section-heading"><div><p className="eyebrow">Paper preview</p><h2>Questions</h2></div><Badge>{test.totalMarks} marks</Badge></div><ol className="preview-list">{test.questions.map((q) => <li key={q.id}><span>{q.prompt}</span><small>{q.marks} marks · {q.options.length} options</small></li>)}</ol></Card></div><aside className="detail-side"><Card><h2>Launch readiness</h2><div className="check-list"><p><Icon name="check"/> Question paper validated</p><p><Icon name="check"/> Candidate roster assigned</p><p><Icon name="check"/> {lab?.available} devices available</p><p className={lab?.status === "maintenance" ? "not-ready" : ""}><Icon name={lab?.status === "maintenance" ? "alert" : "check"}/> Lab environment {lab?.status}</p></div></Card><Card><h2>Instructions</h2><ul className="instruction-list">{test.instructions.map((instruction) => <li key={instruction}>{instruction}</li>)}</ul></Card></aside></div><Modal open={confirm} onClose={() => setConfirm(false)} title="Start this examination now?" description="This begins the examination for all connected students, opens the student entry gate, and starts the shared countdown. This action should only be taken when invigilators are ready." actions={<><Button tone="secondary" onClick={() => setConfirm(false)}>Cancel</Button><Button icon="send" onClick={launch}>Confirm & start</Button></>}><div className="launch-summary"><strong>{test.title}</strong><span>{test.assignedStudentIds.length} assigned students · {test.durationMinutes} minutes · {test.questions.length} questions · {lab?.name}</span></div></Modal></>;
}

// Derive the academic branch and year shown in the students table (Req 8.1).
const branchOf = (program: string) => program.includes("CSE") ? "CSE" : program.includes("ECE") ? "ECE" : program.includes("IT") ? "IT" : program;
const yearOf = (semester: number) => Math.ceil(semester / 2);
const yearLabel = (semester: number) => { const y = yearOf(semester); return ["1st", "2nd", "3rd", "4th"][y - 1] ?? `${y}th`; };

interface StudentRow {
  student: Student;
  branch: string;
  year: number;
  labName: string;
}

// Join each student with their assigned lab via the computer roster (Req 8.1).
function buildStudentRows(students: Student[], computers: Computer[], labs: Lab[]): StudentRow[] {
  const labById = new Map(labs.map((l) => [l.id, l]));
  return students.map((student) => {
    const computer = computers.find((c) => c.assignedStudentId === student.id);
    const lab = computer ? labById.get(computer.labId) : undefined;
    return { student, branch: branchOf(student.program), year: yearOf(student.semester), labName: lab?.name ?? "Unassigned" };
  });
}

// Reusable table listing candidate roll, name, branch, year, status, and lab (Req 8.1, 19.1).
export function StudentTable({ rows }: { rows: StudentRow[] }) {
  return <TableShell caption="Registered candidates"><thead><tr><th>Roll number</th><th>Student</th><th>Branch</th><th>Year</th><th>Section</th><th>Status</th><th>Assigned lab</th></tr></thead><tbody>{rows.map(({ student, branch, labName }) => <tr key={student.id}>
    <td><strong>{student.registrationNo}</strong></td>
    <td><div className="person-cell"><span className="avatar">{initials(student.name)}</span><div><strong>{student.name}</strong><small>{student.email}</small></div></div></td>
    <td>{branch}</td>
    <td>{yearLabel(student.semester)} year</td>
    <td>{student.section}</td>
    <td><Badge tone={student.status === "active" ? "success" : "danger"}>{student.status === "active" ? "Eligible" : "Blocked"}</Badge></td>
    <td>{labName}</td>
  </tr>)}</tbody></TableShell>;
}

export function StudentsScreen() {
  const { state, hydrated } = useExam();
  const [query, setQuery] = useState("");
  const [year, setYear] = useState("all");
  const [branch, setBranch] = useState("all");
  const [section, setSection] = useState("all");

  const rows = useMemo(() => buildStudentRows(state.students, state.computers, state.labs), [state.students, state.computers, state.labs]);
  // Filter option values derived from the roster so they stay in sync with seed data (Req 8.3).
  const branches = useMemo(() => [...new Set(rows.map((r) => r.branch))].sort(), [rows]);
  const years = useMemo(() => [...new Set(rows.map((r) => r.year))].sort((a, b) => a - b), [rows]);
  const sections = useMemo(() => [...new Set(rows.map((r) => r.student.section))].sort(), [rows]);

  if (!hydrated) return <LoadingState/>;

  // Search matches name or roll number (Req 8.2, 8.4); dropdowns narrow by year/branch/section (Req 8.3).
  const term = query.trim().toLowerCase();
  const filtered = rows.filter(({ student, branch: b, year: y }) => {
    const matchesSearch = !term || student.name.toLowerCase().includes(term) || student.registrationNo.toLowerCase().includes(term);
    return matchesSearch && (year === "all" || String(y) === year) && (branch === "all" || b === branch) && (section === "all" || student.section === section);
  });

  return <><PageHeader eyebrow="Candidate management" title="Students" description="Review eligibility, registration, and lab assignment for every candidate." actions={<Button tone="secondary" icon="plus">Import roster</Button>}/>
    <div className="toolbar split">
      <div className="search-box wide"><Icon name="search"/><input value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search students by name or roll number" placeholder="Search by name or roll number"/></div>
      <div className="filter-group">
        <Select label="Year" value={year} onChange={(e) => setYear(e.target.value)}><option value="all">All years</option>{years.map((y) => <option key={y} value={String(y)}>{yearLabel(y * 2)} year</option>)}</Select>
        <Select label="Branch" value={branch} onChange={(e) => setBranch(e.target.value)}><option value="all">All branches</option>{branches.map((b) => <option key={b} value={b}>{b}</option>)}</Select>
        <Select label="Section" value={section} onChange={(e) => setSection(e.target.value)}><option value="all">All sections</option>{sections.map((s) => <option key={s} value={s}>Section {s}</option>)}</Select>
        <Badge tone="info">{filtered.length} candidates</Badge>
      </div>
    </div>
    <Card className="table-card">{filtered.length ? <StudentTable rows={filtered}/> : <EmptyState icon="users" title="No matching students" description="Adjust the search text or clear the year, branch, and section filters to see more candidates."/>}</Card>
  </>;
}

// Time between a test's scheduled start and a candidate's submission (Req 10.2).
function timeTaken(test: Test | undefined, submittedAt: string) {
  if (!test) return "—";
  const seconds = Math.round((new Date(submittedAt).getTime() - new Date(test.scheduledAt).getTime()) / 1000);
  return seconds > 0 ? formatDuration(seconds) : "—";
}

export function ResultsScreen() {
  const { state, hydrated } = useExam();
  const [testFilter, setTestFilter] = useState("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Filter to the chosen assessment, then rank by percentage (highest = rank 1) (Req 10.2).
  const ranked = useMemo(() =>
    state.results
      .filter((r) => testFilter === "all" || r.testId === testFilter)
      .sort((a, b) => percentage(b.score, b.total) - percentage(a.score, a.total))
      .map((result, index) => ({ result, rank: index + 1 })),
  [state.results, testFilter]);

  // Aggregate stats: submitted count, average percentage, highest percentage (Req 10.1).
  const stats = useMemo(() => {
    if (!ranked.length) return { submitted: 0, average: 0, highest: 0, topName: "—" };
    const percentages = ranked.map(({ result }) => percentage(result.score, result.total));
    const top = ranked[0];
    const topStudent = state.students.find((s) => s.id === top.result.studentId);
    return {
      submitted: ranked.length,
      average: Math.round(percentages.reduce((sum, p) => sum + p, 0) / percentages.length),
      highest: percentages[0],
      topName: topStudent?.name ?? "—",
    };
  }, [ranked, state.students]);

  if (!hydrated) return <LoadingState/>;

  const selected = selectedId ? ranked.find(({ result }) => result.id === selectedId) : undefined;
  const selectedStudent = selected ? state.students.find((s) => s.id === selected.result.studentId) : undefined;
  const selectedTest = selected ? state.tests.find((t) => t.id === selected.result.testId) : undefined;

  return <>
    <PageHeader eyebrow="Outcomes" title="Results" description="Review synchronized submissions and candidate performance." actions={<Button tone="secondary" icon="file" title="Report export is available in a later phase">Export report</Button>}/>
    <div className="toolbar split">
      <Select label="Assessment" value={testFilter} onChange={(e) => setTestFilter(e.target.value)}><option value="all">All assessments</option>{state.tests.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}</Select>
      <Badge tone="info">{ranked.length} results</Badge>
    </div>
    <div className="stats-grid three">
      <StatCard label="Students submitted" value={stats.submitted} detail="Recorded submissions" icon="file" tone="blue"/>
      <StatCard label="Average score" value={stats.submitted ? `${stats.average}%` : "—"} detail="Across current selection" icon="chart" tone="teal"/>
      <StatCard label="Highest score" value={stats.submitted ? `${stats.highest}%` : "—"} detail={stats.submitted ? stats.topName : "No submissions"} icon="shield" tone="navy"/>
    </div>
    <Card className="table-card">
      {ranked.length ? <TableShell caption="Exam results">
        <thead><tr><th>Rank</th><th>Candidate</th><th>Roll number</th><th>Score</th><th>Percentage</th><th>Time taken</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{ranked.map(({ result, rank }) => { const student = state.students.find((s) => s.id === result.studentId); const test = state.tests.find((t) => t.id === result.testId); return <tr key={result.id}>
          <td><strong>#{rank}</strong></td>
          <td className="table-title">{student?.name ?? "Unknown candidate"}</td>
          <td>{student?.registrationNo ?? "—"}</td>
          <td><strong>{formatScore(result.score, result.total)}</strong></td>
          <td><span className="score-pill">{percentage(result.score, result.total)}%</span></td>
          <td>{timeTaken(test, result.submittedAt)}</td>
          <td><Badge tone={result.mode === "automatic" ? "warning" : "success"}>{result.mode === "automatic" ? "Auto-submitted" : "Submitted"}</Badge></td>
          <td><div className="row-actions"><Button tone="ghost" onClick={() => setSelectedId(result.id)}>View result</Button></div></td>
        </tr>; })}</tbody>
      </TableShell> : <EmptyState icon="file" title="No results yet" description="Results appear here once candidates submit a completed examination. Choose a different assessment to review other outcomes."/>}
    </Card>
    <Modal open={Boolean(selected)} onClose={() => setSelectedId(null)} title="Candidate result" description={selectedTest ? `${selectedTest.title} · ${selectedTest.code}` : undefined} actions={<Button onClick={() => setSelectedId(null)}>Close</Button>}>
      {selected && <dl className="review-grid">
        <div><dt>Candidate</dt><dd>{selectedStudent?.name ?? "Unknown"}</dd></div>
        <div><dt>Roll number</dt><dd>{selectedStudent?.registrationNo ?? "—"}</dd></div>
        <div><dt>Rank</dt><dd>#{selected.rank}</dd></div>
        <div><dt>Score</dt><dd>{formatScore(selected.result.score, selected.result.total)}</dd></div>
        <div><dt>Percentage</dt><dd>{percentage(selected.result.score, selected.result.total)}%</dd></div>
        <div><dt>Time taken</dt><dd>{timeTaken(selectedTest, selected.result.submittedAt)}</dd></div>
        <div><dt>Submitted</dt><dd>{formatDateTime(selected.result.submittedAt)}</dd></div>
        <div><dt>Status</dt><dd>{selected.result.mode === "automatic" ? "Auto-submitted" : "Submitted"}</dd></div>
      </dl>}
    </Modal>
  </>;
}

// Distinct severity indicators for audit events (Req 11.2).
const AUDIT_SEVERITY_LABEL: Record<AuditSeverity, string> = { info: "Info", warning: "Warning", critical: "Critical" };
const auditSeverityTone = (severity: AuditSeverity) => severity === "critical" ? "danger" : severity === "warning" ? "warning" : "neutral";

// Audit filter tabs mapped to the selector filter values (Req 11.3).
const AUDIT_FILTERS: Array<{ value: AuditFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "warnings", label: "Warnings" },
  { value: "critical", label: "Critical" },
  { value: "connection", label: "Connection" },
  { value: "exam", label: "Exam Events" },
];

export function AuditScreen() {
  const { state, hydrated, resetDemo } = useExam();
  const [filter, setFilter] = useState<AuditFilter>("all");

  // Newest-first ordering for the trail, then apply the active filter (Req 11.4).
  const ordered = useMemo(() => [...state.audits].sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime()), [state.audits]);
  const events = useMemo(() => filterAuditEvents(ordered, filter), [ordered, filter]);
  const studentName = (id?: string) => (id ? state.students.find((s) => s.id === id)?.name ?? "Unknown" : "System");

  if (!hydrated) return <LoadingState/>;

  return <>
    <PageHeader eyebrow="Governance" title="Audit log" description="An immutable-style activity trail for this browser demo session." actions={<Button tone="secondary" icon="reset" onClick={resetDemo}>Reset demo</Button>}/>
    <div className="toolbar"><div className="tabs" role="group" aria-label="Filter audit events">{AUDIT_FILTERS.map(({ value, label }) => <button key={value} className={filter === value ? "active" : ""} onClick={() => setFilter(value)}>{label} <span>{filterAuditEvents(ordered, value).length}</span></button>)}</div></div>
    <Card className="table-card">{events.length ? <TableShell caption="Audit events">
      <thead><tr><th>Timestamp</th><th>Student</th><th>Computer</th><th>Event</th><th>Severity</th><th>Details</th></tr></thead>
      <tbody>{events.map((event) => <tr key={event.id}>
        <td>{formatDateTime(event.at)}</td>
        <td className="table-title">{studentName(event.studentId)}</td>
        <td>{event.computerId ?? "—"}</td>
        <td>{event.action}</td>
        <td><Badge tone={auditSeverityTone(event.severity)}>{AUDIT_SEVERITY_LABEL[event.severity]}</Badge></td>
        <td>{event.detail}</td>
      </tr>)}</tbody>
    </TableShell> : <EmptyState icon="shield" title="No audit events in this view" description="Choose a different filter to review other logged connection and exam events."/>}</Card>
  </>;
}

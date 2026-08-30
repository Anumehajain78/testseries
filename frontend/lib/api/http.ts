import type { AnswerValue, AuditEvent, Computer, ExamSession, ExamState, Lab, Question, Result, Student, Test } from "@/lib/types";
import { toConnection, toExamStatus, toSessionStatus } from "./contract";
import type {
  AuditEventDto,
  ComputerDto,
  ExamDetailDto,
  ExamSummaryDto,
  LabDto,
  ResultsPageDto,
  SessionRowDto,
  StudentDto,
  TokenPairDto,
} from "./contract";

// ---------------------------------------------------------------------------
// HTTP read client
//
// Reads only. Writes still go through the mock implementation until step 05,
// which is why this module exports a loader rather than an ExamApi: the goal of
// this step is that every admin screen renders from Postgres, without those
// screens having to change.
//
// The loader assembles one ExamState from several endpoints. That is a bridge,
// not the destination — per-screen queries with their own loading and error
// states are a later step, and this shape is what makes the cutover reversible
// by a single environment variable in the meantime.
// ---------------------------------------------------------------------------

const BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1").replace(/\/$/, "");
const TOKEN_KEY = "northbridge-access-token";

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export function readToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function storeToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // A blocked storage API must not stop the session; the token simply lives
    // for this page only.
  }
}

async function request<T>(path: string): Promise<T> {
  const token = readToken();
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    cache: "no-store",
  });
  if (!response.ok) {
    // 401 means the token is missing or expired; the caller clears it and
    // re-prompts rather than retrying into a loop.
    const detail = await response.text().catch(() => "");
    throw new ApiError(response.status, detail || response.statusText);
  }
  return (await response.json()) as T;
}

export async function signIn(email: string, password: string): Promise<TokenPairDto> {
  const response = await fetch(`${BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    throw new ApiError(response.status, response.status === 401 ? "Incorrect email or password" : "Sign-in failed");
  }
  const tokens = (await response.json()) as TokenPairDto;
  storeToken(tokens.accessToken);
  return tokens;
}

// ---------------------------------------------------------------------------
// DTO -> domain mapping
//
// The screens keep their existing types; only this layer knows the wire shape.
// ---------------------------------------------------------------------------

interface PageDto<T> { items: T[]; total: number; limit: number; offset: number }

const toTest = (exam: ExamSummaryDto, detail?: ExamDetailDto): Test => ({
  id: exam.id,
  title: exam.title,
  code: exam.code,
  course: exam.course,
  department: exam.department,
  description: detail?.description ?? undefined,
  durationMinutes: exam.durationMinutes,
  totalMarks: exam.totalMarks,
  scheduledAt: exam.scheduledAt,
  status: toExamStatus(exam.status),
  labId: exam.labId,
  // The roster lives on sessions; enrolment ids are filled in from those below.
  assignedStudentIds: [],
  instructions: detail?.instructions ?? [],
  questions: (detail?.questions ?? []).map(toQuestion),
  config: {
    questionsPerStudent: detail?.config?.questionsPerStudent ?? 0,
    randomizeQuestions: detail?.config?.randomizeQuestions ?? false,
    randomizeOptions: detail?.config?.randomizeOptions ?? false,
    allowNavigation: detail?.config?.allowNavigation ?? true,
    autoSubmitOnExpiry: detail?.config?.autoSubmitOnExpiry ?? true,
  },
  endsAt: exam.endsAt ?? undefined,
});

const toQuestion = (question: NonNullable<ExamDetailDto["questions"]>[number]): Question => ({
  id: question.id,
  type: question.type,
  prompt: question.prompt,
  marks: question.marks,
  options: (question.options ?? []).map((option) => option.body),
  correctOption: (question.options ?? []).findIndex((option) => option.isCorrect) >= 0
    ? (question.options ?? []).findIndex((option) => option.isCorrect)
    : undefined,
  correctOptions: (question.options ?? [])
    .map((option, index) => (option.isCorrect ? index : -1))
    .filter((index) => index >= 0),
});

const toStudent = (student: StudentDto): Student => ({
  id: student.id,
  registrationNo: student.registrationNo,
  name: student.fullName,
  email: student.email,
  program: student.program,
  semester: student.semester,
  section: student.section,
  status: student.status === "BLOCKED" ? "blocked" : "active",
  seat: `${student.section}-${student.registrationNo.slice(-2)}`,
});

const toLab = (lab: LabDto): Lab => ({
  id: lab.id,
  name: lab.name,
  building: lab.building,
  capacity: lab.capacity,
  available: lab.onlineCount,
  invigilator: lab.invigilatorName ?? "Unassigned",
  status: lab.status === "MAINTENANCE" ? "maintenance" : lab.status === "OCCUPIED" ? "occupied" : "ready",
});

const toComputer = (computer: ComputerDto): Computer => ({
  id: computer.machineId,
  labId: computer.labId,
  index: computer.position,
  connection: toConnection(computer.connection),
});

const toSession = (examId: string, row: SessionRowDto): ExamSession => ({
  testId: examId,
  studentId: row.studentId,
  computerId: row.machineId ?? "Unassigned",
  connection: toConnection(row.connection),
  examStatus: toSessionStatus(row.status),
  loginAt: row.checkedInAt ?? undefined,
  examStartedAt: row.startedAt ?? undefined,
  lastHeartbeatAt: row.lastHeartbeatAt ?? undefined,
  warnings: row.warningCount ?? 0,
  activity: [],
});

const toResults = (page: ResultsPageDto): Result[] =>
  (page.rows ?? []).map((row) => ({
    id: row.sessionId,
    testId: page.examId,
    studentId: row.studentId,
    // A withheld score arrives as null. The Results screen has no "not yet
    // published" state of its own yet, so it would render this as 0%. Until
    // that state exists (it belongs with the publish action), only published
    // results are mapped through — see the filter in loadStateFromServer.
    score: row.score ?? 0,
    total: row.maxScore,
    submittedAt: row.submittedAt,
    mode: row.mode === "AUTO" ? "automatic" : "manual",
  }));

const toAudit = (event: AuditEventDto): AuditEvent => ({
  id: event.id,
  at: event.occurredAt,
  actor: event.actorLabel,
  action: event.event.replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase()),
  detail: event.detail,
  studentId: event.studentId ?? undefined,
  computerId: event.machineId ?? undefined,
  category: event.category === "CONNECTION" ? "connection" : event.category === "EXAM" ? "exam" : "system",
  severity: event.severity === "CRITICAL" ? "critical" : event.severity === "WARNING" ? "warning" : "info",
});

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

/**
 * Assemble the whole admin world from the API.
 *
 * Deliberately eager: it fetches each exam's detail and roster so the existing
 * screens keep reading synchronously from one snapshot. That is N+1 by
 * construction and is the reason this is a bridge — it is fine for a few dozen
 * exams and must not survive into production.
 */
export async function loadStateFromServer(): Promise<Partial<ExamState>> {
  // Rejecting here rather than firing a fan-out of requests that all 401 keeps
  // the "not signed in" case off the network entirely, and lets the caller
  // handle it on the same code path as an expired token.
  if (!readToken()) throw new ApiError(401, "Not signed in");

  const [examPage, studentPage, labs, auditPage] = await Promise.all([
    request<PageDto<ExamSummaryDto>>("/exams?limit=200"),
    request<PageDto<StudentDto>>("/students?limit=200"),
    request<LabDto[]>("/labs"),
    request<PageDto<AuditEventDto>>("/audit?limit=200"),
  ]);

  const details = await Promise.all(
    examPage.items.map((exam) => request<ExamDetailDto>(`/exams/${exam.id}`)),
  );
  const rosters = await Promise.all(
    examPage.items.map((exam) => request<SessionRowDto[]>(`/exams/${exam.id}/sessions`)),
  );
  const computerLists = await Promise.all(
    labs.map((lab) => request<ComputerDto[]>(`/labs/${lab.id}/computers`)),
  );
  // Results only exist for exams that have finished.
  const resultPages = await Promise.all(
    examPage.items
      .filter((exam) => exam.status === "COMPLETED")
      .map((exam) => request<ResultsPageDto>(`/exams/${exam.id}/results`)),
  );

  const sessions: ExamSession[] = [];
  const tests: Test[] = examPage.items.map((exam, index) => {
    const roster = rosters[index] ?? [];
    sessions.push(...roster.map((row) => toSession(exam.id, row)));
    return {
      ...toTest(exam, details[index]),
      assignedStudentIds: roster.map((row) => row.studentId),
    };
  });

  // The server has no permanent student-to-machine binding — seating is a fact
  // about an exam, not a property of the workstation. The screens that still
  // ask "which lab is this candidate in?" are answered from where the candidate
  // is actually seated right now, which is the truthful reading of that
  // question in a lab that hosts a different cohort every hour.
  const seatedBy = new Map<string, string>();
  for (const session of sessions) {
    if (session.computerId !== "Unassigned") seatedBy.set(session.computerId, session.studentId);
  }
  const computers: Computer[] = computerLists.flat().map((dto) => ({
    ...toComputer(dto),
    assignedStudentId: seatedBy.get(dto.machineId),
  }));

  return {
    version: 2,
    tests,
    students: studentPage.items.map(toStudent),
    labs: labs.map(toLab),
    computers,
    sessions,
    // Unpublished pages are dropped rather than shown as zeros: an empty
    // results table is honest, a table of 0% is not.
    results: resultPages.filter((page) => page.published).flatMap(toResults),
    audits: auditPage.items.map(toAudit),
    submissions: [],
    answers: {} as Record<string, Record<string, AnswerValue>>,
    flags: {},
    toasts: [],
    mockResultMode: resultPages.some((page) => page.published),
  };
}

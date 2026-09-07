import type { AnswerValue, AuditEvent, Computer, ExamSession, ExamState, Lab, Question, Result, Student, Test } from "@/lib/types";
import { toConnection, toExamStatus, toSessionStatus } from "./contract";
import type {
  AuditEventDto,
  ComputerDto,
  ExamDetailDto,
  ExamSummaryDto,
  ExamWindowDto,
  LabDto,
  SessionPaperDto,
  SessionStateDto,
  SubmissionReceiptDto,
  ResultsPageDto,
  SessionRowDto,
  StudentDto,
  TokenPairDto,
} from "./contract";

// ---------------------------------------------------------------------------
// HTTP client
//
// Reads assemble one snapshot the existing screens consume synchronously;
// writes go straight to the API and then reload that snapshot, so a transition
// the server refuses never appears to have happened locally.
//
// The loader assembles one ExamState from several endpoints. That is a bridge,
// not the destination — per-screen queries with their own loading and error
// states are a later step, and this shape is what makes the cutover reversible
// by a single environment variable in the meantime.
// ---------------------------------------------------------------------------

const BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1").replace(/\/$/, "");
const TOKEN_KEY = "northbridge-access-token";
const USER_KEY = "northbridge-user";

export interface SignedInUser { id: string; role: string; fullName: string }

export function readUser(): SignedInUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as SignedInUser) : null;
  } catch {
    return null;
  }
}

function storeUser(user: SignedInUser | null): void {
  try {
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
    else localStorage.removeItem(USER_KEY);
  } catch {
    // Non-fatal: the session simply does not survive a reload.
  }
}

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
  if (!token) storeUser(null);
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // A blocked storage API must not stop the session; the token simply lives
    // for this page only.
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = readToken();
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    // 401 means the token is missing or expired; the caller clears it and
    // re-prompts rather than retrying into a loop.
    throw new ApiError(response.status, await describe(response));
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

/**
 * Turn an error body into something worth showing a person.
 *
 * The server answers a refused transition with both states and a message; a
 * validation failure answers with FastAPI's array. Either beats "Bad Request".
 */
async function describe(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (detail?.message) return detail.message;
    if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
  } catch {
    // fall through to the status text
  }
  return response.statusText || `Request failed (${response.status})`;
}

// ---------------------------------------------------------------------------
// Writes
//
// Each returns the server's answer; the caller reloads the snapshot afterwards.
// ---------------------------------------------------------------------------

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

const put = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "PUT", body: body === undefined ? undefined : JSON.stringify(body) });

export const candidateWrites = {
  checkIn: (sessionId: string, machineId?: string) =>
    post<SessionPaperDto>(`/sessions/${sessionId}/checkin`, { machineId: machineId ?? null }),
  saveAnswer: (sessionId: string, questionId: string, value: unknown, clientSeq: number) =>
    put(`/sessions/${sessionId}/answers/${questionId}`, { value, clientSeq }),
  toggleFlag: (sessionId: string, questionId: string) =>
    put(`/sessions/${sessionId}/flags/${questionId}`, {}),
  submit: (sessionId: string) => post<SubmissionReceiptDto>(`/sessions/${sessionId}/submit`, {}),
};

export const writes = {
  createExam: (body: unknown) => post<ExamDetailDto>("/exams", body),
  scheduleExam: (examId: string) => post<ExamDetailDto>(`/exams/${examId}/schedule`, {}),
  startExam: (examId: string, idempotencyKey: string) =>
    post<ExamWindowDto>(`/exams/${examId}/start`, { idempotencyKey }),
  endExam: (examId: string) => post<ExamWindowDto>(`/exams/${examId}/end`, {}),
  cancelExam: (examId: string, reason: string) => post(`/exams/${examId}/cancel`, { reason }),
  publishResults: (examId: string, published: boolean) =>
    post<ResultsPageDto>(`/exams/${examId}/results/publish`, { published }),
};

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
  storeUser({ id: tokens.user.id, role: tokens.user.role, fullName: tokens.user.fullName });
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

  // A candidate is not a smaller administrator: they get their own paper and
  // nothing else. Branching here is what keeps the faculty exam — the one
  // carrying answer keys — off a candidate's machine entirely.
  if (readUser()?.role === "STUDENT") return loadCandidateState();

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

/**
 * The candidate's world: their assessments, their session, their answers.
 *
 * Assembled into the same ExamState shape the student screens already read, so
 * those screens did not have to change. Nothing here touches an endpoint that
 * can express an answer key.
 */
async function loadCandidateState(): Promise<Partial<ExamState>> {
  const user = readUser();
  const exams = await request<ExamSummaryDto[]>("/me/exams");

  // The paper worth opening: the one that is running, else the next one up.
  const target = exams.find((exam) => exam.status === "LIVE") ?? exams[0];
  const student: Student = {
    id: user?.id ?? "me",
    registrationNo: "",
    name: user?.fullName ?? "Candidate",
    email: "",
    program: "",
    semester: 0,
    section: "",
    status: "active",
    seat: "",
  };

  if (!target) {
    return { ...emptyState(), students: [student] };
  }

  // Resolve the exam into the session this candidate actually sits. The ids
  // are different things, and only the server can say which session is theirs.
  const mySessions = await request<SessionRowDto[]>("/me/sessions");
  const sessionId = mySessions.find((row) => row.examId === target.id)?.id ?? null;
  if (!sessionId) return { ...emptyState(), students: [student] };

  // Check-in is idempotent and draws the paper on first call, so it is the
  // right way to fetch it whether or not this is the candidate's first visit.
  const paper = await candidateWrites.checkIn(sessionId).catch(() => null);
  if (!paper) return { ...emptyState(), students: [student] };

  const state = await request<SessionStateDto>(`/sessions/${paper.sessionId}/state`);
  const key = `${target.id}:${student.id}`;

  const test: Test = {
    ...toTest(target),
    instructions: paper.instructions ?? [],
    // StudentQuestionOut has no answer-key field, so nothing to strip.
    questions: (paper.questions ?? []).map((question) => ({
      id: question.id,
      type: question.type,
      prompt: question.prompt,
      marks: question.marks,
      options: (question.options ?? []).map((option) => option.body),
    })),
    config: {
      questionsPerStudent: paper.config?.questionsPerStudent ?? 0,
      randomizeQuestions: paper.config?.randomizeQuestions ?? false,
      randomizeOptions: paper.config?.randomizeOptions ?? false,
      allowNavigation: paper.config?.allowNavigation ?? true,
      autoSubmitOnExpiry: paper.config?.autoSubmitOnExpiry ?? true,
    },
    endsAt: paper.endsAt ?? undefined,
    assignedStudentIds: [student.id],
  };

  const terminal = paper.status === "SUBMITTED" || paper.status === "AUTO_SUBMITTED";

  return {
    ...emptyState(),
    tests: [test],
    students: [student],
    sessions: [{
      testId: target.id,
      studentId: student.id,
      computerId: paper.sessionId,
      connection: "online",
      examStatus: toSessionStatus(paper.status),
      warnings: 0,
      activity: [],
    }],
    answers: { [key]: (state.answers ?? {}) as Record<string, AnswerValue> },
    flags: { [key]: (state.flagged ?? []).map(String) },
    submissions: terminal
      ? [{
          id: paper.sessionId,
          testId: target.id,
          studentId: student.id,
          answers: (state.answers ?? {}) as Record<string, AnswerValue>,
          flagged: (state.flagged ?? []).map(String),
          submittedAt: new Date().toISOString(),
          mode: paper.status === "AUTO_SUBMITTED" ? "automatic" : "manual",
        }]
      : [],
  };
}

/** The shape every bootstrap fills in, so no caller sees a half-built state. */
function emptyState(): Partial<ExamState> {
  return {
    version: 2,
    tests: [],
    students: [],
    labs: [],
    computers: [],
    sessions: [],
    results: [],
    audits: [],
    submissions: [],
    answers: {},
    flags: {},
    toasts: [],
    mockResultMode: false,
  };
}

/** The session id for a candidate's current paper, needed by the writes. */
export function candidateSessionId(state: ExamState, examId: string, studentId: string): string | null {
  return state.sessions.find((s) => s.testId === examId && s.studentId === studentId)?.computerId ?? null;
}

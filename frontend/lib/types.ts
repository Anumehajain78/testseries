// "cancelled" is a distinct outcome, not a flavour of completed — an exam
// abandoned by an administrator must never read as one that ran to term.
export type ExamStatus = "draft" | "scheduled" | "live" | "completed" | "cancelled";
// "terminated" covers a candidate ejected by an invigilator. Collapsing it
// into "submitted" would misreport them as having sat the paper.
export type StudentExamStatus = "not-ready" | "ready" | "in-progress" | "submitted" | "terminated";
export type ConnectionStatus = "online" | "warning" | "offline";
export type QuestionType = "mcq" | "multiple" | "text" | "coding";
// One language for now. It is still named on every coding question rather than
// assumed, so the day a second runner exists no paper has to be re-authored to
// say which language it was always written in.
export type CodingLanguage = "python";
export type AuditSeverity = "info" | "warning" | "critical";
// Visual tone shared by the Badge component and the status maps in status.ts.
export type BadgeTone = "success" | "warning" | "danger" | "info" | "neutral" | "live";

// Normalized answer value stored per question, supporting all question types
export type AnswerValue =
  | { kind: "single"; option: number }
  | { kind: "multiple"; options: number[] }
  | { kind: "text"; text: string }
  | { kind: "code"; source: string };

/**
 * One test case behind a coding question.
 *
 * Faculty author the whole case; a candidate's paper carries only the cases
 * marked visible, and strips `expectedStdout` even from those. The expected
 * output is the answer key — it is to a coding question what `isCorrect` is to
 * a multiple-choice one, and a paper that shipped it would be a paper that
 * shipped its own marking scheme.
 *
 * Both shapes are this one type, with the withheld fields optional, so a
 * component cannot read a key that was never sent to the machine it is running
 * on: there is nothing to read.
 */
export interface CodingTestCase {
  position: number;
  stdin: string;
  /** Withheld from candidates. */
  expectedStdout?: string;
  /** Withheld from candidates: every case they receive is a visible one. */
  hidden?: boolean;
  weight?: number;
}

/** The authoring form, where every field is the faculty's to fill in.
 *
 *  No `position`: order is carried by the list itself, both in the builder and
 *  on the wire, and the server numbers the cases from it. A second copy of the
 *  same fact would disagree with the list the first time a case in the middle
 *  of it was removed. */
export interface AuthoredCodingTestCase {
  stdin: string;
  expectedStdout: string;
  hidden: boolean;
  weight: number;
}

export interface Question {
  id: string;
  type: QuestionType;
  prompt: string;
  options: string[];
  correctOption?: number;
  correctOptions?: number[];
  marks: number;
  /** Coding questions only. */
  language?: CodingLanguage;
  /** Pre-filled in the candidate's editor. Null when the paper offers none. */
  starterCode?: string | null;
  tests?: CodingTestCase[];
}

export interface ExamConfig {
  questionsPerStudent: number;
  randomizeQuestions: boolean;
  randomizeOptions: boolean;
  allowNavigation: boolean;
  autoSubmitOnExpiry: boolean;
}

export interface Test {
  id: string;
  title: string;
  code: string;
  course: string;
  department: string;
  description?: string;
  durationMinutes: number;
  totalMarks: number;
  scheduledAt: string;
  status: ExamStatus;
  labId: string;
  assignedStudentIds: string[];
  instructions: string[];
  questions: Question[];
  config: ExamConfig;
  endsAt?: string;
  /** When the exam cell released this assessment's scores. Null while
   *  withheld. Publication is per assessment: releasing one must not release
   *  another that is still being marked. */
  resultsPublishedAt?: string | null;
}

export interface Student {
  id: string;
  registrationNo: string;
  name: string;
  email: string;
  program: string;
  semester: number;
  section: string;
  status: "active" | "blocked";
  seat: string;
}

export interface Lab {
  id: string;
  name: string;
  building: string;
  capacity: number;
  available: number;
  invigilator: string;
  status: "ready" | "occupied" | "maintenance";
}

export interface Computer {
  id: string;
  labId: string;
  index: number;
  assignedStudentId?: string;
  connection: ConnectionStatus;
  /** Null until the workstation has been enrolled from the lab client. A
   *  machine that was never enrolled cannot sit a candidate. */
  enrolledAt?: string | null;
  /** Last heartbeat the server received. Null means it has never reported —
   *  which is a different problem from having gone quiet. */
  lastSeenAt?: string | null;
}

export interface ActivityEntry {
  at: string;
  label: string;
  severity: AuditSeverity;
}

export interface ExamSession {
  testId: string;
  studentId: string;
  computerId: string;
  connection: ConnectionStatus;
  examStatus: StudentExamStatus;
  loginAt?: string;
  examStartedAt?: string;
  lastHeartbeatAt?: string;
  warnings: number;
  activity: ActivityEntry[];
}

export interface Result {
  id: string;
  testId: string;
  studentId: string;
  /** Null while the assessment's results are withheld. A withheld score is
   *  not a zero, and rendering it as one would tell a candidate they failed. */
  score: number | null;
  total: number;
  /** Answers on this paper that nothing has scored yet — a written one waiting
   *  for a marker, or a program waiting for the code runner. While this is
   *  above zero the score is a running total, not a result, and a screen that
   *  presents it as final is telling a candidate they lost marks that nobody
   *  has decided. Absent on a row the server predates; zero is its own default. */
  pendingMarking?: number;
  submittedAt: string;
  mode: "manual" | "automatic";
}

export interface AuditEvent {
  id: string;
  at: string;
  actor: string;
  action: string;
  detail: string;
  studentId?: string;
  computerId?: string;
  category: "connection" | "exam" | "system";
  severity: AuditSeverity;
}

export interface Submission {
  id: string;
  testId: string;
  studentId: string;
  answers: Record<string, AnswerValue>;
  flagged: string[];
  submittedAt: string;
  mode: "manual" | "automatic";
}

export interface Toast {
  id: string;
  title: string;
  message: string;
  tone: "success" | "info" | "warning";
}

export interface ExamState {
  version: 2;
  tests: Test[];
  students: Student[];
  labs: Lab[];
  computers: Computer[];
  sessions: ExamSession[];
  results: Result[];
  audits: AuditEvent[];
  submissions: Submission[];
  answers: Record<string, Record<string, AnswerValue>>;
  flags: Record<string, string[]>;
  toasts: Toast[];
  /** Whether the exam cell has released scores to candidates. */
}

export interface NewTestInput {
  title: string;
  code: string;
  course: string;
  department: string;
  description?: string;
  durationMinutes: number;
  labId: string;
  scheduledAt?: string;
  assignedStudentIds?: string[];
  instructions?: string[];
  config?: Partial<ExamConfig>;
  questions: Array<{
    type: QuestionType;
    prompt: string;
    options: string[];
    /** Indices of the correct choices. Empty for a written or coding answer. */
    correctOptions: number[];
    marks: number;
    /** Coding questions only; omitted entirely for every other type. */
    language?: CodingLanguage;
    starterCode?: string | null;
    tests?: AuthoredCodingTestCase[];
  }>;
}

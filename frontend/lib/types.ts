export type ExamStatus = "draft" | "scheduled" | "live" | "completed";
export type StudentExamStatus = "not-ready" | "ready" | "in-progress" | "submitted";
export type ConnectionStatus = "online" | "warning" | "offline";
export type QuestionType = "mcq" | "multiple" | "text";
export type AuditSeverity = "info" | "warning" | "critical";
// Visual tone shared by the Badge component and the status maps in status.ts.
export type BadgeTone = "success" | "warning" | "danger" | "info" | "neutral" | "live";

// Normalized answer value stored per question, supporting all question types
export type AnswerValue =
  | { kind: "single"; option: number }
  | { kind: "multiple"; options: number[] }
  | { kind: "text"; text: string };

export interface Question {
  id: string;
  type: QuestionType;
  prompt: string;
  options: string[];
  correctOption?: number;
  correctOptions?: number[];
  marks: number;
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
  score: number;
  total: number;
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
  mockResultMode: boolean;
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
  questions: Array<Pick<Question, "prompt" | "options" | "correctOption" | "marks">>;
}

import type {
  AuditEvent,
  Computer,
  ConnectionStatus,
  ExamSession,
  Lab,
  Student,
} from "./types";

// ---------------------------------------------------------------------------
// Monitor rows — join sessions + computers + students into a single view model
// ---------------------------------------------------------------------------

export interface MonitorRow {
  session: ExamSession;
  student: Student | undefined;
  computer: Computer | undefined;
  studentName: string;
  registrationNo: string;
  computerId: string;
  connection: ConnectionStatus;
}

export type MonitorFilter = "all" | "active" | "warning" | "offline" | "submitted";

// Build the joined monitor rows for a single test, ordered by computer index.
export function buildMonitorRows(
  testId: string,
  sessions: ExamSession[],
  computers: Computer[],
  students: Student[],
): MonitorRow[] {
  const studentById = new Map(students.map((s) => [s.id, s]));
  const computerById = new Map(computers.map((c) => [c.id, c]));
  return sessions
    .filter((session) => session.testId === testId)
    .map((session) => {
      const student = studentById.get(session.studentId);
      const computer = computerById.get(session.computerId);
      return {
        session,
        student,
        computer,
        studentName: student?.name ?? "Unassigned candidate",
        registrationNo: student?.registrationNo ?? "—",
        computerId: session.computerId,
        connection: session.connection,
      };
    })
    .sort((a, b) => (a.computer?.index ?? 0) - (b.computer?.index ?? 0));
}

// Apply a monitor filter to already-joined rows (Req 6.5).
export function filterMonitorRows(rows: MonitorRow[], filter: MonitorFilter): MonitorRow[] {
  switch (filter) {
    case "active":
      return rows.filter((row) => row.session.examStatus === "in-progress");
    case "warning":
      return rows.filter((row) => row.connection === "warning");
    case "offline":
      return rows.filter((row) => row.connection === "offline");
    case "submitted":
      return rows.filter((row) => row.session.examStatus === "submitted");
    case "all":
    default:
      return rows;
  }
}

// Aggregate monitoring statistics for a set of rows (Req 6.2).
export interface MonitorStatsSummary {
  assigned: number;
  online: number;
  submitted: number;
  active: number;
  warnings: number;
  disconnected: number;
}

export function summarizeMonitorRows(rows: MonitorRow[]): MonitorStatsSummary {
  return rows.reduce<MonitorStatsSummary>(
    (acc, row) => {
      acc.assigned += 1;
      if (row.connection !== "offline") acc.online += 1;
      if (row.session.examStatus === "submitted") acc.submitted += 1;
      if (row.session.examStatus === "in-progress") acc.active += 1;
      if (row.connection === "warning") acc.warnings += 1;
      if (row.connection === "offline") acc.disconnected += 1;
      return acc;
    },
    { assigned: 0, online: 0, submitted: 0, active: 0, warnings: 0, disconnected: 0 },
  );
}

// ---------------------------------------------------------------------------
// Lab occupancy — computer counts per lab (Req 9.1)
// ---------------------------------------------------------------------------

export interface LabOccupancy {
  total: number;
  online: number;
  warning: number;
  offline: number;
  hasActiveExam: boolean;
}

export function computeLabOccupancy(labId: string, computers: Computer[]): LabOccupancy {
  const inLab = computers.filter((computer) => computer.labId === labId);
  const online = inLab.filter((computer) => computer.connection === "online").length;
  const warning = inLab.filter((computer) => computer.connection === "warning").length;
  const offline = inLab.filter((computer) => computer.connection === "offline").length;
  return { total: inLab.length, online, warning, offline, hasActiveExam: online > 0 };
}

export function labsWithOccupancy(labs: Lab[], computers: Computer[]): Array<{ lab: Lab; occupancy: LabOccupancy }> {
  return labs.map((lab) => ({ lab, occupancy: computeLabOccupancy(lab.id, computers) }));
}

// ---------------------------------------------------------------------------
// Audit filters (Req 11.4)
// ---------------------------------------------------------------------------

export type AuditFilter = "all" | "warnings" | "critical" | "connection" | "exam";

export function filterAuditEvents(events: AuditEvent[], filter: AuditFilter): AuditEvent[] {
  switch (filter) {
    case "warnings":
      return events.filter((event) => event.severity === "warning");
    case "critical":
      return events.filter((event) => event.severity === "critical");
    case "connection":
      return events.filter((event) => event.category === "connection");
    case "exam":
      return events.filter((event) => event.category === "exam");
    case "all":
    default:
      return events;
  }
}

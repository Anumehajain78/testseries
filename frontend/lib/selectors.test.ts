import { describe, expect, it } from "vitest";
import { filterAuditEvents, filterMonitorRows, type MonitorRow } from "./selectors";
import type { AuditEvent, ConnectionStatus, StudentExamStatus } from "./types";

function row(
  id: string,
  connection: ConnectionStatus,
  examStatus: StudentExamStatus,
): MonitorRow {
  return {
    session: {
      testId: "t1",
      studentId: id,
      computerId: `pc-${id}`,
      connection,
      examStatus,
      warnings: 0,
      activity: [],
    },
    student: undefined,
    computer: undefined,
    studentName: id,
    registrationNo: id,
    computerId: `pc-${id}`,
    connection,
  };
}

const rows: MonitorRow[] = [
  row("a", "online", "in-progress"),
  row("b", "warning", "in-progress"),
  row("c", "offline", "ready"),
  row("d", "online", "submitted"),
];

describe("filterMonitorRows (Req 6.5)", () => {
  it("returns every row for the all filter", () => {
    expect(filterMonitorRows(rows, "all")).toHaveLength(4);
  });

  it("returns only in-progress rows for active", () => {
    expect(filterMonitorRows(rows, "active").map((r) => r.studentName)).toEqual(["a", "b"]);
  });

  it("returns only warning-connection rows", () => {
    expect(filterMonitorRows(rows, "warning").map((r) => r.studentName)).toEqual(["b"]);
  });

  it("returns only offline rows", () => {
    expect(filterMonitorRows(rows, "offline").map((r) => r.studentName)).toEqual(["c"]);
  });

  it("returns only submitted rows", () => {
    expect(filterMonitorRows(rows, "submitted").map((r) => r.studentName)).toEqual(["d"]);
  });
});

function audit(id: string, category: AuditEvent["category"], severity: AuditEvent["severity"]): AuditEvent {
  return { id, at: "2026-08-18T10:00:00.000Z", actor: "system", action: "a", detail: "d", category, severity };
}

const audits: AuditEvent[] = [
  audit("1", "system", "info"),
  audit("2", "connection", "warning"),
  audit("3", "exam", "critical"),
  audit("4", "exam", "info"),
];

describe("filterAuditEvents (Req 11.4)", () => {
  it("returns every event for the all filter", () => {
    expect(filterAuditEvents(audits, "all")).toHaveLength(4);
  });

  it("returns only warning-severity events", () => {
    expect(filterAuditEvents(audits, "warnings").map((e) => e.id)).toEqual(["2"]);
  });

  it("returns only critical-severity events", () => {
    expect(filterAuditEvents(audits, "critical").map((e) => e.id)).toEqual(["3"]);
  });

  it("returns only connection-category events", () => {
    expect(filterAuditEvents(audits, "connection").map((e) => e.id)).toEqual(["2"]);
  });

  it("returns only exam-category events", () => {
    expect(filterAuditEvents(audits, "exam").map((e) => e.id)).toEqual(["3", "4"]);
  });
});

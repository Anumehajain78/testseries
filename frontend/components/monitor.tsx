"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useExam } from "@/app/providers";
import { formatDateTime, formatTime, initials, statusLabel, timeSince } from "@/lib/format";
import type { ActivityEntry, StudentExamStatus } from "@/lib/types";
import {
  buildMonitorRows,
  filterMonitorRows,
  summarizeMonitorRows,
  type MonitorFilter,
  type MonitorRow,
  type MonitorStatsSummary,
} from "@/lib/selectors";
import { EXAM_STATUS_LABEL, examStatusTone } from "@/lib/status";
import { Icon } from "./icons";
import { Badge, ButtonLink, Card, EmptyState, LoadingState, PageHeader, StatCard, StatusDot, TableShell } from "./ui";
import { ExamTimer } from "./exam";



// -----------------------------------------------------------------------------
// MonitorStats — online/assigned, submitted, active, warnings, disconnected (Req 6.2)
// -----------------------------------------------------------------------------
export function MonitorStats({ summary }: { summary: MonitorStatsSummary }) {
  return <div className="monitor-stats">
    <StatCard label="Students online" value={`${summary.online}/${summary.assigned}`} detail="Connected of assigned" icon="wifi" tone="teal"/>
    <StatCard label="Submitted" value={summary.submitted} detail="Responses secured" icon="check" tone="navy"/>
    <StatCard label="Active" value={summary.active} detail="Actively answering" icon="clock" tone="blue"/>
    <StatCard label="Warnings" value={summary.warnings} detail={summary.warnings ? "Require attention" : "All clear"} icon="alert" tone="amber"/>
    <StatCard label="Disconnected" value={summary.disconnected} detail="Offline workstations" icon="monitor" tone="amber"/>
  </div>;
}

const MONITOR_FILTERS: Array<{ id: MonitorFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "active", label: "Active" },
  { id: "warning", label: "Warning" },
  { id: "offline", label: "Offline" },
  { id: "submitted", label: "Submitted" },
];

// -----------------------------------------------------------------------------
// StudentMonitor — filterable live candidate table (Req 6.3, 6.4, 6.5, 6.7)
// -----------------------------------------------------------------------------
export function StudentMonitor({ rows, filter, onFilterChange, onSelect, nowMs }: {
  rows: MonitorRow[];
  filter: MonitorFilter;
  onFilterChange: (filter: MonitorFilter) => void;
  onSelect: (studentId: string) => void;
  nowMs: number;
}) {
  const visible = filterMonitorRows(rows, filter);
  return <Card className="table-card">
    <div className="section-heading">
      <div><p className="eyebrow">Candidate roster</p><h2>Live session activity</h2></div>
      <div className="tabs" role="group" aria-label="Filter candidates by status">
        {MONITOR_FILTERS.map((item) => <button key={item.id} className={filter === item.id ? "active" : ""} onClick={() => onFilterChange(item.id)}>{item.label} <span>{item.id === "all" ? rows.length : filterMonitorRows(rows, item.id).length}</span></button>)}
      </div>
    </div>
    {visible.length ? <TableShell caption="Live candidate status">
      <thead><tr><th>Computer</th><th>Candidate</th><th>Roll number</th><th>Connection</th><th>Exam status</th><th>Activity</th><th>Last heartbeat</th></tr></thead>
      <tbody>{visible.map((row) => <tr key={row.session.studentId} className="clickable-row" tabIndex={0} role="button" aria-label={`Open ${row.studentName} details`} onClick={() => onSelect(row.session.studentId)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(row.session.studentId); } }}>
        <td><strong>{row.computerId}</strong></td>
        <td><div className="person-cell"><span className="avatar small">{initials(row.studentName)}</span><strong>{row.studentName}</strong></div></td>
        <td>{row.registrationNo}</td>
        <td><StatusDot status={row.connection}/></td>
        <td><Badge tone={examStatusTone(row.session.examStatus)}>{EXAM_STATUS_LABEL[row.session.examStatus]}</Badge></td>
        <td><ActivityIndicator status={row.session.examStatus} connection={row.connection}/></td>
        <td>{timeSince(row.session.lastHeartbeatAt, nowMs)}</td>
      </tr>)}</tbody>
    </TableShell> : <EmptyState title="No candidates in this view" description="Choose another filter to see connected candidates."/>}
  </Card>;
}

// Small live activity indicator derived from exam + connection status (Req 6.3).
function ActivityIndicator({ status, connection }: { status: StudentExamStatus; connection: MonitorRow["connection"] }) {
  if (connection === "offline") return <span className="activity-indicator idle"><i/> No signal</span>;
  if (status === "submitted") return <span className="activity-indicator done"><i/> Completed</span>;
  if (status === "in-progress") return <span className="activity-indicator active"><i/> Answering</span>;
  return <span className="activity-indicator idle"><i/> Waiting</span>;
}

// -----------------------------------------------------------------------------
// ActivityTimeline — chronological session events with severity dots (Req 6.6)
// -----------------------------------------------------------------------------
export function ActivityTimeline({ events }: { events: ActivityEntry[] }) {
  if (!events.length) return <p className="timeline-empty">No activity recorded yet.</p>;
  return <ol className="activity-timeline">{events.map((event, index) => <li key={`${event.at}-${index}`}>
    <span className={`activity-dot ${event.severity}`}><Icon name={event.severity === "info" ? "check" : "alert"} size={12}/></span>
    <div><strong>{event.label}</strong><time dateTime={event.at}>{formatTime(event.at)}</time></div>
  </li>)}</ol>;
}

// -----------------------------------------------------------------------------
// StudentDetailPanel — side drawer with candidate + computer detail (Req 6.6)
// -----------------------------------------------------------------------------
export function StudentDetailPanel({ row, onClose, nowMs }: { row: MonitorRow | null; onClose: () => void; nowMs: number }) {
  if (!row) return null;
  const { session } = row;
  return <div className="detail-drawer-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}>
    <aside className="detail-drawer" role="dialog" aria-modal="true" aria-label={`${row.studentName} session details`}>
      <header className="drawer-head">
        <div className="person-cell"><span className="avatar">{initials(row.studentName)}</span><div><strong>{row.studentName}</strong><small>{row.registrationNo}</small></div></div>
        <button className="icon-button" aria-label="Close details" onClick={onClose}><Icon name="close"/></button>
      </header>
      <div className="drawer-status">
        <StatusDot status={row.connection}/>
        <Badge tone={examStatusTone(session.examStatus)}>{EXAM_STATUS_LABEL[session.examStatus]}</Badge>
      </div>
      <dl className="drawer-facts">
        <div><dt>Computer</dt><dd>{row.computerId}</dd></div>
        <div><dt>Warnings</dt><dd className={session.warnings ? "warn" : ""}>{session.warnings}</dd></div>
        <div><dt>Login time</dt><dd>{session.loginAt ? formatDateTime(session.loginAt) : "Not signed in"}</dd></div>
        <div><dt>Exam started</dt><dd>{session.examStartedAt ? formatDateTime(session.examStartedAt) : "Not started"}</dd></div>
        <div><dt>Last heartbeat</dt><dd>{session.lastHeartbeatAt ? `${formatTime(session.lastHeartbeatAt)} · ${timeSince(session.lastHeartbeatAt, nowMs)}` : "—"}</dd></div>
      </dl>
      <div className="drawer-section">
        <h3>Activity timeline</h3>
        <ActivityTimeline events={session.activity}/>
      </div>
    </aside>
  </div>;
}

// -----------------------------------------------------------------------------
// MonitorScreen — orchestrates the live monitoring dashboard (Req 6.1)
// -----------------------------------------------------------------------------
export function MonitorScreen() {
  const params = useParams<{ id: string }>();
  const { state, hydrated } = useExam();
  const [filter, setFilter] = useState<MonitorFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Display-only tick refreshes "time since last heartbeat" strings (Req 6.3, 6.6).
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => { const timer = window.setInterval(() => setNowMs(Date.now()), 1000); return () => clearInterval(timer); }, []);

  const test = state.tests.find((item) => item.id === params.id);
  const rows = useMemo(
    () => test ? buildMonitorRows(test.id, state.sessions, state.computers, state.students) : [],
    [test, state.sessions, state.computers, state.students],
  );
  const summary = useMemo(() => summarizeMonitorRows(rows), [rows]);

  if (!hydrated) return <LoadingState/>;
  if (!test) return <EmptyState title="Session not found" description="Return to assessments and choose another session." action={<ButtonLink href="/admin/tests">Back to assessments</ButtonLink>}/>;

  const lab = state.labs.find((item) => item.id === test.labId);
  const selectedRow = rows.find((row) => row.session.studentId === selectedId) ?? null;

  return <>
    <PageHeader
      eyebrow="Live operations"
      title={test.title}
      description={`${test.code} · ${lab?.name ?? "Unassigned lab"}`}
      actions={<>
        <Badge tone={test.status === "live" ? "live" : "neutral"}>{test.status === "live" ? "SESSION LIVE" : statusLabel(test.status)}</Badge>
        {test.status === "live" && <ExamTimer endsAt={test.endsAt} onExpire={() => {}}/>}
        <ButtonLink href={`/admin/tests/${test.id}`} tone="secondary">Exam details</ButtonLink>
      </>}
    />
    <MonitorStats summary={summary}/>
    <div className="monitor-callout">
      <span className="pulse-ring small"><Icon name="monitor"/></span>
      <div><strong>Live monitoring active</strong><p>Candidate status updates automatically from the synchronized session.</p></div>
      <span>Last sync: {timeSince(new Date(nowMs).toISOString(), nowMs)}</span>
    </div>
    <StudentMonitor rows={rows} filter={filter} onFilterChange={setFilter} onSelect={setSelectedId} nowMs={nowMs}/>
    <StudentDetailPanel row={selectedRow} onClose={() => setSelectedId(null)} nowMs={nowMs}/>
  </>;
}

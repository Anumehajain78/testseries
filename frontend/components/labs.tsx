"use client";

import { useMemo, useState } from "react";
import { useExam } from "@/app/providers";
import { initials } from "@/lib/format";
import { computeLabOccupancy, type LabOccupancy } from "@/lib/selectors";
import type { Computer, ConnectionStatus, ExamSession, Lab, Student, StudentExamStatus } from "@/lib/types";
import { EXAM_STATUS_LABEL, examStatusTone } from "@/lib/status";
import { Icon } from "./icons";
import { Badge, Button, Card, EmptyState, LoadingState, PageHeader, Progress, StatusDot } from "./ui";

// Per-computer view model joining the workstation with its seated candidate and
// live session so the grid can render machine ID, student, connection, and exam
// status in one place (Req 9.3).
interface ComputerView {
  computer: Computer;
  studentName: string;
  registrationNo: string;
  connection: ConnectionStatus;
  examStatus: StudentExamStatus;
}



// Join every computer in a lab with its assigned student and live session,
// ordered by workstation index for a stable, readable grid (Req 9.3).
function buildComputerViews(labId: string, computers: Computer[], sessions: ExamSession[], students: Student[]): ComputerView[] {
  const studentById = new Map(students.map((s) => [s.id, s]));
  return computers
    .filter((computer) => computer.labId === labId)
    .slice()
    .sort((a, b) => a.index - b.index)
    .map((computer) => {
      const student = computer.assignedStudentId ? studentById.get(computer.assignedStudentId) : undefined;
      const session = sessions.find((item) => item.computerId === computer.id);
      return {
        computer,
        studentName: student?.name ?? "Unassigned",
        registrationNo: student?.registrationNo ?? "—",
        connection: computer.connection,
        examStatus: session?.examStatus ?? "not-ready",
      };
    });
}

// -----------------------------------------------------------------------------
// LabCard — venue summary with online-of-total occupancy (Req 9.1, 19.1)
// -----------------------------------------------------------------------------
export function LabCard({ lab, occupancy, active, onOpen }: { lab: Lab; occupancy: LabOccupancy; active: boolean; onOpen: () => void }) {
  const status = occupancy.online === 0 ? "offline" : occupancy.warning > 0 ? "warning" : "online";
  const percent = occupancy.total ? Math.round(occupancy.online / occupancy.total * 100) : 0;
  return <Card className={`lab-card ${active ? "lab-card-active" : ""}`}>
    <div className="lab-top"><span className={`lab-icon ${lab.status}`}><Icon name="monitor"/></span><StatusDot status={status}/></div>
    <h2>{lab.name}</h2>
    <p><Icon name="building" size={16}/>{lab.building}</p>
    <div className="capacity-row"><span><strong>{occupancy.online}</strong> online</span><span>{occupancy.total} workstations</span></div>
    <Progress value={percent}/>
    <p className="lab-exam-note">{occupancy.hasActiveExam ? <><Icon name="wifi" size={14}/> Active exam in progress</> : <><Icon name="clock" size={14}/> No active exam</>}</p>
    <Button tone={active ? "primary" : "secondary"} onClick={onOpen} aria-pressed={active}>{active ? "Viewing workstations" : "View workstations"}</Button>
  </Card>;
}

// -----------------------------------------------------------------------------
// ComputerGrid — workstation tiles with machine ID, student, connection, status
// (Req 9.3, 9.4)
// -----------------------------------------------------------------------------
export function ComputerGrid({ computers }: { computers: ComputerView[] }) {
  if (!computers.length) return <EmptyState icon="monitor" title="No workstations mapped" description="This laboratory has no registered workstations in the demo data."/>;
  return <div className="computer-grid">{computers.map(({ computer, studentName, registrationNo, connection, examStatus }) => <article key={computer.id} className={`computer-tile connection-${connection}`}>
    <header><span className="computer-id"><Icon name="monitor" size={15}/>{computer.id}</span><StatusDot status={connection} showLabel={false}/></header>
    <div className="computer-person">{computer.assignedStudentId ? <><span className="avatar small">{initials(studentName)}</span><div><strong>{studentName}</strong><small>{registrationNo}</small></div></> : <span className="computer-empty">Unassigned workstation</span>}</div>
    <footer>{computer.assignedStudentId ? <Badge tone={examStatusTone(examStatus)}>{EXAM_STATUS_LABEL[examStatus]}</Badge> : <Badge>Idle</Badge>}</footer>
  </article>)}</div>;
}

// -----------------------------------------------------------------------------
// LabsScreen — labs overview with drill-down into a lab's workstation grid
// (Req 9.1, 9.2, 9.5)
// -----------------------------------------------------------------------------
export function LabsScreen() {
  const { state, hydrated } = useExam();
  const [selectedLabId, setSelectedLabId] = useState<string | null>(null);

  const labs = useMemo(() => state.labs.map((lab) => ({ lab, occupancy: computeLabOccupancy(lab.id, state.computers) })), [state.labs, state.computers]);
  const selected = labs.find((item) => item.lab.id === selectedLabId) ?? null;
  const computerViews = useMemo(
    () => selected ? buildComputerViews(selected.lab.id, state.computers, state.sessions, state.students) : [],
    [selected, state.computers, state.sessions, state.students],
  );

  if (!hydrated) return <LoadingState/>;

  return <>
    <PageHeader eyebrow="Infrastructure" title="Labs & computers" description="Monitor examination venues and workstation readiness across campus." actions={<Button tone="secondary" icon="reset">Run health check</Button>}/>
    <div className="lab-grid">{labs.map(({ lab, occupancy }) => <LabCard key={lab.id} lab={lab} occupancy={occupancy} active={lab.id === selectedLabId} onOpen={() => setSelectedLabId((current) => current === lab.id ? null : lab.id)}/>)}</div>
    {selected && <Card className="table-card computer-panel">
      <div className="section-heading">
        <div><p className="eyebrow">{selected.lab.building}</p><h2>{selected.lab.name} workstations</h2></div>
        <div className="filter-group">
          <Badge tone={selected.occupancy.hasActiveExam ? "success" : "neutral"}>{selected.occupancy.hasActiveExam ? "Active exam" : "No active exam"}</Badge>
          <Badge tone="info">{selected.occupancy.online}/{selected.occupancy.total} online</Badge>
        </div>
      </div>
      <ComputerGrid computers={computerViews}/>
    </Card>}
  </>;
}

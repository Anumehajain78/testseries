"""Seat allocation.

The Python counterpart of the frontend's ``lib/sessions.ts``. The *behaviour*
ports directly — every enrolled candidate ends up with exactly one session,
existing sessions are never rebuilt, and a candidate with no workstation still
gets a session — but the mechanism deliberately differs.

The mock could ask a workstation which student it belonged to, because
``Computer.assignedStudentId`` was a permanent binding. That column does not
exist here: a lab hosts a different cohort every hour, so seating is a fact
about a candidate sitting a *particular exam*. This module therefore
**allocates** workstations rather than looking them up.

Everything is pure and takes plain values, so the allocation policy can be
tested exhaustively without a database and reasoned about without a session.
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Workstation:
    """A seatable machine in the exam's lab."""

    id: UUID
    machine_id: str
    position: int


@dataclass(frozen=True, slots=True)
class SeatAssignment:
    """One candidate placed at one workstation, or at none."""

    student_id: UUID
    computer_id: UUID | None
    machine_id: str | None

    @property
    def is_seated(self) -> bool:
        return self.computer_id is not None


def allocate_seats(
    enrolled: list[UUID],
    workstations: list[Workstation],
    occupied_computer_ids: set[UUID] | None = None,
    already_seated: set[UUID] | None = None,
) -> list[SeatAssignment]:
    """Place every unseated candidate at a free workstation.

    Allocation walks workstations in ``position`` order and candidates in
    enrolment order, so the same inputs always produce the same seating chart.
    That determinism is what lets an invigilator print a seating list before the
    exam and have it still be true afterwards.

    A candidate for whom no workstation remains is still assigned a seat-less
    session rather than being dropped: an unseatable candidate must show up on
    the roster as a problem to solve, not vanish from it.

    :param enrolled: candidate ids, in enrolment order.
    :param workstations: machines in the exam's lab.
    :param occupied_computer_ids: machines already taken in this exam.
    :param already_seated: candidates who already have a session.
    """
    occupied = set(occupied_computer_ids or ())
    seated = set(already_seated or ())

    free = [ws for ws in sorted(workstations, key=lambda w: w.position) if ws.id not in occupied]
    queue = iter(free)

    assignments: list[SeatAssignment] = []
    for student_id in enrolled:
        if student_id in seated:
            continue
        workstation = next(queue, None)
        assignments.append(
            SeatAssignment(
                student_id=student_id,
                computer_id=workstation.id if workstation else None,
                machine_id=workstation.machine_id if workstation else None,
            )
        )
    return assignments


def unseated(assignments: list[SeatAssignment]) -> list[SeatAssignment]:
    """Candidates who could not be placed. Surfaced to faculty before start."""
    return [assignment for assignment in assignments if not assignment.is_seated]


def capacity_shortfall(enrolled_count: int, workstation_count: int) -> int:
    """How many candidates exceed the available machines.

    The frontend performs this check too, but only as UX — a candidate can edit
    the client, so this is the version that decides whether an exam may be
    scheduled.
    """
    return max(0, enrolled_count - workstation_count)

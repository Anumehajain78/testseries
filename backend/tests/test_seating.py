"""Seating parity tests.

These mirror the eleven tests guarding ``lib/sessions.ts`` in the frontend. Where
the mock's semantics still apply they assert the same behaviour; where the
backend deliberately differs — allocation instead of permanent binding — the
test says so explicitly rather than quietly diverging.
"""

import uuid

from app.domain.seating import (
    SeatAssignment,
    Workstation,
    allocate_seats,
    capacity_shortfall,
    unseated,
)


def student(n: int) -> uuid.UUID:
    return uuid.UUID(int=n, version=4)


def lab(count: int, start: int = 1) -> list[Workstation]:
    return [
        Workstation(id=uuid.UUID(int=1000 + i, version=4), machine_id=f"LAB1-PC-{i:02d}", position=i)
        for i in range(start, start + count)
    ]


class TestEveryCandidateIsSeated:
    def test_all_enrolled_candidates_receive_an_assignment(self):
        enrolled = [student(1), student(2), student(3)]
        assignments = allocate_seats(enrolled, lab(3))
        assert [a.student_id for a in assignments] == enrolled
        assert all(a.is_seated for a in assignments)

    def test_an_empty_roster_produces_nothing(self):
        assert allocate_seats([], lab(10)) == []

    def test_each_workstation_is_used_at_most_once(self):
        assignments = allocate_seats([student(i) for i in range(1, 6)], lab(5))
        machines = [a.computer_id for a in assignments]
        assert len(machines) == len(set(machines))


class TestIdempotence:
    """The mock's guarantee that a repeat schedule never rebuilds a session."""

    def test_candidates_who_already_have_a_session_are_skipped(self):
        enrolled = [student(1), student(2), student(3)]
        assignments = allocate_seats(enrolled, lab(3), already_seated={student(1)})
        assert [a.student_id for a in assignments] == [student(2), student(3)]

    def test_re_running_with_everyone_seated_is_a_no_op(self):
        enrolled = [student(1), student(2)]
        assert allocate_seats(enrolled, lab(2), already_seated=set(enrolled)) == []

    def test_occupied_workstations_are_not_reissued(self):
        machines = lab(3)
        assignments = allocate_seats(
            [student(2)], machines, occupied_computer_ids={machines[0].id}
        )
        assert assignments[0].computer_id == machines[1].id


class TestDeterminism:
    """A seating chart printed before the exam must still be true after it."""

    def test_allocation_follows_workstation_position_order(self):
        shuffled = list(reversed(lab(4)))
        assignments = allocate_seats([student(1), student(2)], shuffled)
        assert [a.machine_id for a in assignments] == ["LAB1-PC-01", "LAB1-PC-02"]

    def test_the_same_inputs_always_produce_the_same_chart(self):
        enrolled = [student(i) for i in range(1, 8)]
        machines = lab(7)
        first = allocate_seats(enrolled, machines)
        second = allocate_seats(enrolled, machines)
        assert first == second


class TestOversubscription:
    """An unseatable candidate is a problem to surface, not a row to drop."""

    def test_candidates_beyond_capacity_still_get_a_session(self):
        assignments = allocate_seats([student(1), student(2), student(3)], lab(2))
        assert len(assignments) == 3
        assert assignments[-1].computer_id is None

    def test_unseated_reports_exactly_the_unplaced_candidates(self):
        assignments = allocate_seats([student(1), student(2), student(3)], lab(1))
        assert [a.student_id for a in unseated(assignments)] == [student(2), student(3)]

    def test_a_lab_with_no_workstations_seats_nobody_but_loses_nobody(self):
        assignments = allocate_seats([student(1), student(2)], [])
        assert len(assignments) == 2
        assert not any(a.is_seated for a in assignments)

    def test_shortfall_counts_the_overflow(self):
        assert capacity_shortfall(58, 40) == 18

    def test_shortfall_is_zero_when_the_lab_is_large_enough(self):
        assert capacity_shortfall(20, 40) == 0


class TestAssignmentValue:
    def test_a_seated_assignment_carries_its_machine_label(self):
        assignment = allocate_seats([student(1)], lab(1))[0]
        assert assignment.machine_id == "LAB1-PC-01"
        assert assignment.is_seated

    def test_a_seatless_assignment_carries_neither_id_nor_label(self):
        assignment = allocate_seats([student(1)], [])[0]
        assert assignment == SeatAssignment(student_id=student(1), computer_id=None, machine_id=None)
        assert not assignment.is_seated

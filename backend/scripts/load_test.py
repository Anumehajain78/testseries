"""What happens when a real cohort sits down at once.

The claim this platform makes is sixty candidates in one lab and two hundred
across a campus. Nothing had ever tested it. A room full of students pressing
Start within the same second is not the same workload as one developer
clicking through screens, and the difference shows up as a submission that
does not land — which in an examination is not a slow page, it is a candidate
with no paper.

So this drives the API exactly as candidates do: sign in, check in, read the
paper, answer it, submit. No shortcuts into the database, because the point is
to exercise the path a workstation actually takes, including the token, the
write guards and the grading that happens on submission.

It creates candidates and an exam, and the API has no way to delete either —
an examination record that could be removed on request is not a record. So
point it at a database of its own rather than the one you develop against:

    createdb -h localhost -p 5435 -U exam exam_control_load
    EXAM_DATABASE_URL=postgresql+psycopg://exam:exam_local_dev@localhost:5435/exam_control_load \
      .venv/bin/python -m app.db.seed
    EXAM_DATABASE_URL=postgresql+psycopg://exam:exam_local_dev@localhost:5435/exam_control_load \
      .venv/bin/uvicorn app.main:app --port 8011 &

    .venv/bin/python -m scripts.load_test --api http://localhost:8011/api/v1 --candidates 60
    .venv/bin/python -m scripts.load_test --api http://localhost:8011/api/v1 --candidates 200

    dropdb -h localhost -p 5435 -U exam exam_control_load

Everything it creates is marked LOADTEST, so a run left behind with --keep can
be picked out of the register afterwards.
"""

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

API = "http://localhost:8010/api/v1"

#: Everything this script creates carries the marker, so a cleanup can find its
#: own rows and nothing else.
MARKER = "LOADTEST"


@dataclass
class Timings:
    """Latencies for one kind of request, in milliseconds."""

    name: str
    samples: list[float] = field(default_factory=list)
    failures: int = 0

    def record(self, ms: float) -> None:
        self.samples.append(ms)

    def fail(self) -> None:
        self.failures += 1

    def line(self) -> str:
        if not self.samples:
            return f"{self.name:<14} no successful calls ({self.failures} failed)"
        ordered = sorted(self.samples)
        return (
            f"{self.name:<14} n={len(ordered):<5} "
            f"p50={_pct(ordered, 50):>7.0f}ms  "
            f"p95={_pct(ordered, 95):>7.0f}ms  "
            f"p99={_pct(ordered, 99):>7.0f}ms  "
            f"max={ordered[-1]:>7.0f}ms  "
            f"failed={self.failures}"
        )


def _pct(ordered: list[float], p: int) -> float:
    if not ordered:
        return 0.0
    # Nearest-rank: with 60 samples p95 is the 57th, which is the number a
    # room of sixty actually contains rather than an interpolation of it.
    index = max(0, min(len(ordered) - 1, round(p / 100 * len(ordered) + 0.5) - 1))
    return ordered[index]


class Clock:
    """Times one request and files it under a name."""

    def __init__(self, timings: dict[str, Timings], name: str) -> None:
        self.timings = timings.setdefault(name, Timings(name))
        self.start = 0.0

    def __enter__(self) -> "Clock":
        self.start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        elapsed = (time.perf_counter() - self.start) * 1000
        if exc_type is None:
            self.timings.record(elapsed)
        else:
            self.timings.fail()
        return False


async def _json(response: httpx.Response) -> Any:
    if response.status_code >= 400:
        raise RuntimeError(f"{response.request.method} {response.request.url.path} → {response.status_code} {response.text[:200]}")
    return response.json()


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


async def sign_in(client: httpx.AsyncClient, email: str, password: str) -> str:
    body = await _json(await client.post("/auth/login", json={"email": email, "password": password}))
    return body["accessToken"]


async def create_cohort(
    client: httpx.AsyncClient, admin: dict, count: int, run: str, password_out: dict[str, str]
) -> list[str]:
    """Create the candidates, in one import rather than one request each.

    The addresses use the real institutional domain because ``.test`` is a
    reserved special-use domain and the validator refuses it — correctly. The
    registration numbers carry the marker instead.
    """
    rows = ["registration_no,full_name,email,program,semester,section"]
    for i in range(count):
        # Tagged with the run, so a second run does not collide with the
        # candidates the first one left behind — there is no delete, and a
        # harness that only works once is not a harness.
        rows.append(
            f"{MARKER}-{run}-{i:04d},Load Candidate {run} {i:04d},"
            f"loadtest.{run}.{i:04d}@northbridge.edu,B.Tech CSE,3,A"
        )
    summary = await _json(
        await client.post("/students/import", json={"csv": "\n".join(rows)}, headers=admin)
    )
    for row in summary.get("failed", []):
        print(f"  ! line {row['line']}: {row['reason']}", file=sys.stderr)
    created = summary.get("created", [])
    for row in created:
        password_out[row["student"]["email"]] = row["temporaryPassword"]
    return [row["student"]["id"] for row in created]


def provision_lab(seats: int, run: str) -> tuple[str, str]:
    """Make a lab big enough to seat the cohort.

    There is no endpoint for this — a lab is a room, and rooms are not created
    by an API call — so this one reaches into the database directly. It is the
    only place that does, and it is setup rather than measurement: every call
    the run actually times goes over the wire like a workstation's would.

    It is also why this needs a database of its own.
    """
    from uuid import uuid4

    from app.db.models import Computer, Lab
    from app.db.session import SessionLocal

    name = f"{MARKER} Hall {run}"
    with SessionLocal() as db:
        lab = Lab(id=uuid4(), name=name, building=f"{MARKER} Block", capacity=seats)
        db.add(lab)
        db.flush()
        for position in range(1, seats + 1):
            db.add(Computer(
                id=uuid4(),
                lab_id=lab.id,
                machine_id=f"{MARKER}-{run}-PC-{position:03d}",
                position=position,
                hostname=f"loadtest-{run}-{position:03d}",
            ))
        db.commit()
        return str(lab.id), name


async def build_exam(
    client: httpx.AsyncClient, admin: dict, student_ids: list[str], lab_id: str, questions: int, run: str
) -> str:
    paper = [
        {
            "type": "mcq",
            "prompt": f"Load question {n}",
            "marks": 1,
            "options": [
                {"body": "alpha", "isCorrect": n % 4 == 0},
                {"body": "beta", "isCorrect": n % 4 == 1},
                {"body": "gamma", "isCorrect": n % 4 == 2},
                {"body": "delta", "isCorrect": n % 4 == 3},
            ],
        }
        for n in range(questions)
    ]
    exam = await _json(await client.post("/exams", headers=admin, json={
        "code": f"{MARKER}-{run}",
        "title": f"{MARKER} cohort run {run}",
        "course": "Load Testing",
        "department": "Computer Science",
        "durationMinutes": 60,
        "scheduledAt": "2030-01-01T09:00:00Z",
        "labId": lab_id,
        "instructions": ["This examination exists only to measure the server."],
        "config": {
            "questionsPerStudent": 0,
            "randomizeQuestions": True,
            "randomizeOptions": True,
            "allowNavigation": True,
            "autoSubmitOnExpiry": True,
        },
        "questions": paper,
        "studentIds": student_ids,
    }))
    await _json(await client.post(f"/exams/{exam['id']}/schedule", headers=admin, json={}))
    await _json(await client.post(f"/exams/{exam['id']}/start", headers=admin,
                                  json={"idempotencyKey": f"load:{exam['id']}"}))
    return exam["id"]


# ---------------------------------------------------------------------------
# One candidate
# ---------------------------------------------------------------------------


async def candidate_run(
    base: str,
    email: str,
    password: str,
    exam_id: str,
    answers_per_paper: int,
    timings: dict[str, Timings],
    gate: asyncio.Event,
) -> bool:
    """Sign in, check in, answer, submit — the whole thing one person does."""
    async with httpx.AsyncClient(base_url=base, timeout=60.0) as client:
        try:
            # Everyone waits at the gate, then starts together. Staggering the
            # sign-ins would measure a queue that a real lab does not form.
            await gate.wait()

            with Clock(timings, "sign in"):
                token = await sign_in(client, email, password)
            auth = {"Authorization": f"Bearer {token}"}

            with Clock(timings, "my sessions"):
                sessions = await _json(await client.get("/me/sessions", headers=auth))
            mine = next((s for s in sessions if s["examId"] == exam_id), None)
            if mine is None:
                raise RuntimeError("no session for this exam")

            with Clock(timings, "check in"):
                paper = await _json(
                    await client.post(f"/sessions/{mine['id']}/checkin", headers=auth, json={})
                )

            questions = paper.get("questions", [])
            for n, question in enumerate(questions[:answers_per_paper]):
                with Clock(timings, "save answer"):
                    await _json(await client.put(
                        f"/sessions/{mine['id']}/answers/{question['id']}",
                        headers=auth,
                        json={"value": {"kind": "single", "option": n % 4}, "clientSeq": n + 1},
                    ))

            with Clock(timings, "submit"):
                await _json(
                    await client.post(f"/sessions/{mine['id']}/submit", headers=auth, json={})
                )
            return True
        except Exception as exc:  # noqa: BLE001 - every failure is a result
            # The type matters: a timeout and a refusal are different findings,
            # and httpx timeouts carry an empty message.
            print(f"  ! {email}: {type(exc).__name__}: {exc}".rstrip(": "), file=sys.stderr)
            return False


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


async def remove_run(client: httpx.AsyncClient, admin: dict, exam_id: str) -> None:
    """Take the exam back out. Candidates are blocked rather than deleted,
    because the API has no delete: an examination record that could be removed
    on request is not a record."""
    try:
        await client.post(f"/exams/{exam_id}/cancel", headers=admin, json={"reason": "load test finished"})
    except Exception:  # noqa: BLE001
        pass


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default=API)
    parser.add_argument("--candidates", type=int, default=60, help="how many sit at once")
    parser.add_argument("--questions", type=int, default=20, help="questions on the paper")
    parser.add_argument("--answers", type=int, default=20, help="how many each candidate answers")
    parser.add_argument("--email", default="admin@northbridge.edu")
    parser.add_argument("--password", default="examcontrol")
    parser.add_argument("--keep", action="store_true", help="leave the exam behind for inspection")
    args = parser.parse_args()

    timings: dict[str, Timings] = {}

    async with httpx.AsyncClient(base_url=args.api, timeout=120.0) as client:
        print(f"signing in as {args.email}")
        admin = {"Authorization": f"Bearer {await sign_in(client, args.email, args.password)}"}

        labs = await _json(await client.get("/labs", headers=admin))
        if not labs:
            print("no labs: seed the database first", file=sys.stderr)
            return 1

        run = f"{int(time.time()) % 100_000:05d}"

        # Capacity is enforced on the server and cannot be edited away, so the
        # room has to be real before the cohort can sit in it.
        roomy = [lab for lab in labs if lab.get("capacity", 0) >= args.candidates]
        if roomy:
            lab_id, lab_name = min(roomy, key=lambda item: item["capacity"])["id"], min(roomy, key=lambda item: item["capacity"])["name"]
        else:
            lab_id, lab_name = provision_lab(args.candidates, run)
            print(f"no seeded lab seats {args.candidates}; built {lab_name}")

        print(f"creating {args.candidates} candidates (run {run})")
        passwords: dict[str, str] = {}
        student_ids = await create_cohort(client, admin, args.candidates, run, passwords)
        if len(student_ids) < args.candidates:
            print(f"  only {len(student_ids)} could be created", file=sys.stderr)
        if not student_ids:
            return 1

        print(f"creating and starting the exam in {lab_name}")
        exam_id = await build_exam(client, admin, student_ids, lab_id, args.questions, run)

        print(f"releasing {len(student_ids)} candidates at once…")
        gate = asyncio.Event()
        runs = [
            asyncio.create_task(
                candidate_run(args.api, email, password, exam_id, args.answers, timings, gate)
            )
            for email, password in passwords.items()
        ]
        started = time.perf_counter()
        gate.set()
        results = await asyncio.gather(*runs)
        wall = time.perf_counter() - started

        completed = sum(1 for ok in results if ok)
        print()
        print(f"{completed} of {len(results)} candidates finished, in {wall:.1f}s wall clock")
        for name in ("sign in", "my sessions", "check in", "save answer", "submit"):
            if name in timings:
                print("  " + timings[name].line())

        if not args.keep:
            print("\ncleaning up")
            await remove_run(client, admin, exam_id)
        else:
            print(f"\nleft behind: exam {exam_id}")

        return 0 if completed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

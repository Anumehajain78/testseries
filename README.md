# Exam Control Platform

A server-authoritative examination system for physical college computer labs:
faculty schedule and start an exam, every seated candidate is released at the
same server-defined moment, and the session is monitored until submission.

## Running the stack

```bash
docker compose up -d                                   # Postgres :5433, Redis :6380

cd backend
python3 -m venv .venv
./.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
./.venv/bin/alembic upgrade head
./.venv/bin/python -m app.db.seed                      # 60 candidates, 3 labs, 4 exams
./.venv/bin/uvicorn app.main:app --reload --port 8000

cd ../frontend
npm install
cp .env.example .env.local                             # point it at the API
npm run dev
```

Sign in with any seeded address — `anita.rao@northbridge.edu` (faculty) or
`admin@northbridge.edu` — and the password `examcontrol`.

### If port 5433 is taken

Machines running several projects tend to collect Postgres instances. Move ours
and point the backend at the new port:

```bash
EXAM_DB_PORT=5435 docker compose up -d
export EXAM_DATABASE_URL=postgresql+psycopg://exam:exam_local_dev@localhost:5435/exam_control
```

### Making the lab look alive

Liveness is derived from `last_heartbeat_at`, so workstations go offline about
ninety seconds after anything stops reporting. Machines report for themselves,
using a credential they hold — so enrol a room once, then let it run:

```bash
cd backend
./.venv/bin/python -m scripts.lab_client enrol --lab "Advanced Computing Lab"
./.venv/bin/python -m scripts.lab_client room  --lab "Advanced Computing Lab"
```

That stands in for the desktop client and talks to the same endpoints it will,
so if enrolment or heartbeats break, this breaks too. Delete it when the real
client exists.

## What is done and what is left

See [STATUS.md](STATUS.md) — a plain checklist of every part of the project.

## Layout

| Path | What it is |
| --- | --- |
| `frontend/` | Next.js 16 app — faculty console and candidate exam experience |
| `backend/` | FastAPI + Postgres. See `backend/README.md` for the design decisions |
| `.kiro/specs/` | Original requirements and design notes |

## Where this is

The migration off the browser mock is complete. The server owns the schema, the
state machines, authentication, the exam lifecycle, the candidate's paper, and
grading; the frontend is a client of it and **does not run without it**. There
is no offline mode, because there is no longer a client-side copy of an
examination to fall back to.

What that bought, concretely: a candidate's browser cannot see an answer key,
the exam clock is the server's, a repeated Start cannot move a deadline, and
auto-submission happens whether or not a candidate's machine is still there.

Still ahead: the Tauri lab client (machine enrolment and real heartbeats), the
invigilation signals it will report, and sandboxed code execution — in that
order, and deliberately not before the exam state machine settled.

## Checks

```bash
cd backend  && ./.venv/bin/python -m pytest -q
cd frontend && npm run test && npx tsc --noEmit && npm run lint && npm run build
```

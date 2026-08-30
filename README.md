# Exam Control Platform

A server-authoritative examination system for physical college computer labs:
faculty schedule and start an exam, every seated candidate is released at the
same server-defined moment, and the session is monitored until submission.

## Running the stack

```bash
docker compose up -d                                   # Postgres on :5433

cd backend
python3 -m venv .venv
./.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
./.venv/bin/alembic upgrade head
./.venv/bin/python -m app.db.seed                      # 60 candidates, 3 labs, 4 exams
./.venv/bin/uvicorn app.main:app --reload --port 8000

cd ../frontend
npm install
cp .env.example .env.local                             # set NEXT_PUBLIC_API_MODE=live
npm run dev
```

Sign in with any seeded address — `anita.rao@northbridge.edu` (faculty) or
`admin@northbridge.edu` — and the password `examcontrol`.

### Why the lab looks dead after a minute

Liveness is derived from `last_heartbeat_at`, so seeded workstations correctly
go offline about ninety seconds after seeding: nothing is reporting yet. Until
the lab client exists, stand in for it:

```bash
cd backend && ./.venv/bin/python -m scripts.simulate_heartbeats --watch
```

## Layout

| Path | What it is |
| --- | --- |
| `frontend/` | Next.js 16 app — faculty console and candidate exam experience |
| `backend/` | FastAPI + Postgres. See `backend/README.md` for the design decisions |
| `.kiro/specs/` | Original requirements and design notes |

## Where this is

The frontend workflow is complete against a mock store. The backend owns the
schema, the state machines, authentication, and every admin **read**. Writes
still run against the browser mock, which is why `NEXT_PUBLIC_API_MODE` exists:
`live` reads from Postgres, `mock` runs entirely offline, and flipping it is
the rollback.

Still ahead: the write cutover, WebSocket monitoring, the Tauri lab client, and
sandboxed code execution — in that order, and deliberately not before the exam
state machine is settled.

## Checks

```bash
cd backend  && ./.venv/bin/python -m pytest -q
cd frontend && npm run test && npx tsc --noEmit && npm run lint && npm run build
```

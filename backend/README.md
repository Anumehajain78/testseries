# Exam Control API

The server-authoritative backend for the examination platform.

**Step 02** established the contract: Pydantic schemas whose OpenAPI document
generates the frontend's TypeScript client, so the two sides cannot drift.

**Step 03** added persistence — Postgres, Alembic migrations, password and
token handling, and the seating and liveness logic. The route handlers still
return static examples from `app/examples.py`; wiring them to the database is
step 04, and the shapes they return are already final.

## Running it

```bash
docker compose up -d                              # Postgres on host port 5433
python3 -m venv .venv
./.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
./.venv/bin/alembic upgrade head
./.venv/bin/uvicorn app.main:app --reload --port 8000
```

Interactive docs: <http://localhost:8000/api/v1/docs>

## Migrations

```bash
./.venv/bin/alembic revision --autogenerate -m "what changed"
./.venv/bin/alembic upgrade head
./.venv/bin/alembic downgrade base && ./.venv/bin/alembic upgrade head   # prove it reverses
```

Alembic reads the database URL from application settings, not `alembic.ini`, so
migrations and the API can never be pointed at different databases by accident.

**Always run the round trip before committing a migration.** Postgres keeps an
enum type after the last table using it is dropped, so a downgrade that only
drops tables leaves the types behind and the next upgrade fails with
"type already exists" — the initial migration drops them explicitly for exactly
this reason.

## Regenerating the contract

The OpenAPI document is committed so a contract change shows up as a reviewable
diff rather than a silent behaviour shift. After editing any schema:

```bash
./.venv/bin/python scripts/export_openapi.py   # backend/openapi.json
cd ../frontend && npm run gen:api              # lib/api/schema.gen.ts
```

The frontend's `tsc` run is what enforces the contract: if a schema changes in a
way the screens cannot absorb, the client build fails.

## Layout

| Path | Purpose |
| --- | --- |
| `app/schemas/` | Pydantic models — the contract itself |
| `app/domain/transitions.py` | Legal state transitions for exams and sessions |
| `app/api/` | Route signatures; bodies are placeholders until step 03 |
| `app/examples.py` | Static payloads. Deleted in step 03. |
| `app/db/` | SQLAlchemy models, engine, session lifecycle |
| `app/core/` | Settings, password hashing, token issuance |
| `app/api/deps.py` | Auth and role guards, expressed as dependencies |
| `migrations/` | Alembic revisions |
| `scripts/export_openapi.py` | Writes `openapi.json` |

## Design decisions worth knowing before changing anything

**Two question models, and only one can reach a candidate.** `QuestionOut`
carries `is_correct`; `StudentQuestionOut` has no such field at all. This is
structural rather than a serializer setting, because the frontend's current
mock ships answer keys to the browser — during a live exam `correctOption` is
readable from DevTools. A field that does not exist cannot be leaked by a future
refactor.

**`DISCONNECTED` is not a session state.** Lifecycle (`SessionStatus`) and
liveness (`ConnectionState`) are separate axes. Folding them together would
lose what a candidate was doing when their network dropped, which is exactly
what an invigilator needs to know. Liveness is derived from
`last_heartbeat_at`, never stored.

**Planned time and authoritative time are different columns.** `scheduled_at`
is the advertised slot and is mutable while `DRAFT`. `starts_at` / `ends_at`
are stamped once, when faculty press start, and are immutable after. Without
this split, "the exam began twelve minutes late" is unrepresentable.

**Randomization is materialized per session, not computed per request.** Order
is drawn once at check-in and persisted, or a reconnect would reshuffle the
paper and leave every saved answer pointing at the wrong question. This is also
what makes `questions_per_student` possible, and why questions live in a bank
rather than being owned by one exam.

**A workstation is not a user.** Lab clients authenticate with a machine
credential and carry `subject_type=machine`. Modelling them as user rows would
mean every query touching users has to remember to exclude machines.

**Client-side validation is not enforcement.** The lab-capacity check, the
navigation lock, and the score clamp all exist in the frontend as UX. Each one
is re-implemented here, because a candidate can edit the client.

## Constraints that carry weight

Several rules live in the schema rather than only in application code, because
a check constraint is the version that still holds when a migration, a fixture,
or a future endpoint forgets:

| Constraint | What it prevents |
| --- | --- |
| `ck_exams_live_exam_has_window` | A LIVE exam with no `starts_at`/`ends_at`. This is what makes "the server owns the clock" a database guarantee. |
| `ck_exams_window_moves_forward` | An exam that ends before it begins. |
| `uq_exam_sessions_exam_id_student_id` | Two sessions for one candidate — the storage-level basis of seating and submission idempotence. |
| `uq_exam_sessions_exam_computer` | Two candidates seated at one workstation in the same exam. |
| `ck_results_score_within_max` | The 63/60 the mock once rendered as 105%. |

## Not in scope yet

Route handlers do not read the database yet — they return examples, and the
services that will replace them arrive in step 04. There is no WebSocket
server, no code execution, and no Tauri lab client. The realtime *frames* are
modelled and exported so the frontend can generate their types, but nothing
serves them.

`app/examples.py` is deleted when the handlers become real.

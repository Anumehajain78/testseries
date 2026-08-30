# Exam Control API

Phase 2 of the migration: the system contract expressed as executable schemas.

**There is no database yet, and that is deliberate.** Every handler returns a
static example from `app/examples.py`. What is real and final here are the
request and response *shapes*, the status codes, and the operation ids — those
generate the frontend's TypeScript client, so the two sides cannot drift.

## Running it

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/uvicorn app.main:app --reload --port 8000
```

Interactive docs: <http://localhost:8000/api/v1/docs>

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

## Not in scope yet

No database, no authentication logic behind the token shapes, no WebSocket
server, no code execution, no Tauri lab client. The realtime *frames* are
modelled and exported so the frontend can generate their types, but nothing
serves them.

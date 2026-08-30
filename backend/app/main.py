"""FastAPI application.

Step 02 of the migration: the contract stood up as executable schemas with no
database behind it. The OpenAPI document this produces is the single source of
truth for the frontend's generated types, so drift between client and server
becomes impossible rather than merely discouraged.
"""

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_directory import audit_router, auth_router, directory_router
from app.core.config import get_settings
from app.api.routes_exams import router as exams_router
from app.api.routes_sessions import router as sessions_router
from app.schemas.realtime import (
    ClientFrame,
    ExamEndingFrame,
    ExamStartedFrame,
    FocusFrame,
    ForceSubmitFrame,
    HeartbeatFrame,
    ServerFrame,
    SessionStateFrame,
    WarningFrame,
)

API_PREFIX = "/api/v1"

app = FastAPI(
    title="Exam Control API",
    version="0.2.0",
    summary="Server-authoritative examination platform for physical computer labs.",
    description=(
        "Phase 2 contract. Handlers return static examples; the shapes, status "
        "codes and operation ids are final and generate the frontend client."
    ),
    openapi_url=f"{API_PREFIX}/openapi.json",
    docs_url=f"{API_PREFIX}/docs",
)

# The Next.js dev server is a separate origin. Read from settings rather than
# hardcoded, so deploying to the college LAN is an environment variable - and
# never a wildcard, because credentials are real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(exams_router, prefix=API_PREFIX)
app.include_router(sessions_router, prefix=API_PREFIX)
app.include_router(directory_router, prefix=API_PREFIX)
app.include_router(audit_router, prefix=API_PREFIX)


@app.get("/health", tags=["meta"], operation_id="health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# WebSocket frames in the schema document
#
# FastAPI only documents HTTP routes, but the frontend needs generated types for
# the realtime frames just as much as for the REST payloads. Injecting them into
# `components.schemas` means one generator run produces both, and a frame whose
# shape changes breaks the client build rather than a running exam.
# ---------------------------------------------------------------------------

REALTIME_MODELS = [
    ServerFrame,
    ExamStartedFrame,
    ExamEndingFrame,
    SessionStateFrame,
    WarningFrame,
    ForceSubmitFrame,
    ClientFrame,
    HeartbeatFrame,
    FocusFrame,
]


def custom_openapi() -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema

    from fastapi.openapi.utils import get_openapi

    schema = get_openapi(
        title=app.title,
        version=app.version,
        summary=app.summary,
        description=app.description,
        routes=app.routes,
    )
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    for model in REALTIME_MODELS:
        model_schema = model.model_json_schema(
            ref_template="#/components/schemas/{model}", mode="serialization"
        )
        # Nested models arrive under $defs; lift them alongside everything else
        # so the generated TypeScript has no dangling references.
        for name, definition in model_schema.pop("$defs", {}).items():
            components.setdefault(name, definition)
        components[model.__name__] = model_schema

    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi  # type: ignore[method-assign]

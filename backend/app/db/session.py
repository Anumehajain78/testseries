"""Engine and session lifecycle.

Synchronous SQLAlchemy on purpose. The heavy concurrency in this system is
websocket fan-out and heartbeats, which Redis absorbs; the request path is
short transactional work where async drivers buy complexity rather than
throughput.

That holds only because the endpoints are synchronous too, and so run in
FastAPI's threadpool. Declaring one ``async def`` while it does blocking work
puts that work on the event loop and stops every other request in the process
— which is exactly what a lab full of candidates signing in at once produced,
down to the health check timing out.

Three limits have to agree, and measurement is what showed they did not: the
threadpool decides how many requests a worker runs at once, the pool how many
can reach the database, and Postgres how many connections exist at all. With
more threads than connections, against Postgres's default ceiling of 100, the
losers waited the full pool timeout and then failed — 96 of 200 sign-ins, as a
500 rather than as a queue.

``pool_timeout`` is short for that reason: thirty seconds of waiting is not a
kinder failure than a fast one, it is the same failure with a candidate sitting
in front of it.

What none of this buys is parallelism. A request here is CPU-bound — ORM,
serialisation, a password hash on sign-in — so one process serves them one at a
time however many threads it is given; measured, eighty concurrent reads of a
single table took exactly eighty times one. Throughput comes from running
several workers, and the numbers above are per worker because of it.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    str(settings.database_url),
    echo=settings.database_echo,
    pool_pre_ping=True,  # a lab session must survive an idle connection being reaped
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    #: Fail fast. A request queueing here is already a request that will miss.
    pool_timeout=10,
)

#: How many requests one worker runs at once. See ``Settings`` for why it sits
#: below the pool maximum rather than level with it.
MAX_CONCURRENT_REQUESTS = settings.max_concurrent_requests

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed.

    Commits are explicit in the service layer, so a handler that raises can
    never leave a half-applied transition behind.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

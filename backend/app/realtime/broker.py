"""Event fan-out.

With several Uvicorn workers behind Nginx, a faculty socket and the request
that changes an exam land in different processes. Something has to carry the
event across that boundary, and that something is Redis pub/sub.

Redis is deliberately *only* a transport here. Every durable fact lives in
Postgres, so losing Redis costs live updates — the monitor falls back to
polling and keeps working — but never an exam, a submission or a grade. That
is why the in-process fallback below is an acceptable degradation rather than
a broken deployment: a single worker needs no cross-process hop at all.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

log = logging.getLogger(__name__)

CHANNEL_PREFIX = "exam-control"


def channel_for(exam_id: str) -> str:
    return f"{CHANNEL_PREFIX}:exam:{exam_id}"


class Broker:
    """Publish/subscribe across workers, with a local-only fallback."""

    def __init__(self, redis_url: str | None) -> None:
        self._redis_url = redis_url
        self._redis = None
        self._local: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._reader: asyncio.Task | None = None
        self._pubsub = None

    # -- lifecycle ---------------------------------------------------------

    async def connect(self) -> None:
        if not self._redis_url:
            log.info("realtime: no REDIS_URL, using in-process fan-out (single worker only)")
            return
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
            await self._redis.ping()
            self._pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
            await self._pubsub.psubscribe(f"{CHANNEL_PREFIX}:*")
            self._reader = asyncio.create_task(self._read_redis())
            log.info("realtime: connected to Redis for cross-worker fan-out")
        except Exception as exc:
            # A Redis outage must not take the API down with it. Live updates
            # degrade to this worker only; the monitor's polling path covers
            # the rest.
            log.warning("realtime: Redis unavailable (%s); falling back to in-process fan-out", exc)
            self._redis = None
            self._pubsub = None

    async def close(self) -> None:
        if self._reader:
            self._reader.cancel()
            with suppress(asyncio.CancelledError):
                await self._reader
        if self._pubsub is not None:
            with suppress(Exception):
                await self._pubsub.aclose()
        if self._redis is not None:
            with suppress(Exception):
                await self._redis.aclose()

    # -- publish / subscribe ----------------------------------------------

    async def publish(self, channel: str, frame: dict[str, Any]) -> None:
        if self._redis is not None:
            with suppress(Exception):
                await self._redis.publish(channel, json.dumps(frame, default=str))
                return
        # No Redis, or publishing failed: deliver to this worker's own sockets
        # so a single-process deployment still works.
        self._fan_out_locally(channel, frame)

    def _fan_out_locally(self, channel: str, frame: dict[str, Any]) -> None:
        for queue in list(self._local.get(channel, ())):
            # Drop rather than block: a slow consumer must not stall an exam
            # transition. A dropped frame shows up as a sequence gap, and the
            # client refetches.
            with suppress(asyncio.QueueFull):
                queue.put_nowait(frame)

    async def _read_redis(self) -> None:
        assert self._pubsub is not None
        try:
            async for message in self._pubsub.listen():
                if message.get("type") not in ("message", "pmessage"):
                    continue
                try:
                    frame = json.loads(message["data"])
                except (TypeError, ValueError):
                    continue
                self._fan_out_locally(message["channel"], frame)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - defensive
            log.exception("realtime: redis reader stopped")

    async def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]:
        """Yield frames published to a channel until the caller stops."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        self._local.setdefault(channel, set()).add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            listeners = self._local.get(channel)
            if listeners:
                listeners.discard(queue)
                if not listeners:
                    self._local.pop(channel, None)


#: One broker per process, started and stopped with the application.
broker: Broker | None = None


def get_broker() -> Broker:
    if broker is None:
        raise RuntimeError("realtime broker is not started")
    return broker


def set_broker(instance: Broker | None) -> None:
    global broker
    broker = instance

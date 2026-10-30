"""Fans out newly stored readings, heard on PostgreSQL LISTEN/NOTIFY, to in-process subscribers.

Delivery is best-effort: a notification is lost while the listener connection is down and a
subscriber that cannot keep up loses its oldest messages. Clients backfill from the REST API.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, suppress
from typing import Any, Protocol

import asyncpg  # type: ignore[import-untyped]  # asyncpg ships no type stubs
from sqlalchemy.engine import make_url

from fermon.fermentation.domain import Reading
from fermon.fermentation.infrastructure.realtime.payload import (
    READINGS_CHANNEL,
    InvalidPayloadError,
    decode_reading,
)
from fermon.shared.waiting import sleep_or_stop

logger = logging.getLogger(__name__)

INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0
DEFAULT_QUEUE_SIZE = 100
CONNECT_TIMEOUT_SECONDS = 10.0
HEALTH_INTERVAL_SECONDS = 30.0
HEALTH_TIMEOUT_SECONDS = 5.0
CLOSE_TIMEOUT_SECONDS = 5.0
STOP_GRACE_SECONDS = 1.0


class ReadingFeed(Protocol):
    """What the WebSocket route needs: a live, per-tank stream of stored readings."""

    def subscribe(self, tank_id: str) -> AbstractContextManager[asyncio.Queue[Reading]]:
        """Receive the tank's new readings on the queue until the context exits."""
        ...


def listen_dsn(database_url: str) -> str:
    """A plain ``postgresql://`` DSN for asyncpg from the SQLAlchemy URL."""
    return make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)


async def _connect(dsn: str) -> Any:
    return await asyncpg.connect(dsn, timeout=CONNECT_TIMEOUT_SECONDS)


class ReadingBroadcaster:
    def __init__(
        self,
        dsn: str,
        *,
        connect: Callable[[str], Awaitable[Any]] = _connect,
        wait: Callable[[asyncio.Event, float], Awaitable[None]] = sleep_or_stop,
        queue_size: int = DEFAULT_QUEUE_SIZE,
        health_interval: float = HEALTH_INTERVAL_SECONDS,
        health_timeout: float = HEALTH_TIMEOUT_SECONDS,
        close_timeout: float = CLOSE_TIMEOUT_SECONDS,
        stop_grace: float = STOP_GRACE_SECONDS,
    ) -> None:
        self._dsn = dsn
        self._connect = connect
        self._wait = wait
        self._queue_size = queue_size
        self._health_interval = health_interval
        self._health_timeout = health_timeout
        self._close_timeout = close_timeout
        self._stop_grace = stop_grace
        # Set while a LISTEN is in place (NOTIFY is not buffered for absent listeners).
        self.ready = asyncio.Event()
        self._subscribers: dict[str, set[asyncio.Queue[Reading]]] = {}
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Begin listening in the background; never blocks on (or fails because of) the database."""
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="reading-broadcaster")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            task, self._task = self._task, None
            # The task may be blocked in connect or a health check: give it a short grace
            # period to notice the stop event, then cancel it so shutdown stays prompt.
            await asyncio.wait({task}, timeout=self._stop_grace)
            if not task.done():
                task.cancel()
                await asyncio.wait({task})
            if not task.cancelled() and task.exception() is not None:
                # the loop logs its own failures; shutdown must stay clean
                logger.error("reading listener task ended with an error", exc_info=task.exception())

    @contextmanager
    def subscribe(self, tank_id: str) -> Iterator[asyncio.Queue[Reading]]:
        queue: asyncio.Queue[Reading] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.setdefault(tank_id, set()).add(queue)
        try:
            yield queue
        finally:
            queues = self._subscribers[tank_id]
            queues.discard(queue)
            if not queues:
                del self._subscribers[tank_id]

    def subscriber_count(self, tank_id: str) -> int:
        return len(self._subscribers.get(tank_id, ()))

    def _on_notify(self, _connection: object, _pid: int, _channel: str, payload: str) -> None:
        try:
            reading = decode_reading(payload)
        except InvalidPayloadError as exc:
            logger.warning("dropped malformed notification: %s", exc)
            return
        for queue in tuple(self._subscribers.get(reading.tank_id, ())):
            if queue.full():
                queue.get_nowait()
                logger.debug("slow subscriber: dropped oldest reading for %s", reading.tank_id)
            queue.put_nowait(reading)

    async def _run(self) -> None:
        backoff = INITIAL_BACKOFF_SECONDS
        while not self._stop.is_set():
            lost = asyncio.Event()
            connection: Any = None
            try:
                connection = await self._connect(self._dsn)
                connection.add_termination_listener(lambda _conn, lost=lost: lost.set())
                await connection.add_listener(READINGS_CHANNEL, self._on_notify)
                backoff = INITIAL_BACKOFF_SECONDS
                self.ready.set()
                logger.info("listening for readings on channel %s", READINGS_CHANNEL)
                await self._until_lost_or_stopped(connection, lost)
                if not self._stop.is_set():
                    logger.warning("reading listener connection lost, reconnecting")
            except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError, TimeoutError) as exc:
                logger.warning("reading listener unavailable (%s), retrying in %.0fs", exc, backoff)
            except Exception:
                # Never let the listener die silently: realtime would stop until a restart.
                logger.exception("reading listener failed unexpectedly, retrying in %.0fs", backoff)
            finally:
                self.ready.clear()
                if connection is not None:
                    await self._close(connection)
            if self._stop.is_set():
                return
            await self._wait(self._stop, backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

    async def _close(self, connection: Any) -> None:
        """Close gracefully, but never hang on a half-open socket: fall back to terminate."""
        try:
            await asyncio.wait_for(connection.close(), self._close_timeout)
        except Exception:  # includes the timeout; asyncpg's terminate() is non-graceful
            with suppress(Exception):
                connection.terminate()
        except asyncio.CancelledError:
            # stop() may cancel us mid-close (its grace is shorter than the close timeout):
            # still drop the socket, then let the cancellation propagate.
            with suppress(Exception):
                connection.terminate()
            raise

    async def _until_lost_or_stopped(self, connection: Any, lost: asyncio.Event) -> None:
        """Return when the connection drops, stop is requested or a health check fails.

        A half-open socket (e.g. a silently dropped NAT mapping) never fires the termination
        listener, so the connection is probed with ``SELECT 1`` every ``health_interval``.
        """
        tasks = {asyncio.ensure_future(lost.wait()), asyncio.ensure_future(self._stop.wait())}
        try:
            while True:
                done, _ = await asyncio.wait(
                    tasks, timeout=self._health_interval, return_when=asyncio.FIRST_COMPLETED
                )
                if done:
                    return
                try:
                    await asyncio.wait_for(connection.execute("SELECT 1"), self._health_timeout)
                except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError, TimeoutError):
                    logger.warning("reading listener health check failed, reconnecting")
                    return
        finally:
            for task in tasks:
                task.cancel()

import asyncio
import logging
from collections.abc import Callable
from contextlib import ExitStack

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from fermon.fermentation.domain import InvalidIdentifierError, TankNotFoundError
from fermon.fermentation.infrastructure.http.dependencies import (
    AlertFeedDep,
    GetTankDep,
    ReadingFeedDep,
)
from fermon.fermentation.infrastructure.http.schemas import AlertEventOut, AlertOut, ReadingOut

# Application close codes (4000-4999 are reserved for applications by RFC 6455).
CLOSE_FORBIDDEN_ORIGIN = 4403
CLOSE_TANK_NOT_FOUND = 4404
CLOSE_INTERNAL_ERROR = 1011  # RFC 6455 standard code: the server hit an unexpected condition

logger = logging.getLogger(__name__)

router = APIRouter()


def _origin_allowed(websocket: WebSocket) -> bool:
    """CORS does not cover WebSockets, so enforce the same allow-list on the Origin header.

    Non-browser clients send no Origin; they are not subject to the same-origin model and pass.
    """
    origin = websocket.headers.get("origin")
    if origin is None:
        return True
    allowed: list[str] = websocket.app.state.cors_origins
    return "*" in allowed or origin in allowed


@router.websocket("/ws/tanks/{tank_id}")
async def stream_tank_readings(
    websocket: WebSocket, tank_id: str, get_tank: GetTankDep, feed: ReadingFeedDep
) -> None:
    """Live stream of a tank's newly stored readings, one JSON text message per reading.

    Best-effort: readings stored while the client or the server-side listener was disconnected
    are not replayed (backfill through the REST API), and a client that cannot keep up loses its
    oldest messages. Closes with 4403 for a disallowed Origin, 4404 for an unknown tank and 1011
    when the tank lookup fails.
    """
    if not _origin_allowed(websocket):
        # Accept first: a close before the handshake completes (an HTTP 403) reaches browsers
        # as a bare 1006, so the 4403 code would never be observable.
        await websocket.accept()
        await websocket.close(code=CLOSE_FORBIDDEN_ORIGIN, reason="origin not allowed")
        return
    try:
        tank = (await get_tank.execute(tank_id)).tank
    except (TankNotFoundError, InvalidIdentifierError) as exc:
        # Accept first: a close before the handshake completes reaches browsers as a bare 1006.
        await websocket.accept()
        await websocket.close(code=CLOSE_TANK_NOT_FOUND, reason=str(exc))
        return
    except Exception:
        logger.exception("tank lookup failed for websocket %r", tank_id)
        await websocket.accept()
        await websocket.close(code=CLOSE_INTERNAL_ERROR, reason="internal error")
        return
    await websocket.accept()
    with feed.subscribe(tank.id) as queue:
        await _stream(websocket, queue, lambda r: ReadingOut.from_domain(r).model_dump_json())


@router.websocket("/ws/alerts")
async def stream_alerts(websocket: WebSocket, feed: AlertFeedDep) -> None:
    """Live stream of every alert change (all tanks): `{"type": "alert", "alert": AlertOut}`.

    One message per stored revision: opened, acknowledged and resolved. Best-effort like the
    readings stream: nothing is replayed (backfill through `GET /alerts`) and a client that cannot
    keep up loses its oldest messages. Closes with 4403 for a disallowed Origin and 1011 when the
    server cannot subscribe to the alert feed.
    """
    if not _origin_allowed(websocket):
        await websocket.accept()  # accept first so browsers can observe the close code
        await websocket.close(code=CLOSE_FORBIDDEN_ORIGIN, reason="origin not allowed")
        return
    with ExitStack() as stack:
        try:
            queue = stack.enter_context(feed.subscribe_alerts())
        except Exception:
            logger.exception("alert feed subscription failed for websocket")
            await websocket.accept()
            await websocket.close(code=CLOSE_INTERNAL_ERROR, reason="internal error")
            return
        await websocket.accept()
        await _stream(
            websocket,
            queue,
            lambda alert: AlertEventOut(alert=AlertOut.from_domain(alert)).model_dump_json(),
        )


async def _stream[T](
    websocket: WebSocket, queue: asyncio.Queue[T], render: Callable[[T], str]
) -> None:
    """Send each queued item as a text message until the client disconnects."""
    receive = asyncio.ensure_future(websocket.receive())
    try:
        while True:
            item = asyncio.ensure_future(queue.get())
            try:
                await asyncio.wait({item, receive}, return_when=asyncio.FIRST_COMPLETED)
                if receive.done():
                    if receive.result()["type"] == "websocket.disconnect":
                        return
                    receive = asyncio.ensure_future(websocket.receive())  # ignore chatter
                if item.done():
                    await websocket.send_text(render(item.result()))
            finally:
                item.cancel()
    except WebSocketDisconnect:
        return
    finally:
        receive.cancel()

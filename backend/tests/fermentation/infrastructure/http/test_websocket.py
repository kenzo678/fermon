import asyncio
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from starlette.testclient import TestClient

from fermon.fermentation.application import GetTank
from fermon.fermentation.domain import (
    Alert,
    AlertKind,
    AlertStatus,
    MeasurementType,
    Reading,
    Tank,
)
from fermon.fermentation.infrastructure.http.dependencies import (
    get_alert_feed,
    get_get_tank,
    get_reading_feed,
)
from fermon.main import create_app
from fermon.shared.config import Settings
from tests.fermentation.fakes import (
    InMemoryAlertRepository,
    InMemoryBatchRepository,
    InMemoryReadingRepository,
    InMemoryTankRepository,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
ALLOWED = "http://localhost:5173"
DISALLOWED = "http://evil.example"


def reading(tank: str, value: float, at: datetime = T0) -> Reading:
    return Reading(tank, "s1", MeasurementType.TEMPERATURE, value, "celsius", at)


class FakeFeed:
    """Hands every subscriber the readings queued in ``pending`` and counts live subscribers."""

    def __init__(self) -> None:
        self.pending: list[Reading] = []
        self.subscribed: list[str] = []
        self.active = 0
        self.entered = threading.Event()  # set server-side once a subscription is live

    @contextmanager
    def subscribe(self, tank_id: str) -> Iterator[asyncio.Queue[Reading]]:
        queue: asyncio.Queue[Reading] = asyncio.Queue()
        for item in self.pending:
            queue.put_nowait(item)
        self.subscribed.append(tank_id)
        self.active += 1
        self.entered.set()
        try:
            yield queue
        finally:
            self.active -= 1


def alert(n: int = 1, status: AlertStatus = AlertStatus.OPEN) -> Alert:
    return Alert(
        id=UUID(int=n),
        tank_id=f"tank-{n}",
        batch_id=UUID(int=1),
        kind=AlertKind.OUT_OF_RANGE,
        measurement=MeasurementType.TEMPERATURE,
        status=status,
        opened_at=T0,
        acknowledged_at=T0 if status is AlertStatus.ACKNOWLEDGED else None,
        details={"observed": 25.5},
        version=2 if status is AlertStatus.ACKNOWLEDGED else 1,
    )


class FakeAlertFeed:
    """Hands every subscriber the alerts queued in ``pending`` and counts live subscribers."""

    def __init__(self) -> None:
        self.pending: list[Alert] = []
        self.active = 0
        self.entered = threading.Event()

    @contextmanager
    def subscribe_alerts(self) -> Iterator[asyncio.Queue[Alert]]:
        queue: asyncio.Queue[Alert] = asyncio.Queue()
        for item in self.pending:
            queue.put_nowait(item)
        self.active += 1
        self.entered.set()
        try:
            yield queue
        finally:
            self.active -= 1


@pytest.fixture
def alert_feed() -> FakeAlertFeed:
    return FakeAlertFeed()


@pytest.fixture
def feed() -> FakeFeed:
    return FakeFeed()


@pytest.fixture
def client(feed: FakeFeed, alert_feed: FakeAlertFeed) -> TestClient:
    tanks, readings = InMemoryTankRepository(), InMemoryReadingRepository()
    tanks.tanks["tank-1"] = Tank(id="tank-1", display_name=None, first_seen_at=T0)
    app = create_app(Settings(cors_origins=[ALLOWED]))
    app.dependency_overrides[get_get_tank] = lambda: GetTank(
        tanks, readings, InMemoryBatchRepository(), InMemoryAlertRepository()
    )
    app.dependency_overrides[get_reading_feed] = lambda: feed
    app.dependency_overrides[get_alert_feed] = lambda: alert_feed
    return TestClient(app)


def test_unknown_tank_is_closed_with_4404_and_a_reason(client: TestClient, feed: FakeFeed) -> None:
    with client.websocket_connect("/ws/tanks/nope") as ws:
        message = ws.receive()

    assert message["type"] == "websocket.close"
    assert message["code"] == 4404
    assert "nope" in message["reason"]
    assert feed.subscribed == []


def test_blank_tank_id_is_closed_with_4404(client: TestClient) -> None:
    with client.websocket_connect("/ws/tanks/%20") as ws:
        message = ws.receive()

    assert message["code"] == 4404


def test_known_tank_receives_pushed_readings_in_the_api_shape(
    client: TestClient, feed: FakeFeed
) -> None:
    local = datetime(2026, 1, 1, 9, 0, tzinfo=timezone(timedelta(hours=-3)))
    feed.pending = [reading("tank-1", 18.5, local), reading("tank-1", 19.0)]

    with client.websocket_connect("/ws/tanks/tank-1") as ws:
        first, second = ws.receive_json(), ws.receive_json()

    assert first == {
        "tank_id": "tank-1",
        "sensor_id": "s1",
        "measurement": "temperature",
        "value": 18.5,
        "unit": "celsius",
        "recorded_at": "2026-01-01T12:00:00Z",
    }
    assert second["value"] == 19.0


def test_tank_id_is_normalized_before_subscribing(client: TestClient, feed: FakeFeed) -> None:
    with client.websocket_connect("/ws/tanks/%20tank-1%20"):
        pass

    assert feed.subscribed == ["tank-1"]


def test_disconnecting_unsubscribes(client: TestClient, feed: FakeFeed) -> None:
    with client.websocket_connect("/ws/tanks/tank-1") as ws:
        ws.send_text("ignored chatter")
        assert feed.entered.wait(timeout=5)
        assert feed.active == 1

    assert feed.active == 0


def test_disallowed_origin_is_closed_with_4403_after_accept_so_browsers_see_it(
    client: TestClient, feed: FakeFeed
) -> None:
    with client.websocket_connect("/ws/tanks/tank-1", headers={"origin": DISALLOWED}) as ws:
        message = ws.receive()

    assert message["type"] == "websocket.close"
    assert message["code"] == 4403
    assert message["reason"]
    assert feed.subscribed == []


def test_allowed_origin_and_originless_clients_are_accepted(
    client: TestClient, feed: FakeFeed
) -> None:
    feed.pending = [reading("tank-1", 18.5)]

    with client.websocket_connect("/ws/tanks/tank-1", headers={"origin": ALLOWED}) as ws:
        assert ws.receive_json()["value"] == 18.5
    with client.websocket_connect("/ws/tanks/tank-1") as ws:
        assert ws.receive_json()["value"] == 18.5


class FailingGetTank:
    async def execute(self, tank_id: str) -> object:
        raise ConnectionError("database unreachable")


def test_tank_lookup_infrastructure_failure_closes_with_1011_and_logs(
    client: TestClient, feed: FakeFeed, caplog: pytest.LogCaptureFixture
) -> None:
    client.app.dependency_overrides[get_get_tank] = lambda: FailingGetTank()  # type: ignore[attr-defined]

    with caplog.at_level(logging.ERROR):
        with client.websocket_connect("/ws/tanks/tank-1") as ws:
            message = ws.receive()

    assert message["type"] == "websocket.close"
    assert message["code"] == 1011
    assert message["reason"] == "internal error"
    assert "database unreachable" not in message["reason"]
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errors and errors[0].exc_info is not None
    assert feed.subscribed == []


# --- /ws/alerts -------------------------------------------------------------------------------


def test_alert_stream_pushes_every_alert_wrapped_in_a_typed_event(
    client: TestClient, alert_feed: FakeAlertFeed
) -> None:
    alert_feed.pending = [alert(1), alert(2, AlertStatus.ACKNOWLEDGED)]

    with client.websocket_connect("/ws/alerts") as ws:
        first, second = ws.receive_json(), ws.receive_json()

    assert first == {
        "type": "alert",
        "alert": {
            "id": str(UUID(int=1)),
            "tank_id": "tank-1",
            "batch_id": str(UUID(int=1)),
            "kind": "out_of_range",
            "measurement": "temperature",
            "status": "open",
            "opened_at": "2026-01-01T12:00:00Z",
            "acknowledged_at": None,
            "resolved_at": None,
            "details": {"observed": 25.5},
            "version": 1,
        },
    }
    assert second["alert"]["tank_id"] == "tank-2"  # all tanks, not just one
    assert second["alert"]["status"] == "acknowledged"
    assert second["alert"]["acknowledged_at"] == "2026-01-01T12:00:00Z"


def test_disconnecting_from_the_alert_stream_unsubscribes(
    client: TestClient, alert_feed: FakeAlertFeed
) -> None:
    with client.websocket_connect("/ws/alerts") as ws:
        ws.send_text("ignored chatter")
        assert alert_feed.entered.wait(timeout=5)
        assert alert_feed.active == 1

    assert alert_feed.active == 0


def test_alert_stream_closes_a_disallowed_origin_with_4403_after_accept(
    client: TestClient, alert_feed: FakeAlertFeed
) -> None:
    with client.websocket_connect("/ws/alerts", headers={"origin": DISALLOWED}) as ws:
        message = ws.receive()

    assert message["type"] == "websocket.close"
    assert message["code"] == 4403
    assert message["reason"]
    assert alert_feed.active == 0 and not alert_feed.entered.is_set()


def test_alert_stream_accepts_allowed_origin_and_originless_clients(
    client: TestClient, alert_feed: FakeAlertFeed
) -> None:
    alert_feed.pending = [alert(1)]

    with client.websocket_connect("/ws/alerts", headers={"origin": ALLOWED}) as ws:
        assert ws.receive_json()["alert"]["id"] == str(UUID(int=1))
    with client.websocket_connect("/ws/alerts") as ws:
        assert ws.receive_json()["alert"]["id"] == str(UUID(int=1))


class FailingAlertFeed:
    def subscribe_alerts(self) -> object:
        raise ConnectionError("listener exploded")


def test_alert_stream_subscription_failure_closes_with_1011_and_logs(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    client.app.dependency_overrides[get_alert_feed] = lambda: FailingAlertFeed()  # type: ignore[attr-defined]

    with caplog.at_level(logging.ERROR):
        with client.websocket_connect("/ws/alerts") as ws:
            message = ws.receive()

    assert message["type"] == "websocket.close"
    assert message["code"] == 1011
    assert message["reason"] == "internal error"
    assert "exploded" not in message["reason"]
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errors and errors[0].exc_info is not None

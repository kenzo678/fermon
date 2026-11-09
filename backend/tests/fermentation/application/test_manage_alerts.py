from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from fermon.fermentation.application.manage_alerts import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    AcknowledgeAlert,
    GetAlert,
    ListAlerts,
)
from fermon.fermentation.domain import (
    Alert,
    AlertKind,
    AlertNotFoundError,
    AlertStatus,
    ConcurrentAlertUpdateError,
    InvalidAlertError,
    InvalidAlertTransitionError,
    InvalidIdentifierError,
    MeasurementType,
)
from tests.fermentation.fakes import InMemoryAlertRepository

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
LATER = T0 + timedelta(hours=1)


def make_alert(n: int, tank: str = "tank-1", **overrides: Any) -> Alert:
    values: dict[str, Any] = {
        "id": UUID(int=n),
        "tank_id": tank,
        "batch_id": UUID(int=1),
        "kind": AlertKind.OUT_OF_RANGE,
        "measurement": MeasurementType.TEMPERATURE,
        "status": AlertStatus.OPEN,
        "opened_at": T0 + timedelta(minutes=n),
    }
    return Alert(**{**values, **overrides})


def resolved(n: int, tank: str = "tank-1", **overrides: Any) -> Alert:
    return make_alert(
        n, tank, status=AlertStatus.RESOLVED, resolved_at=T0 + timedelta(hours=2), **overrides
    )


async def seeded() -> InMemoryAlertRepository:
    repo = InMemoryAlertRepository()
    acked = make_alert(
        2,
        kind=AlertKind.SILENT_SENSOR,
        measurement=None,
        status=AlertStatus.ACKNOWLEDGED,
        acknowledged_at=T0 + timedelta(minutes=3),
    )
    pressure = make_alert(4, "tank-2", measurement=MeasurementType.PRESSURE)
    for alert in (make_alert(1), acked, resolved(3, "tank-2"), pressure):
        await repo.add(alert)
    return repo


# --- ListAlerts -----------------------------------------------------------------------------


async def test_list_defaults_to_unresolved_alerts_newest_first() -> None:
    result = await ListAlerts(await seeded()).execute()

    assert [a.id.int for a in result] == [4, 2, 1]


async def test_list_filters_by_tank_batch_kind_and_status() -> None:
    repo = await seeded()
    await repo.add(make_alert(5, "tank-3", batch_id=UUID(int=9)))
    use_case = ListAlerts(repo)

    assert [a.id.int for a in await use_case.execute(tank_id=" tank-2 ")] == [4]
    assert [a.id.int for a in await use_case.execute(batch_id=UUID(int=9))] == [5]
    assert [a.id.int for a in await use_case.execute(kind=AlertKind.SILENT_SENSOR)] == [2]
    assert [a.id.int for a in await use_case.execute(statuses=[AlertStatus.RESOLVED])] == [3]
    both = await use_case.execute(
        statuses=[AlertStatus.RESOLVED, AlertStatus.OPEN, AlertStatus.OPEN]
    )
    assert [a.id.int for a in both] == [5, 4, 3, 1]


async def test_list_limit_keeps_the_newest_and_is_bounded() -> None:
    repo = await seeded()
    use_case = ListAlerts(repo)

    assert [a.id.int for a in await use_case.execute(limit=2)] == [4, 2]
    assert DEFAULT_LIMIT <= MAX_LIMIT
    for bad in (0, -1, MAX_LIMIT + 1):
        with pytest.raises(InvalidAlertError) as exc:
            await use_case.execute(limit=bad)
        assert exc.value.field == "limit"


async def test_list_rejects_a_blank_tank_filter() -> None:
    with pytest.raises(InvalidIdentifierError):
        await ListAlerts(await seeded()).execute(tank_id="  ")


# --- GetAlert -------------------------------------------------------------------------------


async def test_get_returns_the_alert_or_raises_not_found() -> None:
    repo = await seeded()

    assert (await GetAlert(repo).execute(UUID(int=1))).id == UUID(int=1)
    with pytest.raises(AlertNotFoundError) as exc:
        await GetAlert(repo).execute(UUID(int=99))
    assert exc.value.alert_id == str(UUID(int=99))


# --- AcknowledgeAlert -----------------------------------------------------------------------


async def test_acknowledge_opens_to_acknowledged_with_the_clock_time_and_stores_it() -> None:
    repo = await seeded()

    alert = await AcknowledgeAlert(repo, lambda: LATER).execute(UUID(int=1))

    assert alert.status is AlertStatus.ACKNOWLEDGED
    assert alert.acknowledged_at == LATER
    assert alert.version == 2
    assert await repo.get(UUID(int=1)) == alert


async def test_acknowledging_an_acknowledged_alert_is_an_idempotent_no_op() -> None:
    repo = await seeded()
    use_case = AcknowledgeAlert(repo, lambda: LATER)
    first = await use_case.execute(UUID(int=1))

    again = await AcknowledgeAlert(repo, lambda: LATER + timedelta(hours=1)).execute(UUID(int=1))
    stale = await use_case.execute(UUID(int=1), expected_version=1)  # goal already reached

    assert again == first and stale == first
    assert (await repo.get(UUID(int=1))) == first  # no new version, same acknowledged_at


async def test_acknowledging_a_resolved_alert_is_an_invalid_transition() -> None:
    repo = await seeded()

    with pytest.raises(InvalidAlertTransitionError):
        await AcknowledgeAlert(repo, lambda: LATER).execute(UUID(int=3))


async def test_acknowledging_an_unknown_alert_raises_not_found() -> None:
    with pytest.raises(AlertNotFoundError):
        await AcknowledgeAlert(await seeded(), lambda: LATER).execute(UUID(int=99))


async def test_acknowledge_with_a_stale_version_conflicts_and_writes_nothing() -> None:
    repo = await seeded()

    with pytest.raises(ConcurrentAlertUpdateError):
        await AcknowledgeAlert(repo, lambda: LATER).execute(UUID(int=1), expected_version=7)

    assert (await repo.get(UUID(int=1))).status is AlertStatus.OPEN  # type: ignore[union-attr]
    ok = await AcknowledgeAlert(repo, lambda: LATER).execute(UUID(int=1), expected_version=1)
    assert ok.status is AlertStatus.ACKNOWLEDGED


async def test_a_concurrent_write_between_read_and_update_surfaces_as_a_conflict() -> None:
    repo = await seeded()

    class Racing(InMemoryAlertRepository):
        async def get(self, alert_id: UUID) -> Alert | None:
            found = await super().get(alert_id)
            if found is not None and found.status is AlertStatus.OPEN:
                # the alert is resolved by someone else right after we read it
                self.alerts[found.id] = found.resolve(LATER)
            return found

    racing = Racing()
    racing.alerts = dict(repo.alerts)
    # Without an expected version the conflict is re-read: the alert is resolved now, so the
    # caller gets the real reason (invalid transition), not an opaque version conflict.
    with pytest.raises(InvalidAlertTransitionError):
        await AcknowledgeAlert(racing, lambda: LATER).execute(UUID(int=1))


async def test_a_concurrent_write_with_an_expected_version_still_conflicts() -> None:
    repo = await seeded()

    class Racing(InMemoryAlertRepository):
        async def get(self, alert_id: UUID) -> Alert | None:
            found = await super().get(alert_id)
            if found is not None and found.status is AlertStatus.OPEN:
                self.alerts[found.id] = found.acknowledge(LATER)
            return found

    racing = Racing()
    racing.alerts = dict(repo.alerts)
    with pytest.raises(ConcurrentAlertUpdateError):
        await AcknowledgeAlert(racing, lambda: LATER).execute(UUID(int=1), expected_version=1)


async def test_two_concurrent_acknowledges_both_succeed() -> None:
    # Two clients read the same open alert; the loser of the write must not get a 409.
    repo = await seeded()

    class Racing(InMemoryAlertRepository):
        raced = False

        async def get(self, alert_id: UUID) -> Alert | None:
            found = await super().get(alert_id)
            if found is not None and found.status is AlertStatus.OPEN and not self.raced:
                self.raced = True
                self.alerts[found.id] = found.acknowledge(LATER)
            return found

    racing = Racing()
    racing.alerts = dict(repo.alerts)
    result = await AcknowledgeAlert(racing, lambda: LATER).execute(UUID(int=1))

    assert result.status is AlertStatus.ACKNOWLEDGED
    assert result == racing.alerts[UUID(int=1)]

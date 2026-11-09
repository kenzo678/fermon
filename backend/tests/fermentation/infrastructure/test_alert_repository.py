from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from fermon.fermentation.domain import (
    Alert,
    AlertKind,
    AlertStatus,
    Batch,
    BatchStatus,
    ConcurrentAlertUpdateError,
    MeasurementType,
    StyleTemplate,
    TargetRanges,
)
from fermon.fermentation.infrastructure.persistence import (
    SqlAlchemyAlertRepository,
    SqlAlchemyBatchRepository,
    SqlAlchemyTankRepository,
)

pytestmark = pytest.mark.integration

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
TEMP = MeasurementType.TEMPERATURE
PRESSURE = MeasurementType.PRESSURE


def make_alert(n: int, tank: str = "tank-1", **overrides: Any) -> Alert:
    values: dict[str, Any] = {
        "id": UUID(int=n),
        "tank_id": tank,
        "batch_id": UUID(int=1),
        "kind": AlertKind.OUT_OF_RANGE,
        "measurement": TEMP,
        "status": AlertStatus.OPEN,
        "opened_at": T0 + timedelta(minutes=n),
        "details": {"observed": 25.5, "bound": "above", "target_min": 18.0, "target_max": 21.0},
    }
    return Alert(**{**values, **overrides})


def make_silent(n: int, tank: str = "tank-1", **overrides: Any) -> Alert:
    return make_alert(
        n,
        tank,
        kind=AlertKind.SILENT_SENSOR,
        measurement=None,
        details={"last_reading_at": T0.isoformat()},
        **overrides,
    )


@pytest.fixture(autouse=True)
async def batch(
    tank_repository: SqlAlchemyTankRepository, batch_repository: SqlAlchemyBatchRepository
) -> None:
    for tank in ("tank-1", "tank-2"):
        await tank_repository.ensure(tank, T0)
    await batch_repository.add(
        Batch(
            id=UUID(int=1),
            tank_id="tank-1",
            beer_name="Beer",
            style="IPA",
            template=StyleTemplate.CUSTOM,
            targets=TargetRanges(18.0, 21.0, 1.0),
            status=BatchStatus.PLANNED,
            planned_start=T0,
            created_at=T0,
        )
    )


async def test_add_and_get_round_trip_every_field(
    alert_repository: SqlAlchemyAlertRepository,
) -> None:
    full = make_alert(
        2, status=AlertStatus.ACKNOWLEDGED, acknowledged_at=T0 + timedelta(minutes=5), version=2
    )
    silent = make_silent(3, "tank-2", batch_id=UUID(int=1))

    assert await alert_repository.add(full) is True
    assert await alert_repository.add(silent) is True

    assert await alert_repository.get(full.id) == full
    assert await alert_repository.get(silent.id) == silent
    assert await alert_repository.get(UUID(int=99)) is None


async def test_a_second_unresolved_alert_of_the_same_kind_is_reported_not_stored(
    alert_repository: SqlAlchemyAlertRepository,
) -> None:
    assert await alert_repository.add(make_alert(1)) is True
    assert await alert_repository.add(make_alert(2)) is False
    assert await alert_repository.get(UUID(int=2)) is None

    # Same tank but another measurement or kind, or another tank, is a different key.
    assert await alert_repository.add(make_alert(3, measurement=PRESSURE)) is True
    assert await alert_repository.add(make_silent(4)) is True
    assert await alert_repository.add(make_alert(5, "tank-2")) is True
    # Silent alerts have no measurement; NULLs must still collide.
    assert await alert_repository.add(make_silent(6)) is False


async def test_resolving_frees_the_key_for_a_new_alert(
    alert_repository: SqlAlchemyAlertRepository,
) -> None:
    first = make_alert(1)
    await alert_repository.add(first)
    await alert_repository.update(first.resolve(T0 + timedelta(minutes=9)))

    assert await alert_repository.add(make_alert(2)) is True
    unresolved = await alert_repository.get_unresolved("tank-1", AlertKind.OUT_OF_RANGE, TEMP)
    assert unresolved is not None and unresolved.id == UUID(int=2)


async def test_database_enforces_one_unresolved_alert_even_bypassing_the_repository(
    alert_repository: SqlAlchemyAlertRepository, engine: AsyncEngine
) -> None:
    await alert_repository.add(make_silent(1))

    with pytest.raises(IntegrityError, match="uq_alerts_one_unresolved"):
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO alerts (id, tank_id, batch_id, kind, status, opened_at) "
                    "VALUES (:id, 'tank-1', :batch, 'silent_sensor', 'open', now())"
                ),
                {"id": UUID(int=2), "batch": UUID(int=1)},
            )


async def test_update_stores_the_new_revision_and_rejects_stale_ones(
    alert_repository: SqlAlchemyAlertRepository,
) -> None:
    alert = make_alert(1)
    await alert_repository.add(alert)
    acked = alert.acknowledge(alert.opened_at + timedelta(minutes=1))
    await alert_repository.update(acked)
    assert await alert_repository.get(alert.id) == acked

    # A stale writer (still on version 1) must not overwrite the acknowledgement.
    with pytest.raises(ConcurrentAlertUpdateError) as exc:
        await alert_repository.update(alert.resolve(T0 + timedelta(minutes=2)))
    assert exc.value.alert_id == str(alert.id)
    assert await alert_repository.get(alert.id) == acked

    with pytest.raises(ConcurrentAlertUpdateError):
        await alert_repository.update(
            make_alert(9).acknowledge(T0 + timedelta(minutes=9))
        )  # unknown alert


async def test_list_filters_and_orders_newest_first(
    alert_repository: SqlAlchemyAlertRepository,
) -> None:
    a = make_alert(1)
    b = make_silent(2)
    c = make_alert(3, "tank-2")
    d = make_alert(4, measurement=PRESSURE)
    for alert in (a, b, c, d):
        await alert_repository.add(alert)
    await alert_repository.update(a.acknowledge(T0 + timedelta(hours=1)))

    async def ids(**filters: Any) -> list[UUID]:
        return [x.id for x in await alert_repository.list(**filters)]

    assert await ids() == [d.id, c.id, b.id, a.id]
    assert await ids(tank_id="tank-1") == [d.id, b.id, a.id]
    assert await ids(status=AlertStatus.ACKNOWLEDGED) == [a.id]
    assert await ids(kind=AlertKind.SILENT_SENSOR) == [b.id]
    assert await ids(tank_id="tank-1", status=AlertStatus.OPEN, kind=AlertKind.OUT_OF_RANGE) == [
        d.id
    ]


async def test_get_unresolved_matches_tank_kind_and_measurement(
    alert_repository: SqlAlchemyAlertRepository,
) -> None:
    await alert_repository.add(make_alert(1))
    await alert_repository.add(make_silent(2))

    async def found(tank: str, kind: AlertKind, m: MeasurementType | None) -> UUID | None:
        alert = await alert_repository.get_unresolved(tank, kind, m)
        return alert.id if alert else None

    assert await found("tank-1", AlertKind.OUT_OF_RANGE, TEMP) == UUID(int=1)
    assert await found("tank-1", AlertKind.SILENT_SENSOR, None) == UUID(int=2)
    assert await found("tank-1", AlertKind.OUT_OF_RANGE, PRESSURE) is None
    assert await found("tank-2", AlertKind.OUT_OF_RANGE, TEMP) is None


async def test_database_rejects_inconsistent_rows(
    alert_repository: SqlAlchemyAlertRepository, engine: AsyncEngine
) -> None:
    await alert_repository.add(make_alert(1))

    async def run(statement: str) -> None:
        async with engine.begin() as conn:
            await conn.execute(text(statement))

    with pytest.raises(IntegrityError, match="ck_alerts_status"):
        await run("UPDATE alerts SET status = 'closed'")
    with pytest.raises(IntegrityError, match="ck_alerts_kind"):
        await run("UPDATE alerts SET kind = 'loud'")
    with pytest.raises(IntegrityError, match="ck_alerts_measurement_by_kind"):
        await run("UPDATE alerts SET measurement = NULL")
    with pytest.raises(IntegrityError, match="fk_alerts_batch_id"):
        await alert_repository.add(make_alert(2, "tank-2", batch_id=UUID(int=77)))
    with pytest.raises(IntegrityError, match="fk_alerts_tank_id"):
        await alert_repository.add(make_alert(3, "ghost"))


async def test_list_filters_by_batch(
    alert_repository: SqlAlchemyAlertRepository, batch_repository: SqlAlchemyBatchRepository
) -> None:
    await batch_repository.add(
        Batch(
            id=UUID(int=2),
            tank_id="tank-2",
            beer_name="Beer",
            style="IPA",
            template=StyleTemplate.CUSTOM,
            targets=TargetRanges(18.0, 21.0, 1.0),
            status=BatchStatus.PLANNED,
            planned_start=T0,
            created_at=T0,
        )
    )
    mine = make_alert(1)
    theirs = make_alert(2, "tank-2", batch_id=UUID(int=2))
    await alert_repository.add(mine)
    await alert_repository.add(theirs)

    assert [a.id for a in await alert_repository.list(batch_id=UUID(int=2))] == [theirs.id]
    assert [a.id for a in await alert_repository.list(batch_id=UUID(int=1))] == [mine.id]

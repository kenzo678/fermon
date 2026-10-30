from datetime import UTC, datetime

import pytest

from fermon.fermentation.domain import InvalidTankError, Tank

SEEN = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_id_is_normalized_and_display_name_is_optional() -> None:
    tank = Tank(id="  tank-1 ", display_name=None, first_seen_at=SEEN)

    assert tank.id == "tank-1"
    assert tank.display_name is None


@pytest.mark.parametrize("raw", ["", "   ", 7])
def test_blank_or_non_string_id_is_rejected(raw: object) -> None:
    with pytest.raises(InvalidTankError) as exc:
        Tank(id=raw, display_name=None, first_seen_at=SEEN)  # type: ignore[arg-type]

    assert exc.value.field == "id"


def test_naive_first_seen_at_is_rejected() -> None:
    with pytest.raises(InvalidTankError) as exc:
        Tank(id="tank-1", display_name=None, first_seen_at=datetime(2026, 1, 1))

    assert exc.value.field == "first_seen_at"

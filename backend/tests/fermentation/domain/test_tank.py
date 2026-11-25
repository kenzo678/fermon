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


def test_rename_trims_the_name_and_keeps_the_rest() -> None:
    tank = Tank(id="tank-1", display_name=None, first_seen_at=SEEN)

    renamed = tank.rename("  Fermenter 1 ")

    assert renamed == Tank(id="tank-1", display_name="Fermenter 1", first_seen_at=SEEN)
    assert tank.display_name is None  # tanks are immutable


def test_rename_to_none_clears_the_name() -> None:
    tank = Tank(id="tank-1", display_name="Fermenter 1", first_seen_at=SEEN)

    assert tank.rename(None).display_name is None


def test_rename_accepts_the_length_limits() -> None:
    tank = Tank(id="tank-1", display_name=None, first_seen_at=SEEN)

    assert tank.rename("a").display_name == "a"
    assert tank.rename("a" * 64).display_name == "a" * 64


@pytest.mark.parametrize("raw", ["", "   ", "a" * 65, 7])
def test_rename_rejects_blank_too_long_or_non_string_names(raw: object) -> None:
    tank = Tank(id="tank-1", display_name=None, first_seen_at=SEEN)

    with pytest.raises(InvalidTankError) as exc:
        tank.rename(raw)  # type: ignore[arg-type]

    assert exc.value.field == "display_name"

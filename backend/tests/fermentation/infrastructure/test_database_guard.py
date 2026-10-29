import pytest

from tests.fermentation.infrastructure.database import require_test_database


def test_accepts_database_name_ending_in_test() -> None:
    url = "postgresql+asyncpg://u:p@host:5432/fermon_test"
    assert require_test_database(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://u:p@host:5432/fermon",
        "postgresql+asyncpg://u:p@host:5432/test_fermon",
        "postgresql+asyncpg://u:p@host:5432/",
        "postgresql+asyncpg://u:p@host:5432",
    ],
)
def test_refuses_database_names_not_ending_in_test(url: str) -> None:
    with pytest.raises(RuntimeError, match="_test"):
        require_test_database(url)

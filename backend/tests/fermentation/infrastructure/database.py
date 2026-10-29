from pathlib import Path

from alembic.config import Config
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[3]


def require_test_database(url: str) -> str:
    """Return ``url`` only if it targets a database named ``*_test`` (the suite truncates it)."""
    name = make_url(url).database or ""
    if not name.endswith("_test"):
        raise RuntimeError(
            f"refusing to run integration tests against database {name!r}: "
            "TEST_DATABASE_URL must point to a database whose name ends with '_test'"
        )
    return url


def alembic_config(url: str) -> Config:
    """Build an Alembic config that does not depend on the current working directory."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config

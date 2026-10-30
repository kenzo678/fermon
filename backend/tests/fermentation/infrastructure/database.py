from sqlalchemy.engine import make_url


def require_test_database(url: str) -> str:
    """Return ``url`` only if it targets a database named ``*_test`` (the suite truncates it)."""
    name = make_url(url).database or ""
    if not name.endswith("_test"):
        raise RuntimeError(
            f"refusing to run integration tests against database {name!r}: "
            "TEST_DATABASE_URL must point to a database whose name ends with '_test'"
        )
    return url

import pytest
from pydantic import ValidationError

from fermon.shared.config import Settings


def test_default_topic_is_derived_from_the_prefix() -> None:
    assert Settings(mqtt_topic_prefix="fermon").mqtt_topic == "fermon/tanks/+/readings"


@pytest.mark.parametrize(
    "prefix", ["", " ", "fer+mon", "fermon#", "fermon/dev", " fermon", "fermon "]
)
def test_invalid_topic_prefix_is_rejected(prefix: str) -> None:
    with pytest.raises(ValidationError, match="MQTT_TOPIC_PREFIX"):
        Settings(mqtt_topic_prefix=prefix)


def test_configured_mqtt_topic_env_var_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MQTT_TOPIC", "custom/topic")
    with pytest.raises(ValidationError, match="MQTT_TOPIC_PREFIX"):
        Settings()


def test_mqtt_topic_prefix_env_var_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MQTT_TOPIC_PREFIX", "plant-a")
    assert Settings().mqtt_topic == "plant-a/tanks/+/readings"


def test_alembic_ini_path_defaults_to_the_source_tree_and_is_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert Settings().alembic_ini_path.name == "alembic.ini"
    monkeypatch.setenv("ALEMBIC_INI_PATH", "/opt/fermon/alembic.ini")
    assert str(Settings().alembic_ini_path) == "/opt/fermon/alembic.ini"


def test_cors_origins_default_to_local_dashboard_dev_servers() -> None:
    assert Settings().cors_origins == ["http://localhost:5173", "http://localhost:3000"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://a.example", ["https://a.example"]),
        ("https://a.example, https://b.example ,", ["https://a.example", "https://b.example"]),
        ('["https://a.example", "https://b.example"]', ["https://a.example", "https://b.example"]),
    ],
    ids=["single", "comma-separated", "json"],
)
def test_cors_origins_env_var_accepts_comma_separated_or_json(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: list[str]
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", raw)
    assert Settings().cors_origins == expected

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


def test_cors_origins_default_to_local_dashboard_dev_servers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Compose injects CORS_ORIGINS into the container; the default is what applies without it.
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
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


def test_alert_thresholds_default_to_five_two_and_ten_minutes() -> None:
    settings = Settings()
    assert settings.alert_out_of_range_seconds == 300
    assert settings.alert_resolve_seconds == 120
    assert settings.alert_silent_seconds == 600
    assert settings.alert_silent_check_interval_seconds == 60


def test_alert_thresholds_are_configurable_through_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALERT_OUT_OF_RANGE_SECONDS", "20")
    monkeypatch.setenv("ALERT_RESOLVE_SECONDS", "10")
    monkeypatch.setenv("ALERT_SILENT_SECONDS", "30")
    monkeypatch.setenv("ALERT_SILENT_CHECK_INTERVAL_SECONDS", "5")
    settings = Settings()
    assert (
        settings.alert_out_of_range_seconds,
        settings.alert_resolve_seconds,
        settings.alert_silent_seconds,
        settings.alert_silent_check_interval_seconds,
    ) == (20, 10, 30, 5)


@pytest.mark.parametrize(
    "name",
    [
        "alert_out_of_range_seconds",
        "alert_resolve_seconds",
        "alert_silent_seconds",
        "alert_silent_check_interval_seconds",
    ],
)
@pytest.mark.parametrize("value", [0, -1])
def test_alert_thresholds_must_be_positive(name: str, value: int) -> None:
    with pytest.raises(ValidationError, match=name):
        Settings(**{name: value})


def test_session_settings_default_to_eight_hours_and_an_insecure_cookie_for_local_dev() -> None:
    settings = Settings()
    assert settings.session_ttl_seconds == 8 * 3600
    assert settings.session_cookie_secure is False


def test_session_settings_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_TTL_SECONDS", "600")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    settings = Settings()
    assert (settings.session_ttl_seconds, settings.session_cookie_secure) == (600, True)


def test_session_ttl_must_be_positive() -> None:
    with pytest.raises(ValueError):
        Settings(session_ttl_seconds=0)


def test_login_throttle_defaults_and_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    defaults = Settings()
    assert (
        defaults.login_max_failures_per_account,
        defaults.login_max_failures_per_ip,
        defaults.login_throttle_window_seconds,
    ) == (5, 20, 15 * 60)
    monkeypatch.setenv("LOGIN_MAX_FAILURES_PER_ACCOUNT", "3")
    monkeypatch.setenv("LOGIN_THROTTLE_WINDOW_SECONDS", "60")
    settings = Settings()
    assert (settings.login_max_failures_per_account, settings.login_throttle_window_seconds) == (
        3,
        60,
    )


@pytest.mark.parametrize(
    "name",
    [
        "login_max_failures_per_account",
        "login_max_failures_per_ip",
        "login_throttle_window_seconds",
    ],
)
def test_login_throttle_settings_must_be_positive(name: str) -> None:
    with pytest.raises(ValidationError, match=name):
        Settings(**{name: 0})

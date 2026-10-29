import pytest

from fermon.fermentation.infrastructure.mqtt.messages import InvalidTopicError, parse_topic


def test_parse_topic_returns_tank_id() -> None:
    assert parse_topic("fermon/tanks/tank-1/readings", "fermon") == "tank-1"


def test_parse_topic_uses_the_configured_prefix() -> None:
    assert parse_topic("fermon-test/tanks/tank-1/readings", "fermon-test") == "tank-1"
    with pytest.raises(InvalidTopicError):
        parse_topic("fermon/tanks/tank-1/readings", "fermon-test")
    with pytest.raises(InvalidTopicError):
        parse_topic("fermon-test/tanks/tank-1/readings", "fermon")


def test_parse_topic_treats_the_prefix_literally() -> None:
    with pytest.raises(InvalidTopicError):
        parse_topic("fermonXtanks/tank-1/readings", "fermon.")


@pytest.mark.parametrize(
    "topic",
    [
        "fermon/tanks//readings",
        "fermon/tanks/tank-1/other",
        "fermon/tanks/tank-1/readings/extra",
        "other/tanks/tank-1/readings",
        "fermon/tanks/+/readings",
        "fermon/tanks/a/b/readings",
        "",
    ],
)
def test_parse_topic_rejects_other_topics(topic: str) -> None:
    with pytest.raises(InvalidTopicError):
        parse_topic(topic, "fermon")

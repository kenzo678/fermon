import pytest

from fermon.fermentation.infrastructure.mqtt.messages import InvalidTopicError, parse_topic


def test_parse_topic_returns_tank_id() -> None:
    assert parse_topic("fermon/tanks/tank-1/readings") == "tank-1"


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
        parse_topic(topic)

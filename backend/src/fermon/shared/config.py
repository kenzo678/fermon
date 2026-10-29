from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://fermon:fermon@timescaledb:5432/fermon"
    mqtt_host: str = "mosquitto"
    mqtt_port: int = 1883
    mqtt_client_id: str = "fermon-ingestor"
    mqtt_topic: str = "fermon/tanks/+/readings"

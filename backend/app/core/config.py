from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "SpiderMan"
    debug: bool = False
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    database_url: str = "postgresql+asyncpg://spiderman:spiderman@localhost:5432/spiderman"
    redis_url: str = "redis://localhost:6379/0"
    worker_api_key: str = "change-me-in-production"
    admin_username: str = "admin"
    admin_password: str = "admin123"
    heartbeat_interval: int = 10
    heartbeat_timeout: int = 60
    log_retention_days: int = 30
    master_local_node_id: str = "master-local"
    master_local_api_key: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    app_env: str = "development"
    secret_key: str = "change-me"
    database_url: str = "postgresql+asyncpg://agent:agent123@localhost:5432/perfume_video"
    celery_broker_url: str = "redis://localhost:6379/0"

    litellm_base_url: str = "http://localhost:4000/v1"
    litellm_api_key: str = "sk-litellm-master"

    agnes_video_api_key: str = ""
    agnes_video_base_url: str = "https://apihub.agnes-ai.com"

    voxcpm2_base_url: str = "http://localhost:8080"
    latentsync_base_url: str = "http://localhost:8090"
    rustfs_base_url: str = "http://localhost:8001"
    funasr_base_url: str = "http://localhost:8021/v1"

    google_client_id: str = ""
    google_client_secret: str = ""

    langfuse_public_key: str = "pk-lf-default"
    langfuse_secret_key: str = "sk-lf-default"
    langfuse_host: str = "http://localhost:3060"

    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7


settings = Settings()

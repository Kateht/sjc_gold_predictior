from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


def _resolve_path(value: str) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    return str(path)


def _normalize_sqlite_url(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith("sqlite:///"):
        db_path = cleaned.removeprefix("sqlite:///")
        return f"sqlite:///{Path(_resolve_path(db_path)).as_posix()}"
    return cleaned


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), env_file_encoding="utf-8", extra="ignore")

    APP_TITLE: str
    API_V1_PREFIX: str
    PROJECT_ROOT: str = str(BASE_DIR)
    DATABASE_URL: str | None = None
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int

    LOCAL_DATASET_PATH: str
    CRAWLER_DATASET_PATH: str
    MODEL_DIR: str
    PRIMARY_PRICE_MODEL_ARTIFACT_PATH: str
    GOLD_CLI_MODULE: str
    GOLD_CLI_CONFIG_PATH: str

    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL_NAME: str
    ENABLE_GEMINI: bool

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int

    DEFAULT_ADMIN_EMAIL: str
    DEFAULT_ADMIN_PASSWORD: str
    AUTO_SEED_ADMIN: bool

    CORS_ORIGINS: str

    @field_validator(
        "LOCAL_DATASET_PATH",
        "CRAWLER_DATASET_PATH",
        "MODEL_DIR",
        "PRIMARY_PRICE_MODEL_ARTIFACT_PATH",
        "GOLD_CLI_CONFIG_PATH",
        mode="before",
    )
    @classmethod
    def _normalize_paths(cls, value: str) -> str:
        if value is None or str(value).strip() == "":
            raise ValueError("Path configuration cannot be empty")
        return _resolve_path(str(value))

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        if not cleaned:
            return None
        return _normalize_sqlite_url(cleaned)

    @field_validator("GOLD_CLI_MODULE", mode="before")
    @classmethod
    def _normalize_module_name(cls, value: str) -> str:
        if value is None or str(value).strip() == "":
            raise ValueError("GOLD_CLI_MODULE cannot be empty")
        return str(value).strip()

    def get_cors_origins(self) -> list[str]:
        raw = (self.CORS_ORIGINS or "").strip()
        if not raw or raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    def get_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL

        if self.POSTGRES_DB and self.POSTGRES_USER and self.POSTGRES_PASSWORD and self.POSTGRES_HOST and self.POSTGRES_PORT:
            return (
                f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )

        return _normalize_sqlite_url(f"sqlite:///{(BASE_DIR / 'gold_prediction.db').as_posix()}")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
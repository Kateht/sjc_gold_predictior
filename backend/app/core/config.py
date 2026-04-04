import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_TITLE: str = "Gold AI Agent"
    GEMINI_API_KEY: str = ""
    MODEL_DIR: str = "app/ai/weights"
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    class Config:
        env_file = ".env"

settings = Settings()

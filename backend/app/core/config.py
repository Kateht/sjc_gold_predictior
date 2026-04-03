import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_TITLE: str = "Gold AI Agent"
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    MODEL_DIR: str = "app/ai/weights"

settings = Settings()
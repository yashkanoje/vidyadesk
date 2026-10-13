from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Puts .env into os.environ so LangSmith and other libraries see it too. Existing variables win.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Settings(BaseSettings):
    database_url: str  # postgresql://user:password@host:5432/dbname
    anthropic_api_key: str
    fernet_key: str
    llm_model: str = "claude-haiku-4-5-20251001"
    whatsapp_app_secret: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_api_version: str = "v24.0"
    public_base_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()

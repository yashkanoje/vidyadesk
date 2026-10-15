from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Puts .env into os.environ so LangSmith and other libraries see it too. Existing variables win.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Settings(BaseSettings):
    database_url: str  # postgresql://user:password@host:5432/dbname
    fernet_key: str
    llm_provider: Literal["anthropic", "gemini"] = "anthropic"
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"
    google_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    # Passages less similar than this to the question are not shown to the agent. Set from the retrieval
    # test set (python -m evals.retrieval); 0.0 until it has been measured.
    rag_min_similarity: float = 0.0
    whatsapp_app_secret: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_api_version: str = "v24.0"
    public_base_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()

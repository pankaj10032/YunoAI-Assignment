from functools import lru_cache
import os
from typing import List

from dotenv import load_dotenv


load_dotenv()


def _csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings:
    app_name: str = os.getenv("APP_NAME", "AI Orchestrator")
    environment: str = os.getenv("ENVIRONMENT", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/ai_orchestrator.db")

    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1")
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai").lower()

    telegram_bot_token: str | None = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_webhook_url: str | None = os.getenv("TELEGRAM_WEBHOOK_URL")

    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    cors_origins: List[str] = _csv(
        os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    )

    max_agent_iterations: int = int(os.getenv("MAX_AGENT_ITERATIONS", "5"))
    default_agent_timeout_seconds: int = int(
        os.getenv("DEFAULT_AGENT_TIMEOUT_SECONDS", "120")
    )
    enable_telegram_polling: bool = (
        os.getenv("ENABLE_TELEGRAM_POLLING", "false").lower() == "true"
    )
    scheduler_max_concurrent_jobs: int = int(
        os.getenv("SCHEDULER_MAX_CONCURRENT_JOBS", "5")
    )
    scheduler_job_store_url: str = os.getenv("SCHEDULER_JOB_STORE_URL", database_url)

    def validate_runtime(self) -> None:
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        if self.llm_provider not in {"openai", "ollama"}:
            raise RuntimeError("LLM_PROVIDER must be either 'openai' or 'ollama'")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

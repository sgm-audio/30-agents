"""
Core configuration loader for the 30-Agent system.
Reads from .env and provides typed settings.
"""
import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseModel):
    # Ollama
    ollama_host: str = "http://127.0.0.1:11435"
    model_fast: str = "hf.co/evalengine/unbound-e2b-gguf:Q4_K_M"
    model_reason: str = "huihui_ai/gemma-4-abliterated:e4b-q4_K"
    model_vision: str = "minicpm-v:8b"
    model_embed: str = "nomic-embed-text"

    # Redis
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None

    # ChromaDB
    chroma_persist_dir: str = str(PROJECT_ROOT / "data" / "chroma")

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    chroma_collection: str = "agent_memory"

    # Logging
    log_level: str = "INFO"
    log_dir: str = str(PROJECT_ROOT / "logs")

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret: Optional[str] = None

    # Performance
    max_concurrent_agents: int = 8
    agent_timeout: int = 120
    agent_retry_max: int = 3
    ollama_timeout: float = 300.0
    ollama_num_parallel: int = 4
    ollama_max_loaded_models: int = 3

    # CORS
    cors_origins: list[str] = ["*"]

    # Outreach / Lead Generation
    serper_api_key: Optional[str] = None
    tavily_api_key: Optional[str] = None
    firecrawl_api_key: Optional[str] = None
    hunter_api_key: Optional[str] = None
    resend_api_key: Optional[str] = None
    outreach_city: str = "Vancouver"
    outreach_region: str = "BC"
    outreach_country: str = "Canada"
    outreach_max_leads: int = 200
    outreach_email_from: str = "hello@example.com"
    outreach_domain: str = "example.com"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            ollama_host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11435"),
            model_fast=os.getenv("MODEL_FAST", "hf.co/evalengine/unbound-e2b-gguf:Q4_K_M"),
            model_reason=os.getenv("MODEL_REASON", "huihui_ai/gemma-4-abliterated:e4b-q4_K"),
            model_vision=os.getenv("MODEL_VISION", "minicpm-v:8b"),
            model_embed=os.getenv("MODEL_EMBED", "nomic-embed-text"),
            redis_host=os.getenv("REDIS_HOST", "127.0.0.1"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            redis_db=int(os.getenv("REDIS_DB", "0")),
            redis_password=os.getenv("REDIS_PASSWORD") or None,
            chroma_persist_dir=os.getenv(
                "CHROMA_PERSIST_DIR", str(PROJECT_ROOT / "data" / "chroma")
            ),
            chroma_collection=os.getenv("CHROMA_COLLECTION", "agent_memory"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_dir=os.getenv("LOG_DIR", str(PROJECT_ROOT / "logs")),
            api_host=os.getenv("API_HOST", "0.0.0.0"),
            api_port=int(os.getenv("API_PORT", "8000")),
            api_secret=os.getenv("API_SECRET") or None,
            max_concurrent_agents=int(os.getenv("MAX_CONCURRENT_AGENTS", "8")),
            agent_timeout=int(os.getenv("AGENT_TIMEOUT", "120")),
            agent_retry_max=int(os.getenv("AGENT_RETRY_MAX", "3")),
            ollama_timeout=float(os.getenv("OLLAMA_TIMEOUT", "300")),
            ollama_num_parallel=int(os.getenv("OLLAMA_NUM_PARALLEL", "4")),
            ollama_max_loaded_models=int(os.getenv("OLLAMA_MAX_LOADED_MODELS", "3")),
            cors_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")],
            serper_api_key=os.getenv("SERPER_API_KEY") or None,
            tavily_api_key=os.getenv("TAVILY_API_KEY") or None,
            firecrawl_api_key=os.getenv("FIRECRAWL_API_KEY") or None,
            hunter_api_key=os.getenv("HUNTER_API_KEY") or None,
            resend_api_key=os.getenv("RESEND_API_KEY") or None,
            outreach_city=os.getenv("OUTREACH_CITY", "Vancouver"),
            outreach_region=os.getenv("OUTREACH_REGION", "BC"),
            outreach_country=os.getenv("OUTREACH_COUNTRY", "Canada"),
            outreach_max_leads=int(os.getenv("OUTREACH_MAX_LEADS", "200")),
            outreach_email_from=os.getenv("OUTREACH_EMAIL_FROM", "hello@example.com"),
            outreach_domain=os.getenv("OUTREACH_DOMAIN", "example.com"),
        )


# Singleton settings instance
settings = Settings.from_env()

# Ensure directories exist
Path(settings.chroma_persist_dir).mkdir(parents=True, exist_ok=True)
Path(settings.log_dir).mkdir(parents=True, exist_ok=True)

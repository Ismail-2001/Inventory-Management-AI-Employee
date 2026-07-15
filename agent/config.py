import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv


load_dotenv()


@dataclass
class Settings:
    shopify_store_domain: str = field(
        default_factory=lambda: os.getenv("SHOPIFY_STORE_DOMAIN", "")
    )
    shopify_admin_api_token: str = field(
        default_factory=lambda: os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    )
    shopify_api_version: str = field(
        default_factory=lambda: os.getenv("SHOPIFY_API_VERSION", "2026-01")
    )

    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://inventory:inventory@localhost:5432/inventory_agent",
        )
    )

    checkpointer_database_url: str = field(
        default_factory=lambda: os.getenv(
            "CHECKPOINTER_DATABASE_URL",
            os.getenv("DATABASE_URL", "postgresql+asyncpg://inventory:inventory@localhost:5432/inventory_agent")
            .replace("+asyncpg", ""),
        )
    )

    llm_provider: str = field(
        default_factory=lambda: os.getenv("LLM_PROVIDER", "openai")
    )
    openai_api_key: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )
    google_api_key: str = field(
        default_factory=lambda: os.getenv("GOOGLE_API_KEY", "")
    )

    agent_api_key: str = field(
        default_factory=lambda: os.getenv("AGENT_API_KEY", "demo-key-2024")
    )

    environment: str = field(
        default_factory=lambda: os.getenv("ENVIRONMENT", "development")
    )
    allow_demo_key: bool = field(
        default_factory=lambda: os.getenv(
            "ALLOW_DEMO_KEY", "true" if os.getenv("ENVIRONMENT", "development") != "production" else "false"
        ).lower() == "true"
    )

    model_name: str = field(
        default_factory=lambda: os.getenv("MODEL_NAME", "gemini-2.0-flash")
    )
    daily_llm_spend_cap: float = field(
        default_factory=lambda: float(os.getenv("DAILY_LLM_SPEND_CAP", "5"))
    )
    temperature: float = field(
        default_factory=lambda: float(os.getenv("TEMPERATURE", "0.3"))
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("MAX_TOKENS", "1024"))
    )

    slack_webhook_url: str = field(
        default_factory=lambda: os.getenv("SLACK_WEBHOOK_URL", "")
    )

    shopify_webhook_secret: str = field(
        default_factory=lambda: os.getenv("SHOPIFY_WEBHOOK_SECRET", "")
    )

    allowed_origins: list = field(
        default_factory=lambda: [
            o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",") if o.strip()
        ]
    )

    def validate_required(self):
        missing = []
        if not self.shopify_store_domain:
            missing.append("SHOPIFY_STORE_DOMAIN")
        if not self.shopify_admin_api_token:
            missing.append("SHOPIFY_ADMIN_API_TOKEN")
        if not self.database_url:
            missing.append("DATABASE_URL")
        if missing:
            raise ValueError(
                f"Missing required settings: {', '.join(missing)}. "
                "Check your .env file."
            )


settings = Settings()

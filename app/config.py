import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _as_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _extensions() -> frozenset[str]:
    values = os.getenv("ALLOWED_EXTENSIONS", ".html,.htm").split(",")
    normalized = {
        value if value.startswith(".") else f".{value}"
        for item in values
        if (value := item.strip().lower())
    }
    return frozenset(normalized or {".html", ".htm"})


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = "0.0.0.0"
    port: int = 65330
    log_level: str = "INFO"
    upload_dir: Path = Path("uploads")
    api_key: str = ""

    github_repo: str = ""
    github_token: str = ""
    github_pages_domain: str = ""

    notion_database_id: str = ""
    notion_token: str = ""
    telegram_token: str = ""
    telegram_chat_id: str = ""

    openai_api_key: str = ""
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_max_retries: int = 3

    max_file_size: int = 30 * 1024 * 1024
    allowed_extensions: frozenset[str] = field(
        default_factory=lambda: frozenset({".html", ".htm"})
    )

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            host=os.getenv("WEB_CLIPPER_HOST", "0.0.0.0"),
            port=_as_int("WEB_CLIPPER_PORT", 65330),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            upload_dir=Path(os.getenv("UPLOAD_DIR", "uploads")),
            api_key=os.getenv("API_KEY", ""),
            github_repo=os.getenv("GITHUB_REPO", ""),
            github_token=os.getenv("GITHUB_TOKEN", ""),
            github_pages_domain=os.getenv("GITHUB_PAGES_DOMAIN", ""),
            notion_database_id=os.getenv("NOTION_DATABASE_ID", ""),
            notion_token=os.getenv("NOTION_TOKEN", ""),
            telegram_token=os.getenv("TELEGRAM_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_base_url=os.getenv("OPENAI_BASE_URL") or None,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            openai_max_retries=_as_int("OPENAI_MAX_RETRIES", 3),
            max_file_size=_as_int("MAX_FILE_SIZE", 30 * 1024 * 1024),
            allowed_extensions=_extensions(),
        )

    def missing_integration_settings(self) -> list[str]:
        required = {
            "GITHUB_REPO": self.github_repo,
            "GITHUB_TOKEN": self.github_token,
            "GITHUB_PAGES_DOMAIN": self.github_pages_domain,
            "NOTION_DATABASE_ID": self.notion_database_id,
            "NOTION_TOKEN": self.notion_token,
            "TELEGRAM_TOKEN": self.telegram_token,
            "TELEGRAM_CHAT_ID": self.telegram_chat_id,
            "OPENAI_API_KEY": self.openai_api_key,
        }
        return [name for name, value in required.items() if not value]

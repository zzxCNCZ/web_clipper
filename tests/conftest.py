from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import create_app
from app.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        upload_dir=tmp_path / "uploads",
        api_key="test-api-key",
        github_repo="owner/repository",
        github_token="github-token",
        github_pages_domain="https://owner.github.io",
        notion_database_id="notion-database",
        notion_token="notion-token",
        telegram_token="123456:telegram-token",
        telegram_chat_id="123456",
        openai_api_key="openai-key",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client

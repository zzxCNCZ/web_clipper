from unittest.mock import AsyncMock

from fastapi.testclient import TestClient


def test_health_reports_configuration(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "configured": True}


def test_upload_requires_bearer_token(client: TestClient) -> None:
    response = client.post(
        "/upload",
        files={"singlehtmlfile": ("page.html", b"<html></html>", "text/html")},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid authentication token"


def test_upload_accepts_singlefile_field_and_cleans_temporary_file(client: TestClient) -> None:
    process_file = AsyncMock(
        return_value={
            "status": "success",
            "github_url": "https://example.com/page.html",
            "notion_url": "https://notion.so/page",
        }
    )
    client.app.state.clipper.process_file = process_file

    response = client.post(
        "/upload/",
        headers={"Authorization": "Bearer test-api-key"},
        files={"singlehtmlfile": ("page.html", b"<html></html>", "text/html")},
        data={"url": "https://example.com/article"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    uploaded_path, original_url = process_file.await_args.args
    assert original_url == "https://example.com/article"
    assert not uploaded_path.exists()


def test_upload_rejects_unsupported_files(client: TestClient) -> None:
    response = client.post(
        "/upload",
        headers={"Authorization": "Bearer test-api-key"},
        files={"singlehtmlfile": ("payload.exe", b"not html", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "File type not allowed" in response.json()["detail"]

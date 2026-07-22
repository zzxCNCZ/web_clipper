import logging
from types import SimpleNamespace

from app.services import WebClipperService, parse_filename


def test_parse_filename_recovers_singlefile_url() -> None:
    assert (
        parse_filename("cafe1234_https:$$example.com$posts$fastapi.html")
        == "https://example.com/posts/fastapi"
    )


def test_extract_title_supports_text_and_heading_formats() -> None:
    assert WebClipperService.extract_title("Title: Example\n\nBody") == "Example"
    assert WebClipperService.extract_title("# Fallback heading\n\nBody") == "Fallback heading"


def test_pipeline_logs_each_timed_stage(settings, tmp_path, monkeypatch, caplog) -> None:
    service = WebClipperService(settings)
    upload = tmp_path / "abc123_page.html"
    upload.write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr(
        service,
        "upload_to_github",
        lambda _path, *, clip_id: (upload.name, "https://example.com/page.html"),
    )
    monkeypatch.setattr(
        service,
        "html_file_to_text",
        lambda _path, *, clip_id: "Title: Example\n\nBody",
    )
    monkeypatch.setattr(
        service,
        "generate_summary_tags",
        lambda _content, *, clip_id: ("Summary", ["tag"]),
    )
    monkeypatch.setattr(service, "save_to_notion", lambda **_kwargs: "https://notion.so/page")

    with caplog.at_level(logging.INFO, logger="app.services.web_clipper"):
        service._process_file(upload, "https://source.example.com", "abc123")

    for step in ("github_publish", "local_html_extract", "title_extract", "notion_publish"):
        assert f"step={step} status=completed elapsed=" in caplog.text


def test_local_html_extraction_keeps_visible_text_and_removes_scripts(settings, tmp_path) -> None:
    service = WebClipperService(settings)
    html_path = tmp_path / "page.html"
    html_path.write_text(
        """
        <html>
          <head><title>Example Page</title><style>.hidden { color: red; }</style></head>
          <body>
            <nav>Navigation noise</nav>
            <article>
              <h1>Article title</h1>
              <p>Useful article text.</p>
              <script>const secret = "ignore me";</script>
            </article>
            <img src="data:image/png;base64,very-large-data" alt="ignored image">
          </body>
        </html>
        """,
        encoding="utf-8",
    )

    page_text = service.html_file_to_text(html_path, clip_id="abc123")

    assert page_text.startswith("Title: Example Page")
    assert "Article title" in page_text
    assert "Useful article text." in page_text
    assert "Navigation noise" not in page_text
    assert "ignore me" not in page_text
    assert "very-large-data" not in page_text


def test_github_upload_returns_pages_url_without_waiting_for_deployment(settings, tmp_path) -> None:
    class FakeRepository:
        def __init__(self) -> None:
            self.created = False

        def create_file(self, *_args, **_kwargs) -> None:
            self.created = True

    class FakeGithub:
        def __init__(self, repository) -> None:
            self.repository = repository

        def get_repo(self, _name):
            return self.repository

    service = WebClipperService(settings)
    repository = FakeRepository()
    service._github_client = FakeGithub(repository)
    html_path = tmp_path / "page.html"
    html_path.write_text("<html><body>content</body></html>", encoding="utf-8")

    filename, pages_url = service.upload_to_github(html_path, clip_id="abc123")

    assert repository.created is True
    assert filename == "page.html"
    assert pages_url == "https://owner.github.io/repository/clips/page.html"


def test_openai_summary_log_includes_duration_and_output_counts(settings, caplog) -> None:
    service = WebClipperService(settings)
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="摘要：测试摘要\n标签：Python，FastAPI")
            )
        ]
    )
    completions = SimpleNamespace(create=lambda **_kwargs: response)
    service._openai_client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    with caplog.at_level(logging.INFO, logger="app.services.web_clipper"):
        summary, tags = service.generate_summary_tags("content", clip_id="abc123")

    assert summary == "测试摘要"
    assert tags == ["Python", "FastAPI"]
    assert "[abc123] step=openai_summary status=started" in caplog.text
    assert "step=openai_summary status=completed elapsed=" in caplog.text
    assert "summary_chars=4 tag_count=2" in caplog.text

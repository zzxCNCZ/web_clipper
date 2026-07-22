import asyncio
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from bs4 import BeautifulSoup
from github import Auth, Github
from notion_client import Client as NotionClient
from openai import OpenAI
from telegram import Bot

from app.config import Settings

logger = logging.getLogger(__name__)


def parse_filename(filename: str) -> str:
    """Recover the original URL encoded by SingleFile in an upload filename."""
    name_without_extension = Path(filename).stem
    if "_" in name_without_extension:
        name_without_extension = name_without_extension.split("_", 1)[1]
    return name_without_extension.replace("$", "/")


class WebClipperService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._github_client: Github | None = None
        self._notion_client: NotionClient | None = None
        self._telegram_bot: Bot | None = None
        self._openai_client: OpenAI | None = None

    @property
    def github_client(self) -> Github:
        if self._github_client is None:
            self._github_client = Github(auth=Auth.Token(self.settings.github_token))
        return self._github_client

    @property
    def notion_client(self) -> NotionClient:
        if self._notion_client is None:
            self._notion_client = NotionClient(auth=self.settings.notion_token)
        return self._notion_client

    @property
    def telegram_bot(self) -> Bot:
        if self._telegram_bot is None:
            self._telegram_bot = Bot(token=self.settings.telegram_token)
        return self._telegram_bot

    @property
    def openai_client(self) -> OpenAI:
        if self._openai_client is None:
            self._openai_client = OpenAI(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                max_retries=self.settings.openai_max_retries,
            )
        return self._openai_client

    def validate_configuration(self) -> None:
        missing = self.settings.missing_integration_settings()
        if missing:
            raise RuntimeError(f"Missing required settings: {', '.join(missing)}")
        if "/" not in self.settings.github_repo:
            raise RuntimeError("GITHUB_REPO must use the owner/repository format")

    @contextmanager
    def _timed_step(self, clip_id: str, step: str) -> Iterator[None]:
        started_at = time.perf_counter()
        logger.info("[%s] step=%s status=started", clip_id, step)
        try:
            yield
        except Exception:
            logger.exception(
                "[%s] step=%s status=failed elapsed=%.3fs",
                clip_id,
                step,
                time.perf_counter() - started_at,
            )
            raise
        else:
            logger.info(
                "[%s] step=%s status=completed elapsed=%.3fs",
                clip_id,
                step,
                time.perf_counter() - started_at,
            )

    async def process_file(self, file_path: Path, original_url: str = "") -> dict[str, str]:
        clip_id = file_path.name.split("_", 1)[0]
        started_at = time.perf_counter()
        logger.info(
            "[%s] clip status=started file=%s size_bytes=%d source_url_provided=%s",
            clip_id,
            file_path.name,
            file_path.stat().st_size,
            bool(original_url),
        )
        try:
            with self._timed_step(clip_id, "configuration_validation"):
                self.validate_configuration()
            result = await asyncio.to_thread(self._process_file, file_path, original_url, clip_id)
            with self._timed_step(clip_id, "telegram_notification"):
                await self._send_success_notification(result)
            logger.info(
                "[%s] clip status=completed elapsed=%.3fs github_url=%s notion_url=%s",
                clip_id,
                time.perf_counter() - started_at,
                result["github_url"],
                result["notion_url"],
            )
            return {
                "status": "success",
                "github_url": result["github_url"],
                "notion_url": result["notion_url"],
            }
        except Exception as exc:
            logger.exception(
                "[%s] clip status=failed elapsed=%.3fs",
                clip_id,
                time.perf_counter() - started_at,
            )
            await self._send_failure_notification(exc, clip_id)
            raise

    def _process_file(self, file_path: Path, original_url: str, clip_id: str) -> dict[str, str]:
        with self._timed_step(clip_id, "github_publish"):
            filename, github_url = self.upload_to_github(file_path, clip_id=clip_id)

        with self._timed_step(clip_id, "local_html_extract"):
            page_text = self.html_file_to_text(file_path, clip_id=clip_id)

        with self._timed_step(clip_id, "title_extract"):
            title = self.extract_title(page_text)
        logger.info(
            "[%s] title extracted title=%r page_text_chars=%d",
            clip_id,
            title[:200],
            len(page_text),
        )

        if not original_url:
            original_url = parse_filename(filename)
            logger.info("[%s] source URL recovered from filename url=%s", clip_id, original_url)

        summary, tags = self.generate_summary_tags(page_text, clip_id=clip_id)

        with self._timed_step(clip_id, "notion_publish"):
            notion_url = self.save_to_notion(
                title=title,
                original_url=original_url,
                snapshot_url=github_url,
                summary=summary,
                tags=tags,
                created_at=time.time(),
            )
        return {
            "title": title,
            "summary": summary,
            "original_url": original_url,
            "github_url": github_url,
            "notion_url": notion_url,
        }

    def upload_to_github(self, html_path: Path, *, clip_id: str = "-") -> tuple[str, str]:
        filename = html_path.name
        content = html_path.read_text(encoding="utf-8", errors="replace")
        commit_started_at = time.perf_counter()
        logger.info(
            "[%s] step=github_commit status=started repo=%s path=clips/%s content_chars=%d",
            clip_id,
            self.settings.github_repo,
            filename,
            len(content),
        )
        repository = self.github_client.get_repo(self.settings.github_repo)
        repository.create_file(
            f"clips/{filename}",
            f"Add web clip: {filename}",
            content,
            branch="main",
        )
        logger.info(
            "[%s] step=github_commit status=completed elapsed=%.3fs",
            clip_id,
            time.perf_counter() - commit_started_at,
        )

        repository_name = self.settings.github_repo.split("/", 1)[1]
        domain = self.settings.github_pages_domain.rstrip("/")
        if not domain.startswith(("http://", "https://")):
            domain = f"https://{domain}"
        github_url = f"{domain}/{repository_name}/clips/{quote(filename)}"
        logger.info(
            "[%s] GitHub upload accepted; Pages deployment will continue asynchronously url=%s",
            clip_id,
            github_url,
        )
        return filename, github_url

    def html_file_to_text(self, html_path: Path, *, clip_id: str = "-") -> str:
        started_at = time.perf_counter()
        html = html_path.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        if not title:
            heading = soup.find(["h1", "h2", "h3", "h4", "h5", "h6"])
            title = heading.get_text(" ", strip=True) if heading else "未知标题"

        for element in soup(
            [
                "script",
                "style",
                "noscript",
                "template",
                "svg",
                "canvas",
                "iframe",
                "object",
            ]
        ):
            element.decompose()

        content_root = soup.find("article") or soup.find("main") or soup.body or soup
        lines = (
            " ".join(line.split()) for line in content_root.get_text(separator="\n").splitlines()
        )
        text = "\n".join(line for line in lines if line)
        page_text = f"Title: {title}\n\n{text}"
        logger.info(
            "[%s] local HTML extraction completed root=%s input_chars=%d output_chars=%d "
            "elapsed=%.3fs",
            clip_id,
            content_root.name or "document",
            len(html),
            len(page_text),
            time.perf_counter() - started_at,
        )
        return page_text

    @staticmethod
    def extract_title(page_text: str) -> str:
        for line in page_text.splitlines():
            if line.startswith("Title:"):
                return line.removeprefix("Title:").strip() or "未知标题"
        for line in page_text.splitlines():
            if line.startswith("# "):
                return line.removeprefix("# ").strip() or "未知标题"
        return "未知标题"

    def generate_summary_tags(self, content: str, *, clip_id: str = "-") -> tuple[str, list[str]]:
        started_at = time.perf_counter()
        logger.info(
            "[%s] step=openai_summary status=started model=%s input_chars=%d",
            clip_id,
            self.settings.openai_model,
            min(len(content), 5000),
        )
        try:
            response = self.openai_client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "请为以下网页文本内容生成简短摘要和相关标签。"
                            "英文网页也请用中文返回，并严格使用以下格式：\n"
                            "摘要：[100字以内的摘要]\n"
                            "标签：tag1，tag2，tag3，tag4，tag5\n\n"
                            f"网页内容：\n{content[:5000]}"
                        ),
                    }
                ],
            )
            result = response.choices[0].message.content or ""
            summary_line = next(
                line for line in result.splitlines() if line.strip().startswith("摘要：")
            )
            tags_line = next(
                line for line in result.splitlines() if line.strip().startswith("标签：")
            )
            summary = summary_line.split("摘要：", 1)[1].strip()
            tags = [
                tag.strip()[:20]
                for tag in tags_line.split("标签：", 1)[1].replace("，", ",").split(",")
                if tag.strip()
            ]
            summary = summary or "无法解析摘要"
            tags = tags or ["未分类"]
            logger.info(
                "[%s] step=openai_summary status=completed elapsed=%.3fs "
                "summary_chars=%d tag_count=%d",
                clip_id,
                time.perf_counter() - started_at,
                len(summary),
                len(tags),
            )
            return summary, tags
        except Exception:
            logger.exception(
                "[%s] step=openai_summary status=failed elapsed=%.3fs fallback=true",
                clip_id,
                time.perf_counter() - started_at,
            )
            return "无法生成摘要", ["未分类"]

    def save_to_notion(
        self,
        *,
        title: str,
        original_url: str,
        snapshot_url: str,
        summary: str,
        tags: list[str],
        created_at: float,
    ) -> str:
        current_time = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(created_at))
        properties = {
            "title": {"title": [{"text": {"content": title}}]},
            "type": {"select": {"name": "Post"}},
            "summary": {"rich_text": [{"text": {"content": summary}}]},
            "status": {"select": {"name": "Published"}},
            "category": {"select": {"name": "技术分享"}},
            "tags": {"multi_select": [{"name": tag} for tag in tags if tag.strip()]},
            "slug": {"rich_text": [{"text": {"content": str(int(created_at))}}]},
            "date": {"date": {"start": current_time}},
        }
        children: list[dict[str, object]] = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": summary, "link": {"url": snapshot_url}},
                        }
                    ]
                },
            },
            {
                "object": "block",
                "type": "embed",
                "embed": {"url": snapshot_url},
            },
        ]
        if original_url:
            children.append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": "原始链接",
                                    "link": {"url": original_url},
                                },
                            }
                        ]
                    },
                }
            )

        response = self.notion_client.pages.create(
            parent={"database_id": self.settings.notion_database_id},
            properties=properties,
            children=children,
        )
        return response["url"]

    async def _send_success_notification(self, result: dict[str, str]) -> None:
        message = (
            "✨ 新的网页剪藏\n\n"
            f"📑 {result['title']}\n\n"
            f"📝 {result['summary']}\n\n"
            f"🔗 原始链接：{result['original_url']}\n"
            f"📚 快照链接：{result['github_url']}"
        )
        await self.telegram_bot.send_message(
            chat_id=self.settings.telegram_chat_id,
            text=message,
        )

    async def _send_failure_notification(self, exc: Exception, clip_id: str) -> None:
        started_at = time.perf_counter()
        try:
            if self.settings.telegram_token and self.settings.telegram_chat_id:
                logger.info("[%s] step=telegram_failure_notification status=started", clip_id)
                await self.telegram_bot.send_message(
                    chat_id=self.settings.telegram_chat_id,
                    text=f"❌ 网页剪藏处理失败: {exc}",
                )
                logger.info(
                    "[%s] step=telegram_failure_notification status=completed elapsed=%.3fs",
                    clip_id,
                    time.perf_counter() - started_at,
                )
        except Exception:
            logger.exception(
                "[%s] step=telegram_failure_notification status=failed elapsed=%.3fs",
                clip_id,
                time.perf_counter() - started_at,
            )

    def close(self) -> None:
        if self._github_client is not None:
            self._github_client.close()

import logging
import time
from pathlib import Path
from fastapi import HTTPException

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {'.html', '.htm'}

async def process_file(handler, file_path: Path, original_url: str = ''):
    """
    Process uploaded file
    """
    try:
        logger.info("🔄 开始处理新的网页剪藏...")

        # 1. 上传到 GitHub Pages
        filename, github_url = handler.upload_to_github(str(file_path))
        logger.info(f"📤 GitHub 上传成功: {github_url}")

        # Github URL 转换为 Markdown
        md_content = handler.url2md(github_url)

        # 2. 获取页面标题
        title = handler.get_page_content_by_md(md_content)
        logger.info(f"📑 页面标题: {title}")

        # 如果没有提供原始 URL，则从文件名解析
        if not original_url:
            file_info = handler.parse_filename(filename)
            original_url = file_info['original_url']

        # 3. 生成摘要和标签
        summary, tags = handler.generate_summary_tags(md_content)
        logger.info(f"📝 摘要: {summary[:100]}...")
        logger.info(f"🏷️ 标签: {', '.join(tags)}")

        # 4. 保存到 Notion
        notion_url = handler.save_to_notion({
            'title': title,
            'original_url': original_url,
            'snapshot_url': github_url,
            'summary': summary,
            'tags': tags,
            'created_at': time.time()
        })
        logger.info(f"📓 Notion 保存成功")

        # 5. 发送 Telegram 通知
        notification = (
            f"✨ 新的网页剪藏\n\n"
            f"📑 {title}\n\n"
            f"📝 {summary}\n\n"
            f"🔗 原始链接：{original_url}\n"
            f"📚 快照链接：{github_url}"
        )
        await handler.send_telegram_notification(notification)

        logger.info("=" * 50)
        logger.info("✨ 网页剪藏处理完成!")
        logger.info(f"📍 原始链接: {original_url}")
        logger.info(f"🔗 GitHub预览: {github_url}")
        logger.info(f"📚 Notion笔记: {notion_url}")
        logger.info("=" * 50)

        return {
            "status": "success",
            "github_url": github_url,
            "notion_url": notion_url
        }

    except Exception as e:
        error_msg = f"❌ 处理失败: {str(e)}"
        logger.error(error_msg)
        logger.error("=" * 50)
        await handler.send_telegram_notification(error_msg)
        raise


def parse_filename(filename):
    """
    Parse URL from filename
    """
    try:
        name_without_ext = filename.rsplit('.', 1)[0]
        if '_' in name_without_ext:
            name_without_ext = name_without_ext.split('_', 1)[1]

        original_url = name_without_ext.replace('$', '/')
        logger.info(f"从文件名解析出原始URL: {original_url}")
        return {
            'original_url': original_url
        }
    except Exception as e:
        logger.error(f"解析文件名失败: {str(e)}")
        return {
            'original_url': ''
        }
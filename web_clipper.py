import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import requests
from github import Github
import openai
from notion_client import Client
import telegram
import logging
from fastapi import FastAPI, Depends, HTTPException, Request
import uvicorn
import asyncio
from concurrent.futures import ThreadPoolExecutor
import shutil
from pathlib import Path
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import secrets
from security import verify_token
from web_clipping import parse_filename
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from config import CONFIG  # 添加这行在文件开头
import re
from bs4 import BeautifulSoup  # 添加到导入部分
from fastapi.responses import JSONResponse
import html2text

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 设置 httpx 日志级别为 WARNING，隐藏请求日志
logging.getLogger("httpx").setLevel(logging.WARNING)

# 配置限制
MAX_FILE_SIZE = CONFIG.get('max_file_size', 10 * 1024 * 1024)  # 从配置中获取最大文件大小
#ALLOWED_EXTENSIONS = {'.html', '.htm'}
ALLOWED_EXTENSIONS = set(CONFIG.get('allowed_extensions', ['.html', '.htm']))
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

# 创建应用和限速器
app = FastAPI()
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

handler = None
UPLOAD_DIR = Path("uploads")

# 替换原来的 API_KEY_NAME 和 api_key_header
security = HTTPBearer()

class WebClipperHandler:
    def __init__(self, config):
        self.config = config
        self.github_client = Github(config['github_token'], timeout=60)  # 60秒超时
        self.notion_client = Client(auth=config['notion_token'])
        self.telegram_bot = telegram.Bot(token=config['telegram_token'])
        
        # 配置 OpenAI
        openai.api_key = config['openai_api_key']
        if 'openai_base_url' in config:
            openai.base_url = config['openai_base_url']
            logger.info(f"使用自定义 OpenAI API URL: {config['openai_base_url']}")

    async def process_file(self, file_path: Path, original_url: str = ''):
        """处理上传的文件"""
        try:
            logger.info("🔄 开始处理新的网页剪藏...")
            
            # 1. 上传到 GitHub Pages
            filename, github_url = self.upload_to_github(str(file_path))
            logger.info(f"📤 GitHub 上传成功: {github_url}")

            # Github URL 转换为 Markdown
            md_content = self.url2md(github_url)
            
            # 2. 获取页面标题
            title = self.get_page_content_by_md(md_content)
            logger.info(f"📑 页面标题: {title}")
            
            # 如果没有提供原始 URL，则从文件名解析
            if not original_url:
                file_info = parse_filename(filename)
                original_url = file_info['original_url']
            
            # 3. 生成摘要和标签
            summary, tags = self.generate_summary_tags(md_content)
            logger.info(f"📝 摘要: {summary[:100]}...")
            logger.info(f"🏷️ 标签: {', '.join(tags)}")
            
            # 4. 保存到 Notion
            notion_url = self.save_to_notion({
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
            await self.send_telegram_notification(notification)
            
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
            await self.send_telegram_notification(error_msg)
            raise

    def upload_to_github(self, html_path):
        """上传 HTML 文件到 GitHub Pages"""
        from github import GithubException
        filename = os.path.basename(html_path)
        
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        repo = self.github_client.get_repo(self.config['github_repo'])
        file_path = f"clips/{filename}"

        # 检查文件大小
        file_size = len(content.encode("utf-8"))
        file_size_mb = file_size / 1024 / 1024
        
        # GitHub Contents API 限制为 1MB，我们给一些缓冲空间
        if file_size_mb > 0.95:
            logger.warning(f"⚠️ 文件大小 {file_size_mb:.2f}MB，接近或超过 GitHub API 1MB 限制")
            logger.warning(f"⚠️ 建议：使用 SingleFile 压缩选项或手动精简 HTML")
        
        try:
            logger.info(f"📤 开始上传文件 ({file_size_mb:.2f}MB): {filename}")
            repo.create_file(
                file_path,
                f"Add web clip: {filename}",
                content,
                branch="main"
            )
            logger.info(f"✓ 文件上传成功")
        except GithubException as e:
            if "too large" in str(e).lower() or "exceeds" in str(e).lower():
                logger.error(f"✗ 文件过大 ({file_size_mb:.2f}MB)，超过 GitHub API 1MB 限制")
                raise Exception(f"文件大小 {file_size_mb:.2f}MB 超过限制，请压缩后重试")
            # 其他异常：可能是网络问题或文件已存在，尝试验证
            logger.warning(f"create_file 抛出异常：{e}，正在验证文件是否已上传...")
            try:
                existing_file = repo.get_contents(file_path, ref="main")
                logger.info(f"✓ 文件已存在于 GitHub，视为上传成功：{file_path}")
            except GithubException:
                logger.error(f"✗ 上传失败且文件不存在")
                raise e
        except Exception as e:
            logger.error(f"✗ 上传失败: {str(e)}")
            raise
        
        github_url = f"https://{self.config['github_pages_domain']}/{self.config['github_repo'].split('/')[1]}/clips/{filename}"
        
        # 等待 GitHub Pages 部署
        max_retries = self.config.get('github_pages_max_retries', 60)
        for attempt in range(max_retries):
            try:
                response = requests.get(github_url)
                if response.status_code == 200:
                    break
                time.sleep(5)
            except Exception:
                time.sleep(5)
        
        return filename, github_url
    
    def url2md(self, url, max_retries=30):
        """将 URL 转换为 Markdown"""
        try:
            for attempt in range(max_retries):
                try:
                    md_url = f"https://r.jina.ai/{url}"
                    response = requests.get(md_url)
                    if response.status_code == 200:
                        md_content = response.text
                        return md_content
                except Exception:
                    time.sleep(10)
        except Exception:
            md_content = self.get_page_content_by_bs(url)
            return md_content

    def generate_summary_tags(self, content):
        """使用 AI 生成摘要和标签"""
        try:
            client = openai.OpenAI(
                api_key=self.config['openai_api_key'],
                base_url=self.config.get('openai_base_url')
            )
            
            model = self.config.get('openai_model', 'gpt-3.5-turbo')
            
            response = client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": """请为以下网页(已转换为Markdown格式)内容生成简短摘要和相关标签。 
                    请严格按照以下格式返回(英文网页请以中文返回)：
                    摘要：[100字以内的摘要]
                    标签：tag1，tag2，tag3，tag4，tag5

                    网页(已转换为markdown格式)内容：
                    """ + content[:5000] + "..."
                }]
            )

            
            result = response.choices[0].message.content
            
            try:
                parts = result.split('\n')
                summary_part = next(p for p in parts if p.startswith('摘要：'))
                tags_part = next(p for p in parts if p.startswith('标签：'))
                
                summary = summary_part.replace('摘要：', '').strip()
                tags_str = tags_part.replace('标签：', '').strip()
                tags = [
                    tag.strip()[:20]
                    for tag in tags_str.replace('，', ',').split(',')
                    if tag.strip()
                ]
                
                return summary, tags
                
            except Exception as e:
                logger.error(f"解析 AI 响应失败: {str(e)}")
                return "无法解析摘要", ["未分类"]
            
        except Exception as e:
            logger.error(f"OpenAI API 调用失败: {str(e)}")
            return "无法生成摘要", ["未分类"]

    def save_to_notion(self, data):
        """保存到 Notion 数据库"""
        try:
            tags = data.get('tags', [])
            if not tags:
                tags = ["未分类"]
            
            current_time = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', 
                                       time.gmtime(data['created_at']))
            
            # properties = {
            #     "Title": {"title": [{"text": {"content": data['title']}}]},
            #     "OriginalURL": {"url": data['original_url'] if data['original_url'] else None},
            #     "SnapshotURL": {"url": data['snapshot_url']},
            #     "Summary": {"rich_text": [{"text": {"content": data['summary']}}]},
            #     "Tags": {"multi_select": [{"name": tag} for tag in tags if tag.strip()]},
            #     "Created": {"date": {"start": current_time}}
            # }
            
            # response = self.notion_client.pages.create(
            #     parent={"database_id": self.config['notion_database_id']},
            #     properties=properties
            # )

            blog_notion_properties = {
                "title": {"title": [{"text": {"content": data['title']}}]},
                "type": {"select": {"name": "Post"}},
                "summary": {"rich_text": [{"text": {"content": data['summary']}}]},
                # "status": {"select": {"name": "Draft"}},
                "status": {"select": {"name": "Published"}},
                "category": {"select": {"name": "技术分享"}},
                "tags": {"multi_select": [{"name": tag} for tag in tags if tag.strip()]},
                "slug": {"rich_text": [{"text": {"content": str(int(data['created_at']))}}]},
                "date": {"date": {"start": current_time}}
            }
            
            blog_notion_children = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text", "text": {"content": data['summary'], "link": {"url": data['snapshot_url']}}}]},
                },
                {
                    "object": "block",
                    "type": "embed",
                    "embed": {"url": data['snapshot_url']},
                },
                # 文章原始超链接
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {"type": "text", "text": {"content": "原始链接", "link": {"url": data['original_url']}}}
                        ]
                    }
                }
            ]
            cover = {
                "type": "external",
                "external": {
                    # "url": data['snapshot_url']
                    #  "url": "https://img.paulzzh.com/touhou/random"
                      "url": "https://unsplash.it/1600/900?random"
                }
            }

            # 插入到博客数据库
            blog_nation_response = self.notion_client.pages.create(
                parent={"database_id": self.config['notion_database_id']},
                properties=blog_notion_properties,
                children=blog_notion_children,
                cover=cover
            )
            logger.info(f"博客数据库插入成功: {blog_nation_response['url']}")
            
            return blog_nation_response['url']
            
        except Exception as e:
            logger.error(f"保存到 Notion 失败: {str(e)}")
            if hasattr(e, 'response'):
                logger.error(f"Notion API 响应: {e.response.text}")
            raise

    def get_page_content_by_md(self, md_content):
        """从 markdown 获取标题"""
        lines = md_content.splitlines()
        for line in lines:
            if line.startswith("Title:"):
                return line.replace("Title:", "").strip()
        return "未知标题"

    def get_page_content_by_bs(self, url, max_retries=60):
        """从部署的页面获取标题和内容"""
        for attempt in range(max_retries):
            try:
                response = requests.get(url)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # 获取标题
                    title = None
                    if soup.title:
                        title = soup.title.string
                    if not title and soup.h1:
                        title = soup.h1.get_text(strip=True)
                    if not title:
                        for tag in ['h2', 'h3', 'h4', 'h5', 'h6']:
                            if soup.find(tag):
                                title = soup.find(tag).get_text(strip=True)
                                break
                    
                    # 清理标题
                    # if title:
                    #     title = ' '.join(title.split())
                    #     title = re.sub(r'\s*[-|]\s*.*$', '', title)
                    # else:
                    #     title = os.path.basename(url)
                    
                    # 提取正文内容
                    # for script in soup(["script", "style"]):
                    #     script.decompose()
                    
                    # text = soup.get_text()
                    # lines = (line.strip() for line in text.splitlines())
                    # chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                    # text = ' '.join(chunk for chunk in chunks if chunk)

                    # 提取正文内容
                    html2markdown = html2text.HTML2Text()
                    html2markdown.ignore_links = True
                    html2markdown.ignore_images = True
                    content = html2markdown.handle(soup.prettify())
                    
                    return f"Title: {title} \n\n {content}"
                    
                time.sleep(5)
                
            except Exception:
                time.sleep(5)
        
        return os.path.basename(url), ""

    async def send_telegram_notification(self, message):
        """发送 Telegram 通知"""
        await self.telegram_bot.send_message(
            chat_id=self.config['telegram_chat_id'],
            text=message
        )

@app.on_event("startup")
async def startup_event():
    """启动时初始化"""
    global handler
    from config import CONFIG
    handler = WebClipperHandler(CONFIG)
    
    # 如果配置中没有 API key，生成一个
    if 'api_key' not in CONFIG:
        CONFIG['api_key'] = secrets.token_urlsafe(32)
        logger.info(f"Generated new API key: {CONFIG['api_key']}")

@app.post("/upload/")
@limiter.limit("10/minute", key_func=get_remote_address)
async def upload_file(
    request: Request,
    token: str = Depends(verify_token)
):
    """文件上传接口"""
    try:
        form = await request.form()
        original_url = form.get('url', '')
        
        # 获取文件内容
        file = None
        for field_name, field_value in form.items():
            if hasattr(field_value, 'filename') and hasattr(field_value, 'read'):
                file = field_value
                break
        
        if not file:
            raise HTTPException(
                status_code=400,
                detail="No file content found in form data"
            )
        
        filename = file.filename
        content = await file.read()
        
        # 验证和保存文件
        file_ext = Path(filename).suffix.lower()
        if not file_ext:
            filename += '.html'
        elif file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
            )
        
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size allowed: {MAX_FILE_SIZE/1024/1024}MB"
            )
        
        # 保存文件
        safe_filename = f"{secrets.token_hex(8)}_{filename}"
        file_path = UPLOAD_DIR / safe_filename
        
        with open(file_path, "wb") as f:
            f.write(content)
        
        try:
            result = await handler.process_file(file_path, original_url)
            return result
        finally:
            if file_path.exists():
                file_path.unlink()
                
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"上传失败: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

def start_server(host="0.0.0.0", port=8000):
    """启动服务器"""
    uvicorn.run(app, host=host, port=port) 

import logging
import time
import requests
from github import Github
from notion_client import Client
import telegram
from bs4 import BeautifulSoup
import html2text

logger = logging.getLogger(__name__)

class WebClipperHandler:
    def __init__(self, config):
        self.config = config
        self.github_client = Github(config['github_token'], timeout=300)  # 5分钟超时，适应大文件上传
        self.notion_client = Client(auth=config['notion_token'])
        self.telegram_bot = telegram.Bot(token=config['telegram_token'])
        
        openai.api_key = config['openai_api_key']
        if 'openai_base_url' in config:
            openai.base_url = config['openai_base_url']
            logger.info(f"使用自定义 OpenAI API URL: {config['openai_base_url']}")

    def upload_to_github(self, html_path):
        filename = os.path.basename(html_path)
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        from github import GithubException
        repo = self.github_client.get_repo(self.config['github_repo'])
        file_path = f"clips/{filename}"
        try:
            repo.create_file(
                file_path,
                f"Add web clip: {filename}",
                content,
                branch="main"
            )
        except Exception as e:
            # 网络超时时，GitHub 服务端可能已成功写入，验证文件是否存在
            logger.warning(f"create_file 抛出异常：{e}，正在验证文件是否已上传...")
            try:
                repo.get_contents(file_path, ref="main")
                logger.info(f"文件已存在于 GitHub，视为上传成功：{file_path}")
            except GithubException:
                # 文件确实不存在，重新抛出原始异常
                raise e
        
        github_url = f"https://{self.config['github_pages_domain']}/{self.config['github_repo'].split('/')[1]}/clips/{filename}"
        
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
        try:
            tags = data.get('tags', [])
            if not tags:
                tags = ["未分类"]
            
            current_time = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', 
                                       time.gmtime(data['created_at']))
            
            blog_notion_properties = {
                "title": {"title": [{"text": {"content": data['title']}}]},
                "type": {"select": {"name": "Post"}},
                "summary": {"rich_text": [{"text": {"content": data['summary']}}]},
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

            blog_nation_response = self.notion_client.pages.create(
                parent={"database_id": self.config['notion_database_id']},
                properties=blog_notion_properties,
                children=blog_notion_children
            )
            logger.info(f"博客数据库插入成功: {blog_nation_response['url']}")
            
            return blog_nation_response['url']
        except Exception as e:
            logger.error(f"保存到 Notion 失败: {str(e)}")
            if hasattr(e, 'response'):
                logger.error(f"Notion API 响应: {e.response.text}")
            raise

    def get_page_content_by_md(self, md_content):
        lines = md_content.splitlines()
        for line in lines:
            if line.startswith("Title:"):
                return line.replace("Title:", "").strip()
        return "未知标题"

    def get_page_content_by_bs(self, url, max_retries=60):
        for attempt in range(max_retries):
            try:
                response = requests.get(url)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
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
        await self.telegram_bot.send_message(
            chat_id=self.config['telegram_chat_id'],
            text=message
        )

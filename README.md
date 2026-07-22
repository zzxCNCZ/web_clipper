# Web Clipper

将 SingleFile 保存的网页上传到 GitHub Pages，使用 OpenAI 兼容接口生成中文摘要和标签，发布到 Notion，并通过 Telegram 发送通知。

处理链路不会等待 GitHub Pages 部署完成：GitHub API 接受文件后，服务立即从本地 HTML 提取可见文本并继续调用 AI。Pages URL 仍会保存到 Notion，并在 GitHub 后台部署完成后可访问。

## 技术栈

- Python 3.13.12
- FastAPI 应用工厂与 lifespan
- mise 管理 Python、PDM、uv 工具版本
- PDM 管理 `pyproject.toml` 项目元数据及 `pdm.lock`
- uv 创建虚拟环境、同步依赖及维护 `uv.lock`

项目结构：

```text
app/
├── controller/          # HTTP 路由和上传校验
├── schemas/             # API 请求/响应模型
├── services/            # GitHub、Notion、OpenAI、Telegram 业务流程
├── utils/               # Bearer Token 认证
├── config.py            # 环境变量配置
└── __init__.py          # FastAPI 应用工厂、lifespan、异常处理
run.py                   # 服务入口
scripts/upload_clip.py   # 命令行上传客户端
tests/                   # 自动化测试
```

## 本地开发

先安装 [mise](https://mise.jdx.dev/)，然后执行：

```bash
mise install
cp .env.example .env
mise run install
mise run dev
```

默认地址：

- API：`http://127.0.0.1:65330`
- Swagger：`http://127.0.0.1:65330/docs`
- 健康检查：`http://127.0.0.1:65330/health`

常用命令：

```bash
mise run lock      # 同时刷新 pdm.lock 和 uv.lock
mise run test      # pytest
mise run lint      # Ruff
mise run format    # Ruff formatter
mise run start     # 生产模式本地启动
```

不要直接修改锁文件；修改 `pyproject.toml` 后运行 `mise run lock`。部署和 CI 使用 `uv sync --frozen`，确保严格按 `uv.lock` 安装。

## 配置

所有运行配置均来自 `.env`，完整字段见 [.env.example](.env.example)。旧版 `config.py` 不再使用。至少需要配置：

- `API_KEY`
- `GITHUB_REPO`、`GITHUB_TOKEN`、`GITHUB_PAGES_DOMAIN`
- `NOTION_DATABASE_ID`、`NOTION_TOKEN`
- `TELEGRAM_TOKEN`、`TELEGRAM_CHAT_ID`
- `OPENAI_API_KEY`，以及可选的 `OPENAI_BASE_URL`、`OPENAI_MODEL`

`GET /health` 的 `configured` 字段可用于检查必需配置是否齐全，但不会泄露具体缺失项或密钥。

## 上传接口

接口同时兼容 `/upload` 和旧版 `/upload/`，上传文件字段名可为 SingleFile 默认的 `singlehtmlfile`，也兼容其他 multipart 文件字段名。

```bash
curl -X POST "http://127.0.0.1:65330/upload" \
  -H "Authorization: Bearer your-api-key" \
  -F "singlehtmlfile=@webpage.html" \
  -F "url=https://example.com/article"
```

也可以使用随项目提供的客户端：

```bash
uv run python scripts/upload_clip.py webpage.html \
  --key your-api-key \
  --source-url https://example.com/article
```

## Docker

```bash
cp .env.example .env
docker compose -f docker/docker-compose.yml up --build -d
```

服务监听宿主机 `65330` 端口，临时上传目录挂载到项目的 `uploads/`。

Compose 使用 `network_mode: host`。macOS/Windows 的 Docker Desktop 需要先在
Settings → Resources → Network 中启用 `Enable host networking`；host 模式下无需配置
`ports` 映射。

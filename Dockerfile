# 基于镜像基础
FROM python:3.10.12 as builder

# 设置工作目录
WORKDIR /app

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 创建虚拟环境并安装依赖
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 安装依赖，使用pip缓存
RUN pip install --no-cache-dir -r requirements.txt --index-url https://mirrors.sustech.edu.cn/pypi/web/simple

# 最终镜像
FROM python:3.10.12

WORKDIR /app

# 复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 设置 PYTHONPATH 环境变量
ENV PYTHONPATH=/app

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 65330

# 运行应用
CMD ["python", "main.py"]

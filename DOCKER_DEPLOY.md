# EduPilot Docker 一键部署指南

本项目支持通过 Docker 容器化部署，直连云端 LLM API（DashScope / OpenAI 兼容）。

## 前置要求

- Docker 24.0+
- Docker Compose v2.20+
- 阿里云 DashScope API Key（或 OpenAI API Key）

获取 DashScope API Key：https://dashscope.console.aliyun.com/

## 一键部署（3 步）

### 第 1 步：配置环境变量

复制环境变量模板并填入你的 API Key：

Linux / macOS：
cp .env.example .env

Windows (PowerShell)：
Copy-Item .env.example .env

然后编辑 .env 文件，填入你的真实 API Key：
DASHSCOPE_API_KEY=sk-your-real-api-key

### 第 2 步：构建并启动容器

docker compose up -d --build

首次启动会自动完成以下操作（约 2-3 分钟）：
- 安装 Python 依赖
- 执行数据库迁移 (migrate)
- 收集静态文件 (collectstatic)
- 构建 FAISS 向量索引（调用 Embedding API，约 1-2 分钟）
- 启动 gunicorn 服务

### 第 3 步：访问应用

浏览器打开：http://localhost:7860

## 常用运维命令

# 查看实时日志
docker compose logs -f edupilot

# 查看容器状态
docker compose ps

# 停止服务
docker compose down

# 重启服务
docker compose restart edupilot

# 重新构建（代码更新后）
docker compose up -d --build

# 进入容器调试
docker compose exec edupilot bash

## 端口说明

容器对外暴露 7860 端口。如需改为 80 端口，编辑 docker-compose.yml：
ports:
  - 80:7860

## 数据持久化

容器内以下数据需要持久化（首次部署后建议挂载 volume）：
- SQLite 数据库：/app/edupilot_project/db.sqlite3
- FAISS 索引：/app/edupilot_agent/data/langchain_faiss/
- 用户上传媒体：/app/edupilot_project/media/

可在 docker-compose.yml 的 edupilot 服务下添加 volumes：
volumes:
  - ./data/db.sqlite3:/app/edupilot_project/db.sqlite3
  - ./data/faiss:/app/edupilot_agent/data/langchain_faiss
  - ./data/media:/app/edupilot_project/media

## 切换 LLM 服务商

本项目的 LLM 调用走 OpenAI 兼容协议，可无缝切换服务商：

### 方案 A：阿里云 DashScope（默认，推荐）
DASHSCOPE_API_KEY=sk-your-key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen3-max-2026-01-23
EMBEDDING_MODEL=text-embedding-v4

### 方案 B：OpenAI 官方
OPENAI_API_KEY=sk-your-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small

### 方案 C：其他 OpenAI 兼容服务（如 DeepSeek、Moonshot 等）
LLM_API_KEY=your-key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
EMBEDDING_API_KEY=your-key
EMBEDDING_BASE_URL=https://api.deepseek.com/v1
EMBEDDING_MODEL=deepseek-embedding

## 故障排查

### 容器启动失败
查看启动日志：
docker compose logs edupilot

常见原因：
1. .env 文件缺失或 API Key 未填  ->  按 第 1 步 配置
2. 端口 7860 被占用  ->  修改 docker-compose.yml 端口映射
3. FAISS 索引构建失败  ->  检查 Embedding API Key 是否有效

### FAISS 索引构建失败
索引构建需要调用 Embedding API。如果失败，进入容器手动构建：
docker compose exec edupilot bash
cd /app
python edupilot_agent/langchain_index.py

### 前端页面样式丢失
容器内已执行 collectstatic，如仍丢失：
docker compose exec edupilot python /app/edupilot_project/manage.py collectstatic --noinput

## 架构说明

浏览器 (7860) --> gunicorn --> Django (settings_prod)
                                  |
                                  +--> FAISS 本地向量检索
                                  |
                                  +--> 云端 LLM API (DashScope/OpenAI)

- Web 框架：Django 5.x + gunicorn
- 向量检索：FAISS (langchain_community)
- LLM：云端 API，OpenAI 兼容协议
- 数据库：SQLite（生产可换 PostgreSQL）
- 静态文件：Django collectstatic
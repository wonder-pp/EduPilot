#!/bin/sh
# EduPilot 容器启动入口
# 流程：migrate -> collectstatic -> 重建 FAISS 索引(可选) -> gunicorn
# 直连云端 LLM API（DashScope / OpenAI 兼容），无需等待本地 Ollama
set -e

# Django 项目位于 /app/edupilot_project，需在该目录下运行 manage.py 与 gunicorn
cd /app/edupilot_project

echo "[edupilot] 执行数据库迁移 (migrate) ..."
python manage.py migrate --noinput

echo "[edupilot] 收集静态文件 (collectstatic) ..."
python manage.py collectstatic --noinput

# 加载脱敏种子数据：仅当存在 fixture 文件时执行 loaddata，否则跳过
# （如需启用，把 Django fixture 放到 edupilot_project/seed.json，
#   或通过环境变量 SEED_FIXTURE 指定其它路径）
SEED_FIXTURE="${SEED_FIXTURE:-seed.json}"
if [ -f "$SEED_FIXTURE" ]; then
  echo "[edupilot] 发现种子数据 $SEED_FIXTURE，执行 loaddata ..."
  python manage.py loaddata "$SEED_FIXTURE" || echo "[edupilot] loaddata 失败，已跳过（不阻断启动）。"
else
  echo "[edupilot] 未发现种子 fixture ($SEED_FIXTURE)，跳过 loaddata。"
fi

# 重建 FAISS 向量索引：首次启动或索引缺失时自动执行
# 需要 EMBEDDING_API_KEY 已配置（默认从 DASHSCOPE_API_KEY 推导）
INDEX_DIR="/app/edupilot_agent/data/langchain_faiss"
if [ ! -f "${INDEX_DIR}/index.faiss" ]; then
  echo "[edupilot] 未发现 FAISS 索引，开始构建（需访问 Embedding API）..."
  cd /app
  python edupilot_agent/langchain_index.py
  cd /app/edupilot_project
  echo "[edupilot] FAISS 索引构建完成。"
else
  echo "[edupilot] FAISS 索引已存在，跳过构建。"
fi

echo "[edupilot] 启动 gunicorn (0.0.0.0:7860) ..."
# timeout 120：云端 LLM 推理偶有延迟，留足超时
exec gunicorn \
  --bind 0.0.0.0:7860 \
  --workers 2 \
  --threads 2 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile - \
  edupilot_project.wsgi:application

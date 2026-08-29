# EduPilot Django 镜像
# 直连云端 LLM API（DashScope / OpenAI 兼容），无需本地 Ollama
# gunicorn 绑定 0.0.0.0:7860
FROM python:3.10-slim

# Python 运行时与 Django 设置
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=edupilot_project.settings_prod \
    PORT=7860

WORKDIR /app

# 系统依赖：
#   build-essential -> 个别需要编译的 Python 轮子
#   ca-certificates -> HTTPS 校验（访问云端 LLM API 必需）
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 先安装依赖，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝项目代码
COPY . .

# 构建期收集静态文件（settings_prod 中 STATIC_ROOT = edupilot_project/staticfiles）
RUN cd edupilot_project && python manage.py collectstatic --noinput

# 启动脚本：统一去掉可能存在的 CR（兼容 Windows 签出）并赋予可执行权限
RUN sed -i 's/\r$//' docker-entrypoint.sh \
    && chmod +x docker-entrypoint.sh

EXPOSE 7860

# 由 entrypoint 完成 migrate / collectstatic / 启动 gunicorn
CMD ["./docker-entrypoint.sh"]

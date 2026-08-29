#!/bin/bash
# ============================================
# EduPilot 一键部署脚本
# 适用于阿里云 ECS Ubuntu 22.04
# ============================================

set -e

echo "============================================"
echo "  EduPilot 智能教育平台 - 一键部署"
echo "============================================"

PROJECT_DIR="/home/ubuntu/EduPilot"
DEPLOY_DIR="$PROJECT_DIR/deploy"
VENV_DIR="$PROJECT_DIR/venv"
LOGS_DIR="$PROJECT_DIR/logs"

# 创建必要目录
echo "[1/8] 创建目录结构..."
mkdir -p "$LOGS_DIR"
mkdir -p "$PROJECT_DIR/edupilot_project/staticfiles"
mkdir -p "$PROJECT_DIR/edupilot_project/media"
mkdir -p "$PROJECT_DIR/edupilot_project/media/excellent_works"
mkdir -p "$PROJECT_DIR/edupilot_project/media/feedback_images"

# 安装系统依赖
echo "[2/8] 安装系统依赖..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-venv python3-pip \
    nginx git curl > /dev/null

# 创建 Python 虚拟环境
echo "[3/8] 配置 Python 环境..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip setuptools wheel -q

# 安装 Python 依赖
echo "[4/8] 安装 Python 依赖（首次可能较慢）..."
pip install -r "$PROJECT_DIR/requirements.txt" -q

# 初始化数据库
echo "[5/8] 初始化数据库..."
cd "$PROJECT_DIR/edupilot_project"

# 使用生产环境设置
DJANGO_SETTINGS_MODULE=edupilot_project.settings_prod python manage.py migrate --noinput

# 收集静态文件
DJANGO_SETTINGS_MODULE=edupilot_project.settings_prod python manage.py collectstatic --noinput -q

# 确保 staticfiles 目录存在
mkdir -p "$PROJECT_DIR/edupilot_project/staticfiles"

# 设置权限
echo "[6/8] 设置文件权限..."
sudo chown -R ubuntu:www-data "$PROJECT_DIR"
sudo chmod -R 755 "$PROJECT_DIR/edupilot_project/media"
sudo chmod -R 755 "$PROJECT_DIR/edupilot_project/staticfiles"
sudo chmod 664 "$PROJECT_DIR/edupilot_project/db.sqlite3" 2>/dev/null || true

# 配置 Gunicorn 服务
echo "[7/8] 配置服务..."

# 创建 systemd 服务
sudo tee /etc/systemd/system/edupilot.service > /dev/null << 'SERVICEEOF'
[Unit]
Description=EduPilot Django Application
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/home/ubuntu/EduPilot/edupilot_project

Environment="DJANGO_SETTINGS_MODULE=edupilot_project.settings_prod"
Environment="PYTHONUNBUFFERED=1"

ExecStart=/home/ubuntu/EduPilot/venv/bin/gunicorn -c /home/ubuntu/EduPilot/deploy/gunicorn.conf.py

Restart=always
RestartSec=5
LimitNOFILE=65536
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
SERVICEEOF

# 配置 Nginx
sudo tee /etc/nginx/sites-available/edupilot > /dev/null << 'NGINXEOF'
upstream edupilot_backend {
    server unix:///tmp/edupilot.sock fail_timeout=0;
}

server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    client_max_body_size 50M;

    access_log /home/ubuntu/EduPilot/logs/nginx_access.log;
    error_log /home/ubuntu/EduPilot/logs/nginx_error.log;

    location /static/ {
        alias /home/ubuntu/EduPilot/edupilot_project/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /home/ubuntu/EduPilot/edupilot_project/media/;
        expires 7d;
    }

    location / {
        proxy_pass http://edupilot_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
        proxy_connect_timeout 30s;
    }

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
}
NGINXEOF

# 启用站点
sudo ln -sf /etc/nginx/sites-available/edupilot /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# 启动服务
echo "[8/8] 启动服务..."
sudo systemctl daemon-reload
sudo systemctl enable edupilot
sudo systemctl restart edupilot
sudo nginx -t && sudo systemctl restart nginx

# 等待服务启动
sleep 3

# 验证
echo ""
echo "============================================"
echo " 部署完成！"
echo "============================================"
echo ""

# 检查 Gunicorn 状态
if sudo systemctl is-active --quiet edupilot; then
    echo "✅ EduPilot 服务状态: 运行中"
else
    echo "❌ EduPilot 服务启动失败，请查看日志："
    echo "   sudo journalctl -u edupilot -n 50"
fi

# 检查 Nginx 状态
if sudo systemctl is-active --quiet nginx; then
    echo "✅ Nginx 服务状态: 运行中"
else
    echo "❌ Nginx 服务启动失败，请查看日志："
    echo "   sudo journalctl -u nginx -n 50"
fi

# 获取公网 IP
PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || echo "YOUR_SERVER_IP")
echo ""
echo "🌐 访问地址: http://$PUBLIC_IP"
echo ""
echo "⚠️  重要：请确保安全组已开放 80 端口！"
echo ""
echo "常用命令："
echo "  查看服务状态: sudo systemctl status edupilot"
echo "  重启服务: sudo systemctl restart edupilot"
echo "  查看日志: sudo journalctl -u edupilot -f"
echo "  查看Nginx日志: tail -f $LOGS_DIR/nginx_error.log"
echo ""

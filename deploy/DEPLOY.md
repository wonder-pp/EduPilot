# EduPilot 生产环境部署指南

## 服务器信息
- **公网IP**: 182.92.202.78
- **SSH登录**: `ssh root@182.92.202.78` 或 `ssh ubuntu@182.92.202.78`
- **操作系统**: Ubuntu 22.04 64位

## 部署步骤

### 1. 本地打包项目
在你本地电脑上，打开终端（PowerShell/CMD），运行：
```bash
cd "c:\Users\pp101\Desktop\智能体项目"
tar -czf EduPilot-deploy.tar.gz EduPilot --exclude="EduPilot/venv" --exclude="EduPilot/__pycache__" --exclude="EduPilot/**/__pycache__" --exclude="EduPilot/*.log"
```
这会生成一个 `EduPilot-deploy.tar.gz` 文件（约 50-100MB）。

### 2. 上传到服务器
```bash
# 用 SCP 上传（输入你设置的 root 密码）
scp EduPilot-deploy.tar.gz root@182.92.202.78:/tmp/
```

### 3. 在服务器上解压和部署
```bash
# SSH 登录服务器
ssh root@182.92.202.78

# 创建 ubuntu 用户（如果不存在）
useradd -m ubuntu -s /bin/bash 2>/dev/null || true

# 解压项目
cd /home/ubuntu
tar -xzf /tmp/EduPilot-deploy.tar.gz

# 进入项目目录
cd EduPilot

# 运行一键部署脚本
chmod +x deploy/deploy.sh
./deploy/deploy.sh
```

### 4. 验证部署
打开浏览器访问：`http://182.92.202.78`

## 常用维护命令

```bash
# 查看服务状态
sudo systemctl status edupilot

# 重启服务
sudo systemctl restart edupilot

# 停止服务
sudo systemctl stop edupilot

# 查看实时日志
sudo journalctl -u edupilot -f

# 查看 Nginx 错误日志
tail -f /home/ubuntu/EduPilot/logs/nginx_error.log

# 查看 Gunicorn 错误日志
tail -f /home/ubuntu/EduPilot/logs/gunicorn_error.log
```

## 更新部署（代码修改后）
```bash
# 上传新代码后
cd /home/ubuntu/EduPilot/edupilot_project
DJANGO_SETTINGS_MODULE=edupilot_project.settings_prod python manage.py migrate --noinput
DJANGO_SETTINGS_MODULE=edupilot_project.settings_prod python manage.py collectstatic --noinput
sudo systemctl restart edupilot
```

## 安全组配置（必须）
在阿里云控制台 → 安全组，添加以下入方向规则：

| 协议类型 | 端口范围 | 授权对象 | 说明 |
|---------|---------|---------|------|
| TCP | 22/22 | 0.0.0.0/0 | SSH 远程登录 |
| TCP | 80/80 | 0.0.0.0/0 | HTTP 网页访问 |
| ICMP | -1/-1 | 0.0.0.0/0 | Ping 测试（可选） |

## 目录结构
```
/home/ubuntu/EduPilot/
├── edupilot_project/           # Django 项目
│   ├── chat/                    # 应用模块
│   ├── edupilot_project/        # Django 配置
│   │   ├── settings.py           # 开发环境
│   │   └── settings_prod.py      # 生产环境
│   ├── templates/               # 前端模板
│   ├── media/                   # 用户上传文件
│   ├── staticfiles/             # 收集的静态文件
│   └── manage.py
├── edupilot_agent/              # AI Agent 模块
├── venv/                        # Python 虚拟环境
├── deploy/                      # 部署配置
│   ├── gunicorn.conf.py
│   ├── nginx.conf
│   ├── edupilot.service
│   └── deploy.sh
├── logs/                        # 日志目录
├── .env                         # 环境变量
└── requirements.txt
```

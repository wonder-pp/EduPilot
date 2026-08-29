# EduPilot Gunicorn 配置
# 2核4G 经济型e 优化配置

import multiprocessing
import os

# 项目根目录
chdir = '/home/ubuntu/EduPilot/edupilot_project'

# WSGI 应用
wsgi_app = 'edupilot_project.wsgi:application'

# 绑定地址（通过 Nginx 转发，用 Unix Socket 性能更好）
bind = 'unix:///tmp/edupilot.sock'

# Worker 配置：3个Worker（每个约150MB），避免OOM
workers = 3

# 每个Worker线程数：2个（提升单Worker并发处理能力）
threads = 2

# Worker 超时：30秒（处理AI问答等长请求）
timeout = 30

# Worker 重启时间：600秒后自动重启（防止内存泄漏累积）
max_requests = 1000
max_requests_jitter = 50

# 日志
accesslog = '/home/ubuntu/EduPilot/logs/gunicorn_access.log'
errorlog = '/home/ubuntu/EduPilot/logs/gunicorn_error.log'
loglevel = 'info'

# 进程名称
proc_name = 'edupilot'

# 预加载（减少内存占用）
preload_app = True

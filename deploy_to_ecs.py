# -*- coding: utf-8 -*-
""" EduPilot 上传到阿里云 ECS 的一键部署脚本 """
import paramiko, tarfile, os, sys
from pathlib import Path

HOST = '182.92.202.78'
PORT = 22
USER = 'root'
PASS = 'Zhang1012'

PROJECT_ROOT = Path(__file__).parent
LOCAL_PARENT = PROJECT_ROOT.parent
LOCAL_PKG = PROJECT_ROOT / '.deploy_tmp' / 'EduPilot-deploy.tar.gz'
REMOTE_PKG = '/tmp/EduPilot-deploy.tar.gz'
REMOTE_DEPLOY_DIR = '/home/ubuntu/EduPilot'

def log(msg, tag='INFO'):
    print(f'[{tag}] {msg}')

def make_tarfile():
    LOCAL_PKG.parent.mkdir(parents=True, exist_ok=True)
    if LOCAL_PKG.exists():
        LOCAL_PKG.unlink()
    excludes = ['__pycache__', '.pyc', '.bat', 'app.log',
                '.design', '.git', '.gitignore', 'venv']
    log(f'开始打包 → {LOCAL_PKG.name}')
    with tarfile.open(LOCAL_PKG, 'w:gz') as tar:
        for root, dirs, files in os.walk(PROJECT_ROOT):
            dirs[:] = [d for d in dirs if not any(ex in d for ex in excludes)]
            for f in files:
                if any(ex in f for ex in excludes):
                    continue
                full = Path(root) / f
                arcname = str(full.relative_to(LOCAL_PARENT)).replace('\\', '/')
                tar.add(full, arcname=arcname)
    log(f'打包完成：{LOCAL_PKG.stat().st_size / (1024*1024):.1f} MB')

def connect_ssh(timeout=15):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=PASS, timeout=timeout)
    log('SSH 连接成功')
    return client

def upload_scp(client, local_path, remote_path):
    log(f'SCP 上传 {local_path.name} → {remote_path}')
    sftp = client.open_sftp()
    sftp.put(str(local_path), remote_path)
    sftp.close()
    log('上传完成')

def run_cmd(client, cmd, timeout=600):
    log(f'执行：{cmd}', tag='SSH')
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    while True:
        if stdout.channel.recv_ready():
            sys.stdout.write(stdout.channel.recv(16384).decode('utf-8','replace'))
            sys.stdout.flush()
        if stdout.channel.recv_stderr_ready():
            sys.stderr.write(stdout.channel.recv_stderr(16384).decode('utf-8','replace'))
            sys.stderr.flush()
        if stdout.channel.exit_status_ready():
            break
    return stdout.channel.recv_exit_status()

def main():
    # 1. SSH 连通测试
    client = connect_ssh()
    run_cmd(client, 'uname -a && df -h / | tail -1')
    client.close()

    # 2. 本地打包
    make_tarfile()

    # 3. SCP 上传
    client = connect_ssh()
    upload_scp(client, LOCAL_PKG, REMOTE_PKG)

    # 4. 服务器端：解压 + 装依赖 + migrate + 重启
    run_cmd(client, f'''
rm -rf {REMOTE_DEPLOY_DIR}
mkdir -p /home/ubuntu
cd /home/ubuntu
tar -xzf {REMOTE_PKG}
mkdir -p {REMOTE_DEPLOY_DIR}/logs
''')

    # 装依赖（用 venv 绝对路径，不切用户）
    run_cmd(client, '''
VENV=/home/ubuntu/EduPilot/venv
# 如果 venv 不存在就创建
if [ ! -d "$VENV" ]; then
    python3 -m venv $VENV
fi
# 配置清华源
mkdir -p /root/.pip
cat > /root/.pip/pip.conf <<'EOF'
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
trusted-host = pypi.tuna.tsinghua.edu.cn
timeout = 180
EOF
$VENV/bin/python -m pip install --upgrade pip
$VENV/bin/pip install -r /home/ubuntu/EduPilot/requirements.txt
''', timeout=1800)

    # migrate + collectstatic
    run_cmd(client, '''
cd /home/ubuntu/EduPilot/edupilot_project
VENV=/home/ubuntu/EduPilot/venv
DJANGO_SETTINGS_MODULE=edupilot_project.settings_prod $VENV/bin/python manage.py migrate --noinput
DJANGO_SETTINGS_MODULE=edupilot_project.settings_prod $VENV/bin/python manage.py collectstatic --noinput
''', timeout=300)

    # 写 gunicorn.conf.py（确保绑 80）
    run_cmd(client, '''
cat > /home/ubuntu/EduPilot/deploy/gunicorn.conf.py <<'EOF'
import multiprocessing, os
chdir = "/home/ubuntu/EduPilot/edupilot_project"
wsgi_app = "edupilot_project.wsgi:application"
bind = "0.0.0.0:80"
workers = 3
threads = 2
timeout = 120
max_requests = 1000
max_requests_jitter = 50
accesslog = "/home/ubuntu/EduPilot/logs/gunicorn_access.log"
errorlog = "/home/ubuntu/EduPilot/logs/gunicorn_error.log"
loglevel = "info"
proc_name = "edupilot"
preload_app = False
EOF
''')

    # 写 systemd 服务文件 + 重启
    run_cmd(client, '''
cat > /etc/systemd/system/edupilot.service <<'EOF'
[Unit]
Description=EduPilot Django Application
After=network.target

[Service]
User=root
Group=root
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
EOF
systemctl daemon-reload
systemctl enable edupilot
systemctl restart edupilot
sleep 10
systemctl status edupilot --no-pager -l | head -15
ss -tlnp | grep ":80"
curl -s -o /dev/null -w "HTTP %{http_code}\\n" http://127.0.0.1:80/
''', timeout=60)

    client.close()
    log(f'\n部署完成！浏览器打开：http://{HOST}', tag='DONE')

if __name__ == '__main__':
    main()

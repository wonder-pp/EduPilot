# EduPilot 智能教育规划助手

面向数据科学与智能媒体学院学生的智能问答与学业规划平台，基于真实学长学姐访谈与就业案例，提供有据可查的个性化建议。

## 快速启动

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

> Ubuntu 22.04 + Python 3.10 环境下若 `django>=6.0.0` 安装失败，请降级为 `django>=5.0,<6.0`。

### 2. 配置环境变量

在项目根目录创建 `.env` 文件：

```env
DASHSCOPE_API_KEY=your_api_key_here
LLM_MODEL=qwen3-max-2026-01-23
LLM_ENABLE_THINKING=false
```

### 3. 初始化数据库

首次运行需执行迁移：

```bash
cd edupilot_project
python manage.py migrate
```

### 4. 启动服务

```bash
cd edupilot_project
python manage.py runserver 8000
```

启动后访问：http://127.0.0.1:8000

### Docker 部署

```bash
# 1. 配置 API Key
cp .env.example .env
# 编辑 .env 填入 DASHSCOPE_API_KEY

# 2. 构建并启动
docker compose up -d --build

# 3. 浏览器访问
# http://localhost:7860
```

## 项目结构

```
EduPilot/
├── edupilot_project/      # Django 项目
│   ├── chat/              # 问答与课程应用
│   ├── edupilot_project/  # 项目配置
│   ├── templates/         # 前端模板（index.html 单页应用）
│   └── manage.py          # Django 管理脚本
├── edupilot_agent/        # 智能体核心
│   ├── agent.py           # 主流程：plan→retrieve→fuse→reason
│   ├── reasoner.py        # 推理 + 证据统计
│   ├── data/              # FAISS 索引、访谈/案例数据
│   └── ...
├── requirements.txt       # 依赖配置
└── .env                   # 环境变量
```

## 核心功能

- 智能问答：基于 RAG 检索真实学长学姐经验回答
- 证据统计：概率与数值均从检索案例代码统计得出，非模型编造
- 信息溯源：每条回答附带脱敏学长档案卡片（含薪资/绩点/录取院校等亮点）
- 保研指导：绩点、排名、科研、复试全流程建议
- 就业咨询：岗位、薪资、城市分布，结合家乡地给地域化建议
- 课程管理：大纲上传、查重、知识点提取
- 知识图谱：可视化课程知识点关联

## 技术架构

EduPilot 采用分层架构设计：

- **前端**：响应式 Web 界面，学生端 teal-green 主题，教师端 purple-blue 主题
- **Web 层**：Django 5.x + Gunicorn，提供 RESTful API
- **Agent 核心**：基于 LangChain 的 RAG（检索增强生成）引擎，包含查询规划（QueryPlanner）、经验推理（ExperienceReasoner）、证据溯源三大模块
- **LLM 基座**：支持 OpenAI 兼容 API（DashScope / OpenAI / DeepSeek 等），直连云端服务
- **向量库**：FAISS 本地向量检索，支持语义相似度匹配
- **风险评估**：内容安全审核 + 回复质量评估双层保障
- **数据层**：脱敏学长档案（姓名 / 联系方式已脱敏），SQLite + JSON 存储

<img width="100%" alt="EduPilot 系统架构图" src="https://github.com/user-attachments/assets/95d353a6-3214-45d6-a70e-e73296782911" />

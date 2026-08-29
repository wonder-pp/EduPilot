# EduPilot 贡献指南

感谢你对 EduPilot 项目的关注！本文档说明如何参与协作开发。

## 一、贡献者须知

### 1.1 行为准则

- 尊重每一位贡献者，保持专业和友善的沟通
- 提交前确保代码能在本地正常运行
- 一个 PR 只解决一个问题，不要混合多个不相关的改动

### 1.2 开发环境准备

```bash
# 1. Fork 仓库后克隆到本地
git clone https://github.com/<你的用户名>/EduPilot.git
cd EduPilot

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入你自己的 DASHSCOPE_API_KEY

# 4. 初始化数据库
cd edupilot_project
python manage.py migrate
cd ..

# 5. 启动服务
python run.py
# 访问 http://127.0.0.1:7860
```

## 二、Issue 贡献流程

### 2.1 寻找任务

前往 Issues 页面，筛选带有以下标签的 Issue：

| 标签 | 含义 | 适合人群 |
|------|------|---------|
| `good first issue` | 入门级任务，适合新手 | 首次贡献者 |
| `help wanted` | 需要帮助的任务，难度中等 | 有一定基础的开发者 |
| `documentation` | 文档相关任务 | 任何人 |
| `enhancement` | 功能增强任务 | 熟悉项目的开发者 |

### 2.2 认领任务

在目标 Issue 下方留言评论：`我想认领这个任务，预计 X 天内完成。`
维护者会回复确认并将 Issue 分配给你。

### 2.3 提交 Issue（报告 Bug 或提出建议）

如果你想报告 Bug 或提出新功能建议，请使用对应的 Issue 模板提交。

## 三、Pull Request 流程

### 3.1 分支规范

```bash
# 从 main 分支创建特性分支
git checkout main
git pull origin main
git checkout -b <分支类型>/<简短描述>

# 分支命名示例：
# fix/login-redirect-bug
# feature/add-dark-mode
# docs/fix-readme-typos
# refactor/simplify-query-planner
```

### 3.2 开发与提交

```bash
# 提交信息规范（遵循 Conventional Commits）
git commit -m "feat: 新增深色模式主题切换"
git commit -m "fix: 修复登录后跳转错误页面的问题"
git commit -m "docs: 修正 README 中的端口号描述"
git commit -m "refactor: 简化 QueryPlanner 正则匹配逻辑"
git commit -m "test: 为可信度评分模块添加单元测试"
```

提交信息前缀说明：

| 前缀 | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档变更 |
| `style` | 代码格式调整（不影响功能） |
| `refactor` | 重构（不新增功能、不修复 Bug） |
| `test` | 测试相关 |
| `chore` | 构建/工具/依赖等杂项 |

### 3.3 提交 PR

1. 将你的分支推送到 Fork 仓库
2. 在 GitHub 上向 `main` 分支发起 Pull Request
3. 按照 PR 模板填写以下内容：
   - 关联的 Issue 编号（如 `Closes #12`）
   - 改动说明（做了什么、为什么）
   - 测试方式（如何验证你的改动有效）
4. 等待维护者 Code Review

### 3.4 Code Review 流程

**这是本项目最核心的协作环节，请务必认真对待。**

1. 维护者会在 PR 上给出评审意见
2. 如果有需要修改的地方，请在**同一分支**上继续提交（不要关闭重开）
3. 每次修改后推送，PR 会自动更新，维护者会重新审查
4. 通过 Review 后，维护者执行 Merge（默认使用 Squash Merge）
5. Merge 后你的分支会被自动删除（可在设置中保留）

### 3.5 Review 标准

维护者会从以下维度审查 PR：

- **功能正确性**：改动是否解决了 Issue 描述的问题
- **代码质量**：是否符合 PEP 8（Python）/ 项目前端编码规范
- **安全性**：是否引入安全漏洞（XSS、注入、敏感信息泄露等）
- **脱敏合规**：是否泄露学长学姐真实姓名或个人信息
- **兼容性**：是否破坏已有功能
- **测试覆盖**：是否包含必要的测试

## 四、项目结构速览

```
EduPilot/
├── edupilot_project/          # Django 后端
│   ├── chat/                   # 主应用（views/models/urls）
│   ├── edupilot_project/       # Django 配置
│   └── templates/             # 前端单页应用
├── edupilot_agent/            # AI Agent 核心（RAG 流水线）
│   ├── agent.py               # 主流程：plan→retrieve→fuse→reason
│   ├── reasoner.py            # 推理 + 证据统计
│   ├── data/                  # 知识库数据 + FAISS 索引
│   └── ...
├── deploy/                    # 部署配置
├── CONTRIBUTING.md            # 本文件
└── requirements.txt           # Python 依赖
```

## 五、联系方式

- Issue 讨论：直接在对应 Issue 下评论
- 其他问题：通过 Discussions 板块发起讨论

---

感谢你的贡献！每一个 PR 都让 EduPilot 更好。

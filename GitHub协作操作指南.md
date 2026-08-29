# EduPilot GitHub 协作操作指南

> 本文档是给项目维护者（你本人）的完整操作手册，按照顺序执行即可。
> 完成后你就拥有了标准化的开源协作流程 + 可追溯的 Code Review 记录。

***

## 第一步：GitHub 账号实名激活

### 1.1 实名设置

1. 登录 GitHub → 点击右上角头像 → **Settings**
2. 左侧 **Account** → 确认邮箱已验证（显示绿色 Verified）
3. 左侧 **Profile** → 填写：
   - **Name**：你的真实姓名（中文或拼音均可，建议与学校一致）
   - **Bio**：如"数据科学与智能媒体学院 / EduPilot 项目维护者"
   - **Company / Location**：学校 / 城市
4. 左侧 **Emails** → 确保主邮箱已设为 Primary 且 Verified

### 1.2 开启二次验证（加分项）

1. Settings → **Password and authentication**
2. 启用 **Two-factor authentication**（推荐使用 Authenticator App）
3. 保存好恢复码

### 1.3 完善个人主页（让老师能认出你）

1. 点击头像 → **Your profile**
2. 上传清晰头像（或使用 Identicons）
3. 添加一行 Bio 简介
4. 在 Profile README 中（如果有）提及 EduPilot 项目

***

## 第二步：在 GitHub 上创建仓库

### 2.1 创建仓库

1. GitHub 首页 → **New repository**
2. 填写：
   - **Repository name**：`EduPilot`
   - **Description**：面向数据科学与智能媒体学院学生的智能学业规划平台，基于 RAG 检索增强生成技术
   - **Visibility**：Public（必须公开，老师才能看到）
   - **Initialize**：不要勾选 "Add a README"（项目已有）
   - **.gitignore**：不要选（项目需要自定义）
   - **License**：建议选 MIT（开源友好）
3. 点击 **Create repository**

### 2.2 本地初始化 Git 并推送

在你的项目根目录打开终端，依次执行：

```bash
# 1. 初始化 Git 仓库
git init

# 2. 先创建 .gitignore（参考 GoodFirstIssue清单 中的任务8，或直接执行下面）
# — 创建 .gitignore 后再 add —

# 3. 添加所有文件
git add .

# 4. 首次提交
git commit -m "feat: EduPilot 初始版本，包含智能问答、课程管理、知识图谱等核心功能"

# 5. 设置主分支名
git branch -M main

# 6. 关联远程仓库（替换成你的地址）
git remote add origin https://github.com/<你的用户名>/EduPilot.git

# 7. 推送到 GitHub
git push -u origin main
```

### 2.3 创建 .gitignore

在推送之前，务必先创建 `.gitignore`，防止敏感文件泄露：

```
# Python
__pycache__/
*.pyc
*.pyo
venv/
.venv/
*.egg-info/

# 敏感信息
.env

# 数据库
db.sqlite3
db.sqlite3-journal

# 日志
app.log
*.log

# 媒体文件
edupilot_project/media/

# FAISS 索引（可重建）
edupilot_agent/data/langchain_faiss/

# 部署临时文件
.deploy_tmp/

# IDE
.vscode/
.idea/
*.swp

# 系统
.DS_Store
Thumbs.db
```

> 注意：`edupilot_agent/data/*.json` 要提交（这是知识库数据），但 `langchain_faiss/` 可以忽略（随时可重建）。

### 2.4 创建 .env.example

```bash
# 复制一份脱敏的环境变量模板
cp .env .env.example
```

然后编辑 `.env.example`，把真实 Key 替换成占位符：

```env
DASHSCOPE_API_KEY=your_api_key_here
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen3-max-2026-01-23
LLM_ENABLE_THINKING=false
EMBEDDING_MODEL=text-embedding-v4
```

提交并推送：

```bash
git add .gitignore .env.example
git commit -m "chore: 添加 .gitignore 和 .env.example 模板"
git push
```

***

## 第三步：配置仓库协作设置

### 3.1 创建标签

进入仓库 → **Issues** → **Labels**，确认/创建以下标签：

| 标签名                | 颜色建议               | 说明        |
| ------------------ | ------------------ | --------- |
| `good first issue` | #7057ff（GitHub 默认） | 入门任务，适合新手 |
| `help wanted`      | #008672（GitHub 默认） | 需要帮助的任务   |
| `bug`              | #d73a4a            | Bug       |
| `enhancement`      | #a2eeef            | 功能增强      |
| `documentation`    | #0075ca            | 文档        |
| `test`             | #fbca04            | 测试相关      |
| `chore`            | #c5def5            | 杂项        |
| `data`             | #5319e7            | 数据相关      |
| `review needed`    | #fbca04            | 需要审查      |

### 3.2 设置分支保护规则（关键！）

这是"标准化审核流程"的核心保障：

1. 进入仓库 → **Settings** → **Branches**
2. 点击 **Add branch protection rule**
3. Branch name pattern：`main`
4. 勾选以下规则：
   - **Require a pull request before merging**
     - Required approvals：1（至少1人审批才能合并）
   - **Require status checks to pass**（如果有 CI 可以开启）
   - **Require conversation resolution before merging**（所有讨论必须标记已解决）
   - **Do not allow bypassing the above settings**（不允许绕过）
5. 点击 **Create** / **Save changes**

> 这样设置后，任何人（包括你自己）向 main 合并都必须走 PR 流程，不能直接 push。

### 3.3 开启 Discussions

Settings → **Features** → 勾选 **Discussions**，作为社区讨论区。

***

## 第四步：发布 Good First Issue

### 4.1 批量创建 Issue

打开 `GoodFirstIssue清单.md`，里面已经准备好了 10 个具体任务。

**发布策略**：

- 首批先发 3\~4 个（建议选任务 1、3、8，最简单最具体）
- 每个 Issue 打上 `good first issue` + `help wanted` 标签
- Issue 内容直接从清单中复制标题和描述

### 4.2 具体操作步骤

1. 仓库 → **Issues** → **New issue**
2. 选择模板（Bug 报告 / 功能建议）
3. 填写标题和内容（从 GoodFirstIssue清单.md 复制）
4. 右侧 Labels → 选择 `good first issue`、`help wanted`
5. 点击 **Submit new issue**
6. 重复发布其他 Issue

### 4.3 Issue 示例（以任务1为例）

**标题**：

```
docs: README 中启动端口描述前后矛盾
```

**正文**：

```markdown
## 问题描述

README 中快速启动部分写道"默认端口 7860"，但方式二 `python manage.py runserver 8000` 使用的是 8000 端口，两者不一致，容易让新用户困惑。

## 期望修复

在方式二下方补充说明端口差异，或统一说明端口可由 `PORT` 环境变量控制。

## 涉及文件

- `README.md`

## 难度

入门级，只需修改 Markdown 文本。

---

如果有人想认领这个任务，请在下方评论 `我来认领`，我会分配给你。
```

***

## 第五步：Code Review 标准流程（最重要）

这是老师最看重的环节——**有人提交 PR 时，你必须作为 Maintainer 进行专业评审**。

### 5.1 当收到 PR 时

1. GitHub 会发邮件通知你，也可以在仓库 **Pull requests** 页面看到
2. 点击 PR 标题进入详情页
3. 先看 PR 描述是否完整（关联了哪个 Issue、改了什么、怎么测试的）
4. 切换到 **Files changed** 标签页，逐文件审查代码

### 5.2 Code Review 检查清单

对照以下清单逐项检查：

**功能层面**：

- [ ] PR 是否真正解决了关联的 Issue
- [ ] 改动是否引入了新的问题
- [ ] 是否有明显的逻辑错误

**代码质量**：

- [ ] 变量/函数命名是否清晰
- [ ] 是否有冗余或重复代码
- [ ] 是否符合项目现有代码风格

**安全性**：

- [ ] 是否引入了 SQL 注入、XSS 等漏洞
- [ ] 是否硬编码了密码、API Key 等敏感信息
- [ ] 文件上传是否有类型/大小校验

**脱敏合规**（EduPilot 特有）：

- [ ] 代码或数据中是否泄露学长学姐真实姓名
- [ ] 提交的 JSON 数据是否已脱敏
- [ ] 日志输出中是否打印了敏感信息

**文档**：

- [ ] 改动是否需要同步更新文档
- [ ] 新增函数是否有必要的注释

### 5.3 如何在 GitHub 上留下专业评审意见

**方式1：行内评论（推荐，最专业）**

1. 在 Files changed 页面，鼠标悬停到某行代码
2. 出现蓝色 `+` 图标，点击它
3. 写下你的评审意见
4. 点击 **Start a review**（不要点 Add single comment，这样多条意见汇总为一次 Review）
5. 继续在其他行添加评论
6. 全部添加完后，点击页面顶部 **Review changes**

**评审意见的写法参考**：

好的评审意见（具体、可操作）：

```
这里使用了 `eval()` 解析用户输入，存在代码注入风险。建议改用 `json.loads()` 并加 try-except 处理异常。
```

```
这个函数名 `process_data` 太笼统了，建议改为 `compute_confidence_score`，更清晰地表达意图。
```

```
这里提交的 employment_cases.json 中第 3 条记录的 person_id 字段还是真实姓名"张三"，需要改为"某师兄"格式进行脱敏。请修正后重新提交。
```

不太好的评审意见（模糊、无建设性）：

```
代码写得不好，改一下。
```

```
这样不行。
```

**方式2：提交 Review 结论**

在 Review changes 弹窗中，选择一种结论：

| 选项                  | 含义        | 使用场景             |
| ------------------- | --------- | ---------------- |
| **Comment**         | 仅评论，不审批通过 | 有小问题但不阻塞，可以继续讨论  |
| **Approve**         | 审批通过      | 代码没有问题，可以合并      |
| **Request changes** | 要求修改      | 有需要修改的问题，必须改完再合并 |

### 5.4 标准评审流程（完整走一遍）

以一个真实场景为例——有人提交了"补充家乡知识数据"的 PR：

```
第一步：查看 PR 描述
→ 确认关联了 Issue #3，描述了新增 5 个城市的数据

第二步：查看 Files changed
→ 发现 hometown_knowledge.json 新增了长沙、合肥等城市
→ 逐条检查数据格式是否一致
→ 发现长沙的 salary_range 字段写的是 "8-15K" 而非现有的 "8K-15K" 格式
→ 在该行添加评论："salary_range 格式建议与现有数据保持一致，使用 '8K-15K' 而非 '8-15K'"

第三步：检查脱敏
→ 确认 tech_companies 字段中没有个人姓名
→ 确认数据为公开信息，无隐私问题

第四步：提交 Review
→ 选择 "Request changes"
→ 总结："数据格式基本正确，但 salary_range 字段格式需要统一，请修正后重新提交"

第五步：等待贡献者修改
→ 贡献者修改后推送，PR 自动更新

第六步：重新审查
→ 确认格式已修正
→ 选择 "Approve"

第七步：合并
→ 点击 "Squash and merge"
→ 合并后 Issue #3 自动关闭（因为 PR 描述中写了 Closes #3）
```

### 5.5 Merge 策略选择

在 Settings → **General** → **Pull Requests** → Merge Button 中：

建议勾选：

- ✅ **Allow squash merging**（推荐默认，将多个 commit 压成一个）
- ❌ **Allow merge committing**（不需要，容易产生无意义的 merge commit）
- ❌ **Allow rebase merging**（新手容易搞混，不推荐）

设置 **Default merge method** 为 **Squash**。

***

## 第六步：留存评审记录作为佐证材料

### 6.1 哪些记录需要保存

| 记录类型                | 在哪里                                  | 保存方式        |
| ------------------- | ------------------------------------ | ----------- |
| Issue 列表            | 仓库 Issues 页面                         | 截图 + URL 链接 |
| Good First Issue 任务 | 带标签的 Issue                           | 截图 + URL 链接 |
| Pull Request 列表     | 仓库 Pull requests 页面（Closed）          | 截图 + URL 链接 |
| Code Review 评论      | PR 的 Files changed / Conversation 页面 | 截图 + URL 链接 |
| Review 审批记录         | PR 的 Reviews 部分                      | 截图          |
| Merge 记录            | PR 底部 merged 标签                      | 截图 + URL    |

### 6.2 如何整理佐证材料

建议创建一个文档，整理为如下格式：

```
## 贡献佐证材料

### 1. Good First Issue 发布记录

| Issue # | 标题 | 标签 | 链接 |
|---------|------|------|------|
| #1 | docs: README 端口描述不一致 | good first issue, documentation | https://github.com/xxx/EduPilot/issues/1 |
| #2 | feat: 前端移动端适配 | good first issue, enhancement | https://github.com/xxx/EduPilot/issues/2 |
| ... | ... | ... | ... |

### 2. 代表性 Pull Request / Code Review 记录

#### PR #1: 补充家乡知识数据
- PR 链接：https://github.com/xxx/EduPilot/pull/1
- 关联 Issue：#3
- 贡献者：xxx
- Review 意见摘要：指出 salary_range 格式不一致，要求修正后合并
- Review 链接：https://github.com/xxx/EduPilot/pull/1#pullrequestreview-xxx
- 最终状态：已合并（Squash Merge）

#### PR #2: ...
- ...

### 3. 作为 Maintainer 的代码评审记录

- 共评审 N 个 PR
- 提出修改意见 X 条
- 全部要求修改后再合并，无一例外直接合并
```

### 6.3 截图保存建议

1. 每完成一次 PR 评审 + 合并，立即截图保存
2. 截图内容包括：
   - PR 标题和状态（Open/Merged）
   - Files changed 中的行内评论
   - Review 结论（Request changes / Approve）
   - 最终 Merge 记录
3. 建议按 `PR编号_简要描述_日期` 命名，如 `PR3_家乡知识数据_20260829.png`

***

## 第七步：持续运营建议

### 7.1 定期发布新 Issue

- 每解决一批 Issue，及时发布新的
- 从 GoodFirstIssue清单.md 中挑选，也可以根据项目需要新增
- 保持仓库始终有 3\~5 个 open 的 good first issue

### 7.2 回复及时性

- 收到 PR 后 24\~48 小时内给出初步 Review 意见
- 贡献者修改后，尽快复审
- 不要让 PR 悬而未决太久

### 7.3 让协作看起来真实

老师要看到的是**真实有人提交 PR、你真实做了 Review**。所以：

- 可以邀请同学来认领 Issue 并提交 PR
- 可以自己从另一个分支/账号提交一些简单的 PR 来走通流程
- 但 Review 意见必须真实、专业、有技术含量

***

## 快速检查清单

完成以上所有步骤后，用这个清单确认：

- [ ] GitHub 账号已实名设置
- [ ] 仓库已创建并推送代码
- [ ] `.gitignore` 已配置，敏感文件未泄露
- [ ] `.env.example` 已创建
- [ ] CONTRIBUTING.md 已推送
- [ ] Issue 模板已生效（.github/ISSUE\_TEMPLATE/）
- [ ] PR 模板已生效（.github/PULL\_REQUEST\_TEMPLATE.md）
- [ ] 标签已创建（good first issue、help wanted 等）
- [ ] 分支保护规则已设置（main 分支必须 PR 才能 merge）
- [ ] Squash Merge 已设为默认
- [ ] 已发布 3\~5 个 Good First Issue
- [ ] 已收到至少 1 个 PR 并完成 Code Review
- [ ] 评审记录已截图保存
- [ ] 佐证材料已整理成文档


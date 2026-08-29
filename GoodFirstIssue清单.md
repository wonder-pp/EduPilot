# EduPilot Good First Issue 任务清单

> 以下任务均可直接在 GitHub Issues 上发布，建议每次发 3~5 个，不要一次全发。
> 发布后打上 `good first issue` 和 `help wanted` 标签。

---

## 任务1：修复 README 中端口描述不一致问题

**标签**：`good first issue` `documentation`

**标题**：docs: README 中启动端口描述前后矛盾

**描述**：
README 中快速启动部分写道"默认端口 7860"，但方式二 `python manage.py runserver 8000` 使用的是 8000 端口，两者不一致，容易让新用户困惑。

**具体改动**：
1. 在方式二下方补充说明：`此方式端口为 8000，与一键启动的 7860 不同`
2. 或者统一说明端口可由 `PORT` 环境变量控制

**文件**：`README.md`

**难度**：入门级

---

## 任务2：补充前端移动端响应式适配

**标签**：`good first issue` `enhancement`

**标题**：feat: 前端移动端响应式适配优化

**描述**：
当前前端页面（`templates/index.html`）在手机浏览器上部分布局溢出，主要问题：
1. 导航栏在窄屏下元素重叠
2. 问答输入框在手机上过窄
3. 证据溯源卡片在小屏下文字溢出

**具体改动**：
1. 在 `<meta viewport>` 已有的基础上，添加媒体查询断点（768px / 480px）
2. 导航栏在移动端切换为汉堡菜单或折叠布局
3. 卡片在小屏下改为单列布局

**文件**：`edupilot_project/templates/index.html`（CSS 部分）

**难度**：入门级，需了解基础 CSS 媒体查询

---

## 任务3：补充家乡地域知识数据（新增 5 个城市）

**标签**：`good first issue` `help wanted` `data`

**标题**：data: 补充家乡知识库，新增 5 个城市的产业/薪资/岗位数据

**描述**：
`hometown_knowledge.json` 目前覆盖的城市有限，需要补充更多城市的就业地域化数据，帮助学生获得更全面的地域就业建议。

**具体改动**：
1. 查看现有 `hometown_knowledge.json` 的数据结构（每个城市包含 main_industries、tech_companies、salary_range、positions_for_data_science、positions_for_ai_science 等字段）
2. 按照相同格式，补充以下 5 个城市的数据：长沙、合肥、厦门、东莞、珠海
3. 数据来源可参考各城市统计局公开数据或招聘平台公开信息
4. 所有数据必须脱敏，不含任何个人隐私信息

**文件**：`edupilot_project/hometown_knowledge.json`

**难度**：入门级，需了解 JSON 格式

---

## 任务4：为可信度评分模块添加单元测试

**标签**：`good first issue` `help wanted` `test`

**标题**：test: 为可信度评分模块添加单元测试

**描述**：
`edupilot_project/chat/views.py` 中的可信度评分逻辑（`ask` 函数内）目前没有测试覆盖。需要为该算法补充基础测试。

**具体改动**：
1. 在 `edupilot_project/chat/tests.py` 中添加测试类
2. 测试场景至少覆盖：
   - 0 条证据时可信度返回 10
   - 5 条高质量证据（普查+深度）时可信度较高
   - 全部为公众号数据源时可信度有扣分
   - 证据分数离散度大时一致性惩罚生效
3. 由于评分逻辑内嵌在 `ask` 视图中，建议先重构提取为独立函数 `compute_confidence(evidence_list)` 再测试

**文件**：`edupilot_project/chat/tests.py`、`edupilot_project/chat/views.py`

**难度**：中等，需了解 Django 测试和 Python unittest

---

## 任务5：修正 QueryPlanner 中注释错别字

**标签**：`good first issue` `documentation`

**标题**：docs: 修正 query_planner.py 中注释拼写错误

**描述**：
`edupilot_agent/query_planner.py` 中部分英文注释存在拼写错误和语法问题。

**具体改动**：
1. 检查所有 docstring 和注释
2. 修正拼写错误（如 "fallback" 有处写成其他形式）
3. 保持注释内容不变，仅修正拼写

**文件**：`edupilot_agent/query_planner.py`

**难度**：入门级

---

## 任务6：前端 AI 回答区域添加加载动画

**标签**：`good first issue` `enhancement`

**标题**：feat: AI 回答区域增加加载动画，提升用户体验

**描述**：
当前用户点击"发送"后，在 AI 回答返回之前页面没有明显的加载反馈，用户不知道是否在处理中。

**具体改动**：
1. 在问答输入区域添加发送后的 loading 状态
2. 显示一个简单的加载动画（CSS spinner 或文字"正在思考中..."）
3. AI 回答返回后移除加载状态，展示回答内容
4. 加载动画样式与现有主题风格一致（teal-green / indigo-purple）

**文件**：`edupilot_project/templates/index.html`（JS + CSS）

**难度**：入门级，需了解 JavaScript DOM 操作

---

## 任务7：补充就业案例数据集（新增 10 条脱敏记录）

**标签**：`good first issue` `help wanted` `data`

**标题**：data: 补充就业案例数据集，新增 10 条脱敏记录

**描述**：
`edupilot_agent/data/employment_cases.json` 当前有 93 条记录，需要补充更多就业案例以提升 RAG 检索的覆盖面和回答质量。

**具体改动**：
1. 查看现有 `employment_cases.json` 的数据结构
2. 按相同格式新增 10 条就业案例记录
3. 覆盖更多行业方向：金融科技、新能源汽车、芯片半导体、医疗健康等
4. 所有姓名必须脱敏（使用"某师兄""某师姐"格式），薪资为区间范围
5. 新增后需重新构建 FAISS 索引：`python edupilot_agent/langchain_index.py`

**文件**：`edupilot_agent/data/employment_cases.json`

**难度**：入门级，需了解 JSON 和数据脱敏概念

---

## 任务8：添加 .gitignore 文件

**标签**：`good first issue` `chore`

**标题**：chore: 添加标准 .gitignore 文件

**描述**：
项目根目录目前缺少 `.gitignore`，敏感文件（`.env`、`db.sqlite3`、`__pycache__`）可能被误提交。

**具体改动**：
1. 创建 `.gitignore` 文件
2. 忽略以下内容：
   - `__pycache__/`、`*.pyc`
   - `.env`（敏感信息）
   - `db.sqlite3`（开发数据库）
   - `app.log`（日志文件）
   - `venv/`、`.venv/`
   - `media/`（用户上传文件）
   - `*.egg-info/`
   - `edupilot_agent/data/langchain_faiss/`（FAISS 索引可重建）
   - IDE 配置：`.vscode/`、`.idea/`
   - 系统：`.DS_Store`、`Thumbs.db`
3. 但保留 `edupilot_agent/data/*.json`（这些是知识库数据，需要版本管理）

**文件**：`.gitignore`（新建）

**难度**：入门级

---

## 任务9：为 LLM Client 添加连接状态检测接口

**标签**：`help wanted` `enhancement`

**标题**：feat: 添加 LLM 连接状态检测接口，便于运维排查

**描述**：
当前 `JsonLLMClient` 的 `status()` 方法返回状态字典，但没有独立的 HTTP 接口供运维调用查看。

**具体改动**：
1. 在 `edupilot_project/chat/views.py` 中添加 `llm_status` 视图函数
2. 路由：`GET /ai/llm_status`
3. 返回 LLM 是否可用、模型名称、base_url、是否有 API Key（不返回 Key 本身）
4. 仅限管理员角色访问
5. 在 `edupilot_project/chat/urls.py` 中注册路由

**文件**：`edupilot_project/chat/views.py`、`edupilot_project/chat/urls.py`

**难度**：中等，需了解 Django 视图和权限控制

---

## 任务10：前端证据卡片添加复制按钮

**标签**：`good first issue` `enhancement`

**标题**：feat: 证据溯源卡片增加一键复制功能

**描述**：
AI 回答右侧的证据溯源卡片展示了学长学姐的脱敏信息，学生可能需要复制某条证据内容用于笔记。目前需要手动选中文本复制，体验不佳。

**具体改动**：
1. 在每张证据卡片右上角添加"复制"图标按钮
2. 点击后复制该卡片的文本内容到剪贴板
3. 复制成功后显示"已复制"提示（2秒后消失）
4. 使用 Clipboard API 或 fallback 方案

**文件**：`edupilot_project/templates/index.html`（JS + CSS）

**难度**：入门级，需了解 JavaScript Clipboard API

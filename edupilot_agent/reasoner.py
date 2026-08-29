from __future__ import annotations

from collections import Counter, defaultdict
import json
import re
import sys
from typing import Any, Dict, List

from edupilot_agent.llm_client import JsonLLMClient
from edupilot_agent.schemas import AgentResponse, FusedEvidence, RetrievedChunk, StructuredQuery


class ExperienceReasoner:
    """
    Fuse retrieved experience chunks into a structured suggestion.

    This demo uses deterministic rules so it stays runnable without an external
    LLM. In production, you can replace `reason` with an actual model call that
    consumes the same evidence bundle.
    """

    def __init__(self, llm: JsonLLMClient | None = None):
        self.llm = llm or JsonLLMClient(enabled=False)

    # ==================== 证据脱敏 ====================

    def _desensitize_person_name(self, person_id: str, idx: int = 0) -> str:
        """将 person_id 转为中性案例标识符（如 '常佳毅' → '案例A'）。
        正文不引用任何称呼，仅用于溯源卡片/证据内部替换真实姓名。"""
        if not person_id:
            return f"案例{chr(ord('A') + idx)}"
        # 用 A/B/C... 标识，超过26则用 A1/A2...
        if idx < 26:
            tag = chr(ord('A') + idx)
        else:
            tag = f"A{idx - 25}"
        return f"案例{tag}"

    def _build_name_mapping(self, chunks: List[RetrievedChunk]) -> Dict[str, str]:
        """从证据chunks构建 真实姓名→中性案例标识符 的映射。"""
        mapping: Dict[str, str] = {}
        idx = 0
        for chunk in chunks:
            pid = chunk.content.get("person_id", "")
            if pid and pid not in mapping:
                mapping[pid] = self._desensitize_person_name(pid, idx)
                idx += 1
        return mapping

    def _desensitize_text(self, text: str, name_mapping: Dict[str, str]) -> str:
        """在文本中替换所有真实姓名为脱敏称呼"""
        if not text or not name_mapping:
            return text
        result = text
        # 按姓名长度降序替换，避免短姓名误匹配
        for real_name in sorted(name_mapping.keys(), key=len, reverse=True):
            short_name = real_name.split("_")[0].strip()
            desensitized = name_mapping[real_name]
            if short_name and len(short_name) >= 2:
                result = result.replace(short_name, desensitized)
        return result

    def _desensitize_evidence_dict(self, fused_dict: dict, name_mapping: Dict[str, str]) -> dict:
        """递归脱敏证据字典中的所有文本"""
        if not name_mapping:
            return fused_dict
        result = {}
        for key, value in fused_dict.items():
            if isinstance(value, str):
                result[key] = self._desensitize_text(value, name_mapping)
            elif isinstance(value, list):
                result[key] = [
                    self._desensitize_text(item, name_mapping) if isinstance(item, str)
                    else self._desensitize_evidence_dict(item, name_mapping) if isinstance(item, dict)
                    else item
                    for item in value
                ]
            elif isinstance(value, dict):
                result[key] = self._desensitize_evidence_dict(value, name_mapping)
            else:
                result[key] = value
        return result

    def reason(self, user_query: StructuredQuery, chunks: List[RetrievedChunk]) -> AgentResponse:
        grouped = self._group_by_type(chunks)
        fused = FusedEvidence(
            profile=[item.content.get("content", "") for item in grouped.get("profile", [])[:3]],
            timeline=[item.content.get("content", "") for item in grouped.get("timeline", [])[:4]],
            decisions=[item.content.get("content", "") for item in grouped.get("decision", [])[:4]],
            advice=[item.content.get("content", "") for item in grouped.get("advice", [])[:5]],
            methods=[item.content.get("content", "") for item in grouped.get("method", [])[:4]],
            reflections=[item.content.get("content", "") for item in grouped.get("reflection", [])[:3]],
            raw_evidence=[item.to_dict() for item in chunks],
        )
        return self.reason_with_fusion(user_query, fused, chunks)

    def reason_with_fusion(
        self,
        user_query: StructuredQuery,
        fused: FusedEvidence,
        chunks: List[RetrievedChunk],
    ) -> AgentResponse:
        # 只使用LLM回答，不回退到规则引擎
        if not self.llm.enabled:
            raise RuntimeError("LLM is not enabled. Please enable LLM to use this feature.")
        
        if not self.llm.available:
            raise RuntimeError("LLM is not available. Please check your API key and network connection.")
        
        llm_response = self._reason_with_llm_natural(user_query, fused, chunks)
        if llm_response:
            return llm_response
        
        raise RuntimeError("LLM returned empty response")

    def _reason_with_llm_natural(
        self,
        user_query: StructuredQuery,
        fused: FusedEvidence,
        chunks: List[RetrievedChunk],
    ) -> AgentResponse | None:
        try:
            raw_input = user_query.user_profile.get('raw_input', '')
            major = user_query.user_profile.get('major', '')
            grade = user_query.user_profile.get('grade', '')
            goal = user_query.goal or ''
            # 纯科研入门：目标修正，避免输出保研去向统计/套用保研规划
            if re.search(r'科研.*(怎么|如何|怎样|从哪|入门|开始|起步)', raw_input) and not re.search(r'保研|推免', raw_input):
                goal = '科研入门'
            hometown = user_query.user_profile.get('hometown', '')

            # === 意图指令：明确告诉LLM用户在问什么，防止跑题 ===
            is_emp = self._is_employment_question(user_query)
            is_grad = self._is_gradschool_question(user_query)
            # 纯科研入门修正
            if re.search(r'科研.*(怎么|如何|怎样|从哪|入门|开始|起步)', raw_input) and not re.search(r'保研|推免|夏令营|考研|读研', raw_input):
                is_grad = False
            # 综合性方向选择问题修正：用户问"往哪个方向努力/应该选哪条路/怎么规划"等，
            # 即使问题含"绩点"等关键词，也不应锁定单一升学/就业意图，应给出多方向对比建议
            is_direction = self._is_direction_question(raw_input)
            if is_direction:
                is_emp = False
                is_grad = False
            if is_emp and not is_grad:
                intent_directive = (
                    "【意图锁定 — 必须严格遵守】\n"
                    "用户当前问题属于【就业/职业发展】类。回答必须紧扣用户问题本身（如工作地点选择、岗位方向、薪资水平等），"
                    "绝对禁止在回答中谈论保研、考研、推免、夏令营、绩点排名等升学相关内容，"
                    "除非用户问题明确涉及升学。如果检索到的证据与用户问题不相关（如保研案例但用户问就业），"
                    "直接忽略该证据，基于证据统计数据和你自己的专业知识回答用户的问题。\n"
                )
            elif is_grad and not is_emp:
                intent_directive = (
                    "【意图锁定 — 必须严格遵守】\n"
                    "用户当前问题属于【保研/考研/升学】类。回答必须紧扣用户问题本身（如保研准备、绩点要求、院校选择等），"
                    "绝对禁止在回答中谈论就业岗位、薪资、求职等就业相关内容，"
                    "除非用户问题明确涉及就业。如果检索到的证据与用户问题不相关（如就业案例但用户问保研），"
                    "直接忽略该证据，基于证据统计数据和你自己的专业知识回答用户的问题。\n"
                )
            elif is_direction:
                intent_directive = (
                    "【意图锁定 — 最高优先级，高于system_prompt所有规则】\n"
                    "用户当前问题属于【综合性方向选择/规划】类。回答必须覆盖3个不同方向对比，禁止3点都讲保研。\n"
                    "输出格式要求：\n"
                    "1. 第一句必须直接给出主推方向（结合用户绩点和背景，推荐保研/就业/考研中最适合的一条作为主推），并提一句备选兜底方向。\n"
                    "2. 然后用3个分点展开，每点用加粗序号标题独占一行（格式'**N. 方向（定位）**'），3个方向必须分别是保研、就业、考研，不得合并或省略：\n"
                    "   - **1. 保研（主推/备选）**：门槛（绩点/排名/英语）、时间节点、核心准备\n"
                    "   - **2. 直接就业（主推/备选）**：岗位方向、薪资区间、与保研的差异、适合人群\n"
                    "   - **3. 考研（兜底）**：院校选择、时间投入、与保研的差异、何时转向\n"
                    "3. 每点内容1-2句，基于用户实际背景和证据统计数据给出具体建议，数字取自证据统计不要编造。\n"
                    "4. 禁止在正文出现'案例A''案例B'等标识符，禁止出现'师兄/师姐'称呼。\n"
                )
            else:
                intent_directive = (
                    "【意图锁定 — 必须严格遵守】\n"
                    "回答必须紧扣用户问题本身，不要偏题。如果检索到的证据与用户问题不相关，"
                    "直接忽略该证据，基于证据统计数据和你自己的专业知识回答用户的问题。\n"
                )

            background_parts = []
            if major:
                background_parts.append(f"专业={major}")
            if grade:
                background_parts.append(f"年级={grade}")
            if goal:
                background_parts.append(f"目标={goal}")
            if hometown:
                background_parts.append(f"家乡={hometown}")
            background = ", ".join(background_parts) if background_parts else "用户暂未提供个人背景信息"
            
            # === 证据统计：从检索到的真实chunks中代码统计，零LLM调用 ===
            stats = self._compute_evidence_stats(chunks, user_query)
            stats_text = self._format_stats(stats)

            system_prompt = (
                "你是一位经验丰富的学长/学姐，也是一位专业的职业发展导师。"
                "请根据用户的问题和提供的证据，用自然、亲切的语气回答。\n\n"
                "【三种证据来源及使用规则 — 必须严格遵守】\n"
                "证据分为三类，来源不同可信度不同，用途完全不同：\n"
                "1. 📊 grade_census（年级普查数据）：最新一届全体同学的结构化档案，样本量最大、最客观。\n"
                "   - 用途：只用于开头交代统计背景和输出精确概率/分布数字（如'你们专业65人里，保研的有X人，占比Y%'）。\n"
                "   - 绝对禁止：提到任何一个普查同学的姓名、不能在溯源卡片上出现普查的人。\n"
                "2. 🔍 deep_interview（深度访谈）：往届学长学姐的一对一真实访谈，有精确绩点、排名、录取学校、具体时间点。\n"
                "   - 用途：用于支撑具体可执行建议，必须能举出'参考C某某的做法'这种，引用精确数字（绩点3.88，排名1/63等）。\n"
                "   - 溯源卡片上展示的学长，必须来自deep_interview或employment数据。\n"
                "3. 📱 public_interview（公众号访谈）+ advice类：公开文章，经过编辑加工，信息较泛。\n"
                "   - 用途：只用于定性佐证句式'不少学长学姐也在公众号中强调过...'，不得从中提取具体数字当权威引用。\n"
                "回答的结构应当自然分层：先用普查交代概率/背景 → 再用深度访谈给出具体建议和案例 → 最后用公众号补一句通用经验。\n\n"
                "【用户背景信息规则 — 必须严格遵守】\n"
                "1. 如果用户在问题中明确说了自己的年级/专业/家乡等信息，可以基于这些信息回答\n"
                "2. 如果用户没有说任何个人信息，绝对禁止自行推断用户的年级、专业或学习阶段\n"
                "3. 禁止出现'你现在是大三学生''你是2024级'这类未经用户确认的判断\n"
                "4. 如果需要知道用户年级才能给出精准建议，可以反问用户'你是几级的学生？'\n\n"
                "【特别重要：多问题处理规则】\n"
                "用户的问题可能包含多个子问题，请务必：\n"
                "1. 仔细分析用户的问题，识别出所有子问题\n"
                "2. 对每个子问题都给出完整回答，按逻辑顺序逐一回答\n"
                "3. 如果用户的问题涉及多个主题（如同时问就业和保研），请分别回答每个主题\n\n"
                "【概率依据规范 — 必须严格遵守】\n"
                "1. 所有概率、数值判断必须基于下方「证据统计数据」部分的真实统计结果，不得自行编造任何数字\n"
                "2. 给出概率时必须标注样本量，格式：「基于N条检索案例，XX概率约为YY%」；仅当【用户背景】中明确给出了具体专业/年级/家乡/目标等匹配维度时，才可以改为「基于N条匹配（维度）的相关案例，XX概率约为YY%」，禁止凭空说'相似案例'\n"
                "3. 薪资必须引用统计区间，格式：「参考N条案例，应届薪资范围为XX-XXK（中位数XXK）」\n"
                "4. 如果样本量<5，必须明确声明「样本量有限，以下判断仅供参考」\n"
                "5. 如果统计数据中没有相关信息，不得编造概率，应明确说「现有数据不足以给出可靠概率估计」\n"
                "6. 保留替代可能性：「也有约YY%的案例显示另一种情况...」\n"
                "7. 统计数据中的百分比是已计算好的，直接引用即可，不要重新计算\n"
                "8. 【数字一致性】回答中出现的所有样本量数字（如'X位学长''样本量N'）必须严格取自上方「证据统计数据」的同一字段，禁止在同一回答里出现口径不一致的多个总数（如既说15位又说样本量13）。若统计数据未给出某口径的总数，就不要自行编造该数字\n\n"
                "【回答要求 — 精简结构化，贴合学生需求】\n"
                "1. 用自然语言回答，语气亲切，像学长学姐在给学弟学妹建议\n"
                "2. 回答总字数控制在300-500字以内，不要长篇大论\n"
                "3. 待办清单格式（'- [ ] '）仅用于'有明确时间节点和执行动作、做完一件勾一件'的行动步骤（如'- [ ] 大三上学期完成一段大数据项目实习''- [ ] 9月前通过英语六级'）。其他建议内容用自然段落或'1. 2. 3.'编号叙述，不要用 '- ' 无序列表，不要用边框块包裹建议。\n"
                "4. 回答必须直答问题且分层结构化：第一句必须直接回答用户问题本身（如用户问'做什么能拿2万月薪'，第一句应直接答'大数据开发、数据科学家、数据分析师是达2万月薪的主流岗位'），严禁用'X位学长中...''基于N条案例...''样本量N...'这种统计依据/数据来源式开头。再用2-3个分点展开，每点用加粗序号标题独占一行（格式'**N. 标题**'，如'**1. 薪资水平**''**2. 所需能力**''**3. 行动路径**'），标题用纯中文不加emoji不加代码前缀。标题下用1-2句简短内容支撑。分点正文只写定性结论和具体建议，禁止出现人数/占比/分布等统计数字（如'8位学长''4人''占比30%''集中在15-20K'），这些统计只能用第13条的chart块可视化展现；仅允许极简单个数值点睛（如'应届中位数18.5K'），且不解释样本量\n"
                "4.5. 【比较/选择类问题】如果用户问的是'A还是B''适合A还是B''该选A还是B'等比较选择类问题，第一句必须直接给出明确推荐（如'以你目前绩点3.84的条件，保研是更优选择'），然后用分点对比两条路径的差异（如门槛、时间投入、成功率、风险等），最后给出行动建议。不要泛泛而谈'两者各有优势'，要结合用户背景给出明确倾向性结论\n"
                "5. 禁止使用---分隔符、*斜体*、#标题、emoji图标等装饰。分点标题用加粗序号（见第4条）。正文中关键指标（如绩点3.88、排名1/36、薪资18K）保持自然行文，不强制包裹\n"
                "6. 直接使用纯文本，段落之间用空行分隔，每段不超过3-4句\n"
                "7. 正文聚焦回答问题本身，禁止罗列学长案例和'师兄/师姐/同学'称呼。统计性结论（如'X位学长中Y人从事...''参考N位学长''集中在X-Y（Z人）''N人选择...''占比Z%''全部从事某岗位''多数企业采用N薪'）禁止用文字陈述，必须用第13条的chart代码块可视化展现。仅单个数值（如中位数、区间端点）可作为结论的简短支撑带出。具体学长案例交给右侧溯源卡片，正文不提称呼\n"
                "8. 回答要具体、可操作，不要太空泛\n"
                "9. 必须完整回答用户的所有问题，不要遗漏\n"
                "10. 如果用户背景为'暂未提供个人背景信息'，直接基于检索案例给出通用建议，禁止在回答中提及'未填写/未提供/没有填写个人资料'等表述\n"
                "11. 绝对禁止自行推断用户的年级或学习阶段，除非用户在问题中明确提及\n"
                "12. 【脱敏规则】正文原则上不出现任何学长称呼（禁止'师兄/师姐/学长/学姐/同学'等），聚焦问题答案。如必须引用某人数据，用'部分学长''往届毕业生'等不带具体称呼的表述。绝对禁止出现真实姓名。绝对禁止在正文出现'案例A''案例B''案例H'等任何案例标识符（这些仅用于你内部理解证据来源，不得写入回答）。具体学长案例由右侧溯源卡片独立展示，正文无需重复\n"
                "13. 【可视化图表 — 非必要不加，加则多样化】\n"
                "  加图条件：仅当证据统计数据中确实有分布/区间/趋势/对比类数据，且该数据对回答用户问题有直接价值时才加图。如果用户问的是方法/建议/比较选择类问题（如'科研怎么准备''保研应该注重什么''适合考研还是保研'），不需要加图。如果用户问的是数据类问题（如'薪资多少''去哪工作'），才加图。\n"
                "  图表类型选择规则：占比分布用饼图(pie)；区间对比用柱图(bar)；年度/时间趋势用折线(line)；明细对比用表格。不要每条回答都用饼图，根据数据特征选最合适的类型。\n"
                "  饼图（占比分布）— 第一行标题，后续每行'名称 数值'：\n"
                "  ```chart:pie\n去向分布\n全职就业 60\n升学深造 25\n出国留学 10\n创业 5\n```\n"
                "  柱图（区间/数量对比）：```chart:bar\n薪资区间\n8K以下 2\n8-12K 5\n12-15K 8\n15-20K 4\n```\n"
                "  折线（年度趋势）：```chart:line\n保研人数\n2019 3\n2020 5\n2021 8\n2022 10\n```\n"
                "  表格（明细对比）— 用markdown表格：\n  | 维度 | 选项A | 选项B |\n  |---|---|---|\n  | 起薪 | 18K | 25K |\n  | 占比 | 30% | 20% |\n"
                "  规则：图表数据必须来自上方证据统计，禁止编造；一条回答最多1个图表（避免过载）；若回答无可视化数据或用户问的是方法建议类问题则不输出任何图表块；chart块必须用三个反引号```包裹（格式```chart:pie\\n标题\\n名称 数值\\n...```），缺反引号会导致前端无法渲染；占比类数值不带%号直接写数字（如'60'而非'60%'）"
            )

            # === 证据脱敏：将真实姓名替换为脱敏称呼后再发给LLM ===
            name_mapping = self._build_name_mapping(chunks)
            desensitized_fused = self._desensitize_evidence_dict(fused.to_dict(), name_mapping)

            # 方向类问题：只给统计数据，不给原始保研证据 chunks，避免 LLM 被单一方向证据带着走
            if is_direction:
                evidence_section = (
                    "（方向类问题：为避免被单一方向证据主导，不提供原始案例。"
                    "请基于上方统计数据和你的专业知识，生成覆盖保研/就业/考研多方向的对比回答）"
                )
            else:
                evidence_section = (
                    "（姓名已脱敏为'案例A/案例B'等中性标识，仅供你内部理解数据来源。"
                    "回答正文中绝对禁止出现'案例A''案例B''案例G'等任何案例标识符，"
                    "也禁止'师兄/师姐/学长/学姐/同学'等称呼；仅使用统计数据支撑结论，"
                    "如必须提及某人用'部分往届生''有案例显示'等不带标识的表述；"
                    "具体案例数据由右侧溯源卡片独立展示）\n"
                    f"{json.dumps(desensitized_fused, ensure_ascii=False)[:8000]}"
                )

            response_text = self.llm.complete_text(
                system_prompt=system_prompt,
                user_prompt=(
                    f"{intent_directive}\n"
                    f"用户问题：{raw_input}\n"
                    f"用户背景：{background}\n\n"
                    f"【证据统计数据】以下数据均从检索到的真实案例中代码统计得出，非编造：\n{stats_text}\n\n"
                    f"【原始证据参考】{evidence_section}"
                ),
                fallback="",
            )
            
            if not response_text or not str(response_text).strip():
                print(f"[LLM Debug] Empty response text", file=sys.stderr)
                return None
            
            # === 回答后脱敏兜底：替换LLM可能泄露的真实姓名 ===
            response_text = self._desensitize_text(response_text, name_mapping)
            
            print(f"[LLM Debug] Natural response: {response_text[:500]}...", file=sys.stderr)
            
            return AgentResponse(
                analysis=str(response_text),
                decision="",
                action_plan=[],
                reason="",
                evidence=[item.to_dict() for item in chunks[:5]],
                caveats=[],
            )
        except Exception as e:
            print(f"[LLM Debug] Exception in _reason_with_llm_natural: {e}", file=sys.stderr)
            return None

    # ==================== 证据统计方法（零LLM调用，纯代码统计） ====================

    def _compute_evidence_stats(
        self, chunks: List[RetrievedChunk], user_query: StructuredQuery
    ) -> Dict[str, Any]:
        """从检索到的真实chunks中统计证据数据，按三种数据源分桶处理。

        分桶规则：
        - census（年级普查）: 仅用于聚合统计概率/分布，样本人数权威来源
        - deep_interview 或老 interview 的 profile/timeline/decision: 用于绩点/排名/录取院校/offer具体数字
        - public_interview 或 advice/method/reflection: 定性经验佐证，不做数值统计
        - employment: 用于薪资/公司/岗位统计
        """
        if not chunks:
            return {"sample_size": 0, "total_chunks": 0, "question_type": "general"}

        is_employment = self._is_employment_question(user_query)
        is_gradschool = self._is_gradschool_question(user_query)
        # 综合性方向选择问题：不锁定单一升学/就业意图，stats 走 general 分支，
        # 避免输出保研去向细节让 LLM 误以为只能围绕保研回答
        _raw = user_query.user_profile.get('raw_input', '')
        if self._is_direction_question(_raw):
            is_employment = False
            is_gradschool = False

        # ---- 按三种数据源分桶 ----
        census_chunks: List[RetrievedChunk] = []
        deep_chunks: List[RetrievedChunk] = []
        public_chunks: List[RetrievedChunk] = []
        emp_chunks: List[RetrievedChunk] = []

        for c in chunks:
            ct = c.type
            ds = str(c.content.get("data_source", ""))
            if ct == "census":
                census_chunks.append(c)
            elif ct == "employment":
                emp_chunks.append(c)
            elif ds == "deep_interview" or ct in ("profile", "timeline", "decision"):
                deep_chunks.append(c)
            else:
                # public_interview / advice / reflection / method 等
                public_chunks.append(c)

        scores = [c.score for c in chunks]
        stats: Dict[str, Any] = {
            "total_chunks": len(chunks),
            "avg_similarity": round(sum(scores) / len(scores), 3),
            "min_similarity": round(min(scores), 3),
            "max_similarity": round(max(scores), 3),
            "source_breakdown": {
                "census_count": len(census_chunks),
                "deep_count": len(deep_chunks),
                "public_count": len(public_chunks),
                "employment_count": len(emp_chunks),
            },
        }

        # 样本人数：census 的独立人数 + 深度 + 公众号 去重合并
        census_persons = {c.person_id for c in census_chunks if c.person_id}
        deep_persons = {c.person_id for c in deep_chunks if c.person_id}
        public_persons = {c.person_id for c in public_chunks if c.person_id}
        emp_persons = {c.person_id for c in emp_chunks if c.person_id}
        stats["sample_size"] = len(census_persons | deep_persons | public_persons | emp_persons)
        stats["census_sample_size"] = len(census_persons)  # 最权威的"全年级多少人"口径

        # 专业、年级分布：取 census + deep 合并（都有精确字段）
        all_structured = census_chunks + deep_chunks + emp_chunks
        majors = [c.content.get("major", "") for c in all_structured if c.content.get("major")]
        stats["major_distribution"] = dict(Counter(majors))
        stages = [c.content.get("stage", "") for c in all_structured if c.content.get("stage")]
        stats["grade_distribution"] = dict(Counter(stages))

        # 家乡/去向统计优先用 census（大样本）
        if census_chunks:
            future_paths = [
                c.content.get("future_path", "") for c in census_chunks
                if c.content.get("future_path")
            ]
            if future_paths:
                stats["future_path_distribution"] = dict(Counter(future_paths))
            hometowns_census = [
                c.content.get("hometown_province", "") for c in census_chunks
                if c.content.get("hometown_province")
            ]
            if hometowns_census:
                stats["hometown_distribution"] = dict(Counter(hometowns_census))
            # 按去向的GPA门槛
            if is_gradschool:
                gpa_paths = [
                    (float(c.content["gpa"]), c.content.get("future_path", ""))
                    for c in census_chunks
                    if isinstance(c.content.get("gpa"), (int, float))
                ]
                gradschool_gpas = sorted([g for g, p in gpa_paths if "保研" in p])
                if gradschool_gpas:
                    n = len(gradschool_gpas)
                    stats["gpa_from_census"] = {
                        "保研样本数": n,
                        "保研绩点中位数": round(
                            gradschool_gpas[n // 2] if n % 2 == 1
                            else (gradschool_gpas[n // 2 - 1] + gradschool_gpas[n // 2]) / 2, 2
                        ),
                        "保研绩点最低": round(min(gradschool_gpas), 2),
                        "保研绩点前25%阈值": round(
                            gradschool_gpas[max(0, n // 4)], 2
                        ),
                    }
            if is_employment:
                # 从普查中统计目标公司/省份/岗位分布
                target_provs = [
                    c.content.get("province", "") for c in census_chunks
                    if c.content.get("future_path") == "就业" and c.content.get("province")
                ]
                if target_provs:
                    stats["work_province_from_census"] = dict(Counter(target_provs))

        if is_employment:
            stats["question_type"] = "employment"
            # 薪资/公司只从 employment 型 chunks 算（细节多），普查只做去向分布
            all_emp = emp_chunks + deep_chunks if emp_chunks else (deep_chunks or chunks)
            stats.update(self._compute_employment_stats(all_emp))
        elif is_gradschool:
            stats["question_type"] = "gradschool"
            # 保研绩点/排名/录取院校，优先 deep_interview 的 profile（信息最精确）
            stats.update(self._compute_gradschool_stats(deep_chunks or chunks))
        else:
            stats["question_type"] = "general"

        return stats

    def _compute_employment_stats(self, emp_chunks: List[RetrievedChunk]) -> Dict[str, Any]:
        """统计就业类数据：薪资、城市、岗位、家乡分布"""
        result: Dict[str, Any] = {}

        # --- 薪资统计（从content文本正则提取） ---
        fresh_salaries: List[int] = []
        multipliers: List[int] = []
        for c in emp_chunks:
            text = str(c.content.get("content", ""))
            # 应届XXK×YY薪
            m = re.search(r"应届(\d+)K[×x\*](\d+)薪", text)
            if m:
                fresh_salaries.append(int(m.group(1)))
                multipliers.append(int(m.group(2)))

        if fresh_salaries:
            fresh_salaries_sorted = sorted(fresh_salaries)
            n = len(fresh_salaries_sorted)
            median = fresh_salaries_sorted[n // 2] if n % 2 == 1 else (
                (fresh_salaries_sorted[n // 2 - 1] + fresh_salaries_sorted[n // 2]) / 2
            )
            result["salary"] = {
                "fresh_values": fresh_salaries_sorted,
                "median": int(median) if median == int(median) else round(median, 1),
                "min": min(fresh_salaries_sorted),
                "max": max(fresh_salaries_sorted),
                "sample_count": n,
            }
            # 各档分布（供前端图表，口径与数据概览面板一致）
            brackets = [("8K以下", 0, 8), ("8-12K", 8, 12), ("12-15K", 12, 15), ("15-20K", 15, 20), ("20-30K", 20, 30), ("30K以上", 30, 9999)]
            bracket_dist = {}
            for label, lo, hi in brackets:
                cnt = sum(1 for s in fresh_salaries_sorted if lo <= s < hi)
                if cnt > 0:
                    bracket_dist[label] = cnt
            if bracket_dist:
                result["salary"]["bracket_dist"] = bracket_dist
            if multipliers:
                result["salary"]["multiplier_median"] = sorted(multipliers)[len(multipliers) // 2]

        # --- 工作城市分布（优先从person_id提取，回退到province字段） ---
        cities: List[str] = []
        for c in emp_chunks:
            city = self._extract_city(c)
            if city:
                cities.append(city)
        if cities:
            result["work_city_distribution"] = dict(Counter(cities))

        # --- 岗位类型分布（基于topic/tags关键词分类） ---
        job_types: List[str] = []
        for c in emp_chunks:
            jt = self._categorize_job_type(c)
            if jt:
                job_types.append(jt)
        if job_types:
            result["job_type_distribution"] = dict(Counter(job_types))

        # --- 家乡省份分布 ---
        hometowns: List[str] = []
        for c in emp_chunks:
            ht = c.content.get("hometown_province", "")
            if ht:
                # 标准化：去掉"省/市/自治区"后缀，保留简称
                ht_short = re.sub(r"(省|市|自治区|壮族自治区|维吾尔自治区|回族自治区)$", "", ht)
                hometowns.append(ht_short)
        if hometowns:
            result["hometown_distribution"] = dict(Counter(hometowns))

        # --- 公司分布 ---
        companies: List[str] = []
        for c in emp_chunks:
            topic = str(c.content.get("topic", ""))
            # topic格式："就业案例-字节跳动数据分析师"
            if topic.startswith("就业案例-"):
                rest = topic[len("就业案例-"):]
                # 公司名通常在开头，岗位在后；用已知岗位关键词切分
                job_kw = ["大数据工程师", "数据分析师", "数据工程师", "算法工程师",
                          "AI产品经理", "产品经理", "AI工程师", "AI研究员", "量化分析师"]
                company = rest
                for kw in job_kw:
                    idx = rest.find(kw)
                    if idx > 0:
                        company = rest[:idx]
                        break
                if company:
                    companies.append(company)
        if companies:
            result["company_distribution"] = dict(Counter(companies))

        return result

    def _compute_gradschool_stats(self, chunks: List[RetrievedChunk]) -> Dict[str, Any]:
        """统计保研/考研类数据：绩点、排名、录取院校分布"""
        result: Dict[str, Any] = {}

        # --- 绩点统计（从content正则提取） ---
        gpas: List[float] = []
        for c in chunks:
            text = str(c.content.get("content", ""))
            m = re.search(r"绩点[：:]\s*(\d+\.?\d*)", text)
            if m:
                try:
                    gpas.append(float(m.group(1)))
                except ValueError:
                    pass
        if gpas:
            gpas_sorted = sorted(gpas)
            n = len(gpas_sorted)
            median = gpas_sorted[n // 2] if n % 2 == 1 else (
                (gpas_sorted[n // 2 - 1] + gpas_sorted[n // 2]) / 2
            )
            result["gpa"] = {
                "values": gpas_sorted,
                "median": round(median, 2),
                "min": min(gpas_sorted),
                "max": max(gpas_sorted),
                "sample_count": n,
            }

        # --- 专业排名统计 ---
        ranks: List[tuple[int, int]] = []
        for c in chunks:
            text = str(c.content.get("content", ""))
            m = re.search(r"专业排名[：:]\s*(\d+)/(\d+)", text)
            if m:
                try:
                    ranks.append((int(m.group(1)), int(m.group(2))))
                except ValueError:
                    pass
        if ranks:
            result["rank"] = {
                "values": ranks,
                "best_rank": min(r[0] for r in ranks),
                "median_rank": sorted(r[0] for r in ranks)[len(ranks) // 2],
                "sample_count": len(ranks),
            }

        # --- 录取院校分布（从content提取"录取院校：XXX"） ---
        target_schools: List[str] = []
        for c in chunks:
            text = str(c.content.get("content", ""))
            m = re.search(r"录取院校[：:]\s*([^\s；;,，。、]+)", text)
            if m:
                target_schools.append(m.group(1).strip())
        if target_schools:
            result["target_school_distribution"] = dict(Counter(target_schools))

        # --- target字段分布（保研去向类型） ---
        targets = [c.content.get("target", "") for c in chunks if c.content.get("target")]
        # 过滤掉非去向类型（如"大英经验分享""竞赛经验分享"等访谈主题被误存为target）
        valid_targets = [t for t in targets if t and "分享" not in t and "经验" not in t]
        if valid_targets:
            result["target_type_distribution"] = dict(Counter(valid_targets))

        return result

    def _extract_city(self, chunk: RetrievedChunk) -> str:
        """从chunk中提取工作城市，优先person_id，回退province"""
        # person_id格式："张学长_北京"
        pid = chunk.person_id or ""
        if "_" in pid:
            city = pid.rsplit("_", 1)[-1]
            if city:
                return city
        # 回退：标准化province字段
        province = chunk.content.get("province", "")
        if province:
            return re.sub(r"(省|市|自治区|壮族自治区|维吾尔自治区|回族自治区)$", "", province)
        return ""

    def _categorize_job_type(self, chunk: RetrievedChunk) -> str:
        """基于topic和tags关键词将岗位归类到标准类型"""
        topic = str(chunk.content.get("topic", ""))
        tags = chunk.content.get("tags", [])
        tags_text = " ".join(tags) if isinstance(tags, list) else str(tags)
        content = str(chunk.content.get("content", ""))
        text = f"{topic} {tags_text} {content}"

        if "数据分析" in text:
            return "数据分析"
        if "大数据" in text or "数据工程" in text:
            return "大数据开发"
        if "量化" in text or "金融" in text:
            return "金融量化"
        if "产品" in text:
            return "产品经理"
        if "算法" in text and "工程" in text:
            return "算法工程师"
        if "AI" in text.upper() or "人工智能" in text:
            return "AI工程师"
        if "算法" in text:
            return "算法"
        if "研究" in text:
            return "研究员"
        return ""

    def _format_stats(self, stats: Dict[str, Any]) -> str:
        """将统计结果格式化为人类可读文本，注入prompt"""
        if stats.get("sample_size", 0) == 0:
            return "（未检索到相关案例，无统计数据）"

        sample = stats["sample_size"]
        total = stats["total_chunks"]
        avg_sim = stats.get("avg_similarity", 0)
        min_sim = stats.get("min_similarity", 0)
        max_sim = stats.get("max_similarity", 0)
        lines: List[str] = [
            f"样本规模：共{sample}位学长（来自{total}条检索记录，部分学长有多条记录），相似度区间{min_sim}-{max_sim}（平均{avg_sim}）。引用学长人数时必须用{sample}，不得用{total}"
        ]

        # 专业分布
        major_dist = stats.get("major_distribution", {})
        if major_dist:
            major_str = "、".join(f"{k}{v}人" for k, v in major_dist.items())
            lines.append(f"专业分布：{major_str}")

        # 年级分布
        grade_dist = stats.get("grade_distribution", {})
        if grade_dist:
            grade_str = "、".join(f"{k}{v}人" for k, v in grade_dist.items())
            lines.append(f"年级分布：{grade_str}")

        qtype = stats.get("question_type", "general")

        if qtype == "employment":
            # 薪资
            salary = stats.get("salary", {})
            if salary:
                lines.append(
                    f"应届薪资：中位数{salary['median']}K，"
                    f"区间{salary['min']}-{salary['max']}K，"
                    f"样本量{salary['sample_count']}"
                )
                if "bracket_dist" in salary:
                    bd = salary["bracket_dist"]
                    bd_str = "、".join(f"{k}{v}人" for k, v in bd.items())
                    lines.append(f"薪资各档分布：{bd_str}")
                if "multiplier_median" in salary:
                    lines.append(f"年薪倍数：中位数{salary['multiplier_median']}薪")

            # 工作城市分布
            city_dist = stats.get("work_city_distribution", {})
            if city_dist:
                city_items = sorted(city_dist.items(), key=lambda x: -x[1])
                city_str = "、".join(
                    f"{city}({cnt}人，{round(cnt / sample * 100)}%)"
                    for city, cnt in city_items if sample > 0
                )
                lines.append(f"工作城市分布：{city_str}")

            # 岗位类型分布
            job_dist = stats.get("job_type_distribution", {})
            if job_dist:
                job_items = sorted(job_dist.items(), key=lambda x: -x[1])
                job_str = "、".join(
                    f"{jt}({cnt}人，{round(cnt / sample * 100)}%)"
                    for jt, cnt in job_items if sample > 0
                )
                lines.append(f"岗位类型分布：{job_str}")

            # 家乡分布
            ht_dist = stats.get("hometown_distribution", {})
            if ht_dist:
                ht_items = sorted(ht_dist.items(), key=lambda x: -x[1])[:5]
                ht_str = "、".join(f"{k}{v}人" for k, v in ht_items)
                lines.append(f"家乡分布（前5）：{ht_str}")

            # 公司分布
            comp_dist = stats.get("company_distribution", {})
            if comp_dist:
                comp_items = sorted(comp_dist.items(), key=lambda x: -x[1])[:5]
                comp_str = "、".join(f"{k}{v}人" for k, v in comp_items)
                lines.append(f"公司分布（前5）：{comp_str}")

        elif qtype == "gradschool":
            # 绩点
            gpa = stats.get("gpa", {})
            if gpa:
                lines.append(
                    f"绩点：中位数{gpa['median']}，区间{gpa['min']}-{gpa['max']}，"
                    f"样本量{gpa['sample_count']}"
                )

            # 专业排名
            rank = stats.get("rank", {})
            if rank:
                lines.append(
                    f"专业排名：最优{rank['best_rank']}名，中位数{rank['median_rank']}名，"
                    f"样本量{rank['sample_count']}"
                )

            # 录取院校分布
            school_dist = stats.get("target_school_distribution", {})
            if school_dist:
                school_items = sorted(school_dist.items(), key=lambda x: -x[1])
                school_str = "、".join(f"{k}{v}人" for k, v in school_items)
                lines.append(f"录取院校分布：{school_str}")

            # 保研去向类型
            target_dist = stats.get("target_type_distribution", {})
            if target_dist:
                target_items = sorted(target_dist.items(), key=lambda x: -x[1])
                target_str = "、".join(f"{k}{v}条" for k, v in target_items)
                lines.append(f"保研去向类型：{target_str}")

        # 小样本警告
        if sample < 5:
            lines.append("【注意】样本量有限（<5），以下判断仅供参考，个体差异可能较大")

        return "\n".join(lines)

    def _group_by_type(self, chunks: List[RetrievedChunk]) -> Dict[str, List[RetrievedChunk]]:
        grouped: Dict[str, List[RetrievedChunk]] = defaultdict(list)
        for item in chunks:
            grouped[item.type].append(item)
        return grouped

    def _is_employment_question(self, user_query: StructuredQuery) -> bool:
        """判断是否为就业相关问题"""
        employment_keywords = [
            "就业", "工作", "求职", "薪资", "工资", "待遇", "前景",
            "发展方向", "就业方向", "哪里工作", "从事什么", "职业规划",
            "职业发展", "行业选择", "公司选择", "岗位选择", "秋招", "春招",
            "上班", "打工", "副业", "创业", "自由职业",
            "岗位", "职位", "薪水", "薪酬", "跳槽", "转行"
        ]
        
        text = f"{user_query.who} {user_query.what} {user_query.goal} {user_query.user_profile.get('raw_input', '')}"
        text_lower = text.lower()
        
        if user_query.goal == "就业":
            return True
        
        return any(kw in text or kw.lower() in text_lower for kw in employment_keywords)

    def _is_gradschool_question(self, user_query: StructuredQuery) -> bool:
        """判断是否为保研/考研相关问题"""
        gradschool_keywords = [
            "保研", "推免", "夏令营", "预推免", "考研", "读研",
            "绩点", "科研", "实验室", "导师", "论文",
            "复试", "材料", "文书", "个人陈述", "推荐信",
            "学术", "研究生", "硕士", "博士", "直博",
            "学硕", "专硕", "考研", "备考"
        ]
        
        text = f"{user_query.who} {user_query.what} {user_query.goal} {user_query.user_profile.get('raw_input', '')}"

        if user_query.goal in ["保研", "考研"]:
            return True

        return any(kw in text for kw in gradschool_keywords)

    def _is_direction_question(self, raw_input: str) -> bool:
        """判断是否为综合性方向选择/规划类问题。
        这类问题不锁定单一升学或就业意图，应给出多方向对比建议。
        例如：'我应该往哪个方向努力''该选哪条路''怎么规划未来发展'。
        关键：问题中没有明确出现'保研/就业/考研'等单一方向词，而是问'方向/努力/规划/选择'。
        """
        if not raw_input:
            return False
        # 显式单一方向词出现则不算综合性方向问题
        single_track = ["保研", "推免", "夏令营", "考研", "读研", "就业", "求职", "工作", "薪资", "工资"]
        if any(kw in raw_input for kw in single_track):
            return False
        # 综合性方向选择关键词
        direction_patterns = [
            r"往.{0,4}方向",
            r"应该.{0,6}方向",
            r"哪个方向",
            r"什么方向",
            r"该选.{0,6}路",
            r"选哪条路",
            r"怎么规划",
            r"如何规划",
            r"未来规划",
            r"未来.{0,6}发展",
            r"发展方向",
            r"应该往.{0,4}努力",
            r"往.{0,4}努力",
            r"怎么努力",
            r"如何努力",
            r"应该怎么走",
            r"路怎么走",
        ]
        return any(re.search(p, raw_input) for p in direction_patterns)

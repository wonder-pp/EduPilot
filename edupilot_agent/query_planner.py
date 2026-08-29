from __future__ import annotations

import re
from typing import List

from edupilot_agent.llm_client import JsonLLMClient
from edupilot_agent.schemas import StructuredQuery


class QueryPlanner:
    """Turn raw user input into a structured retrieval intent."""

    def __init__(self, llm: JsonLLMClient | None = None):
        self.llm = llm or JsonLLMClient(enabled=False)

    STAGE_PATTERNS = [
        ("大一", r"大一|一年级|freshman"),
        ("大二", r"大二|二年级|sophomore"),
        ("大三", r"大三|三年级|junior"),
        ("大四", r"大四|四年级|senior"),
        ("研一", r"研一"),
        ("研二", r"研二"),
    ]

    MAJOR_PATTERNS = [
        ("数据科学", r"数科|数据科学|大数据|数据专业"),
        ("计算机", r"计算机|CS|软件工程|计科"),
        ("数学", r"数学|应用数学|统计"),
        ("电子信息", r"电子信息|通信|EE|微电子"),
        ("自动化", r"自动化|控制工程"),
        ("金融", r"金融|经济|经管"),
        ("机械", r"机械|机电|制造"),
        ("材料", r"材料|材料科学"),
        ("生物", r"生物|生命科学"),
        ("化学", r"化学|化工"),
        ("物理", r"物理"),
    ]

    GOAL_PATTERNS = [
        ("保研", r"保研|推免|夏令营|预推免"),
        ("考研", r"考研|读研"),
        ("就业", r"就业|找工作|求职|秋招|春招|上班|工作|薪资|工资|待遇|前景|发展方向|就业方向|哪里工作|从事什么"),
        ("出国", r"出国|留学|申请海外"),
    ]

    TOPIC_PATTERNS = [
        ("就业方向", r"就业|工作|求职|薪资|工资|待遇|前景|发展方向|就业方向|哪里工作|从事什么|职业规划|职业发展|行业选择|公司选择|岗位选择"),
        ("保研发力点", r"发力|重点|着重|最重要|核心"),
        ("绩点还是科研", r"绩点.*科研|科研.*绩点"),
        ("竞赛还是科研", r"竞赛.*科研|科研.*竞赛"),
        ("时间管理", r"时间管理|平衡|兼顾|安排"),
        ("创新创业", r"创新创业|创新比赛|创业比赛|互联网\+|大创|大学生创新创业训练计划"),
        ("科研入门", r"科研|实验室|导师|论文"),
        ("数学竞赛", r"数学竞赛|大数竞赛|数学建模|数模"),
        ("竞赛规划", r"竞赛|比赛|国奖|省奖"),
        ("实习规划", r"实习|暑期实习|寒假实习"),
        ("材料与复试", r"简历|个人陈述|面试|复试|夏令营"),
        ("信息获取", r"信息差|官网|通知|学长学姐|经验帖"),
        ("避坑与复盘", r"踩坑|避坑|后悔|复盘"),
    ]

    CONSTRAINT_KEYWORDS = [
        "GPA",
        "科研",
        "竞赛",
        "实习",
        "论文",
        "英语",
        "六级",
        "项目",
        "智科",
        "智能科学与技术",
    ]

    def plan(self, user_input: str) -> StructuredQuery:
        fallback = self._rule_plan(user_input)
        if not self.llm.enabled and not self.llm.available:
            return fallback
        if self.llm.enabled and not self.llm.available:
            raise RuntimeError("LLM mode is enabled, but the LLM client is not available.")

        payload = self.llm.complete_json(
            system_prompt=(
                "你是教育规划问答系统的 Query Planner。请只输出 JSON，不要输出解释。"
                "需要抽取用户画像、目标、阶段、约束、问题类型，并拆成可检索的子问题。"
            ),
            user_prompt=(
                "请按这个 JSON schema 输出："
                '{"who": "...", "what": "...", "stage": "...", "goal": "...", '
                '"question_type": "why/how/which/what", '
                '"user_profile": {"major": "", "grade": "", "goal": "", "confusion": ""}, '
                '"constraints": ["..."], "sub_questions": ["..."]}\n\n'
                f"用户问题：{user_input}"
            ),
            fallback=fallback.to_dict(),
        )
        return self._from_payload(payload, fallback)

    def _rule_plan(self, user_input: str) -> StructuredQuery:
        stage = self._detect_by_patterns(user_input, self.STAGE_PATTERNS, default="大学整体")
        major = self._detect_by_patterns(user_input, self.MAJOR_PATTERNS, default="")
        goal = self._detect_by_patterns(user_input, self.GOAL_PATTERNS, default="")
        topic = self._detect_topic(user_input)
        constraints = self._extract_constraints(user_input)
        question_type = self._detect_question_type(user_input)

        who_parts = [part for part in [stage, major, goal] if part]
        who_parts.extend(constraints[:3])
        who = " + ".join([part for part in who_parts if part]) or "经验相似学生"

        return StructuredQuery(
            who=who,
            what=topic,
            stage=stage,
            goal=goal,
            question_type=question_type,
            user_profile={
                "grade": stage,
                "major": major,
                "goal": goal,
                "confusion": topic,
                "raw_input": user_input,
            },
            sub_questions=self._build_sub_questions(stage, goal, topic, question_type),
            constraints=constraints,
        )

    def _from_payload(self, payload: dict, fallback: StructuredQuery) -> StructuredQuery:
        if not isinstance(payload, dict):
            return fallback
        sub_questions = payload.get("sub_questions", fallback.sub_questions)
        constraints = payload.get("constraints", fallback.constraints)
        # Always preserve raw_input from fallback — LLM payload's user_profile lacks it
        llm_profile = payload.get("user_profile")
        if isinstance(llm_profile, dict):
            user_profile = dict(llm_profile)
        else:
            user_profile = dict(fallback.user_profile)
        user_profile["raw_input"] = fallback.user_profile.get("raw_input", "")
        return StructuredQuery(
            who=str(payload.get("who") or fallback.who),
            what=str(payload.get("what") or fallback.what),
            stage=str(payload.get("stage") or fallback.stage),
            goal=str(payload.get("goal") or fallback.goal),
            question_type=str(payload.get("question_type") or fallback.question_type),
            user_profile=user_profile,
            sub_questions=sub_questions if isinstance(sub_questions, list) else fallback.sub_questions,
            constraints=constraints if isinstance(constraints, list) else fallback.constraints,
        )

    def _detect_by_patterns(self, text: str, patterns: List[tuple[str, str]], default: str) -> str:
        for label, pattern in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return label
        return default

    def _detect_topic(self, text: str) -> str:
        for label, pattern in self.TOPIC_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return label
        cleaned = re.sub(r"\s+", " ", text).strip()
        return cleaned[:40] if cleaned else "经验建议"

    def _extract_constraints(self, text: str) -> List[str]:
        found: List[str] = []
        lowered = text.lower()

        for item in self.CONSTRAINT_KEYWORDS:
            if item.lower() in lowered:
                found.append(item)

        gpa_match = re.search(r"GPA\s*([0-4]\.?\d*)", text, flags=re.IGNORECASE)
        if gpa_match:
            found.append(f"GPA {gpa_match.group(1)}")

        if "没有科研" in text or "无科研" in text:
            found.append("无科研")
        if "没有竞赛" in text or "无竞赛" in text:
            found.append("无竞赛")
        return found

    def _detect_question_type(self, text: str) -> str:
        if re.search(r"为什么|原因|适合吗|值不值", text):
            return "why"
        if re.search(r"怎么|如何|怎样|路径|规划|准备", text):
            return "how"
        if re.search(r"哪个|哪一个|还是|选择|A|B", text, flags=re.IGNORECASE):
            return "which"
        return "what"

    def _build_sub_questions(self, stage: str, goal: str, topic: str, question_type: str) -> List[str]:
        base = [
            f"{stage} {goal} 的当前核心矛盾是什么？".strip(),
            f"相似背景学生在 {topic} 上做过哪些关键选择？",
            f"可以复用哪些行动方法和避坑经验？",
        ]
        if question_type == "which":
            base.insert(1, f"{topic} 的优先级和取舍依据是什么？")
        if question_type == "why":
            base.insert(1, f"{topic} 背后的原因和约束是什么？")
        return base


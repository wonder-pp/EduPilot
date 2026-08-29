from __future__ import annotations

from edupilot_agent.schemas import RetrievalQueryBundle, StructuredQuery


class QueryGenerator:
    """Generate multi-channel retrieval queries from a structured query."""

    def generate(self, structured_query: StructuredQuery) -> RetrievalQueryBundle:
        goal = structured_query.goal
        what = structured_query.what
        stage = structured_query.stage
        hometown = structured_query.user_profile.get('hometown', '')
        
        # 从constraints中提取家乡信息
        hometown_constraint = ''
        for c in structured_query.constraints:
            if c.startswith('家乡='):
                hometown_constraint = c.replace('家乡=', '')
                break
        
        # 优先使用constraints中的家乡信息
        if hometown_constraint:
            hometown = hometown_constraint
        
        constraints = " ".join(structured_query.constraints)
        who_query = f"{structured_query.who} {constraints} 人物画像 背景 profile tags"
        what_query = f"{what} {structured_query.question_type} 关键选择 建议 方法 复盘"
        stage_query = f"{stage} 应该如何规划 timeline advice method"

        # 检测是否为就业案例查询
        is_employment_case = (
            goal == "就业" and 
            any(kw in what for kw in ["就业方向", "就业案例", "工作"])
        )
        
        # 检测是否包含案例查询关键词
        case_keywords = ["师哥", "师姐", "师兄", "学姐", "学长", "同学", "往届", "毕业生", "案例", "例子"]
        is_case_query = any(kw in what for kw in case_keywords) or any(
            kw in structured_query.user_profile.get('raw_input', '') 
            for kw in case_keywords
        )

        if is_employment_case or is_case_query:
            # 就业案例查询 - 优先检索就业案例数据
            fused_queries = [
                "就业案例 师哥师姐 工作案例 就业去向",
                f"{goal} 案例 经验 分享 工作去向",
                "就业 案例 经验 工作 公司 岗位 薪资",
                f"{what} case study alumni experience career",
                f"{stage} {goal} 案例 经验 分享",
            ]
            # 如果有家乡信息，添加地区相关的检索查询
            if hometown:
                hometown_province = self._extract_province(hometown)
                fused_queries.insert(0, f"{hometown} 就业案例 师哥师姐 工作")
                fused_queries.insert(1, f"{hometown_province} 就业 案例 工作 公司")
        elif goal == "就业":
            # 通用就业查询
            fused_queries = [
                "就业方向 就业 求职 职业规划",
                f"{goal} 案例 经验 分享",
                "就业 岗位 薪资 技能 行业",
                f"{what} decision reason tradeoff",
                f"{stage} {goal} advice method",
            ]
            # 如果有家乡信息，添加地区相关的检索查询
            if hometown:
                hometown_province = self._extract_province(hometown)
                fused_queries.insert(0, f"{hometown} 就业 求职 工作 机会")
                fused_queries.insert(1, f"{hometown_province} 就业 行业 岗位")
        elif goal in ["保研", "考研"]:
            # 保研/考研查询
            fused_queries = [
                f"{stage} {goal} {what}".strip(),
                f"{what} decision reason tradeoff",
                f"{what} advice method reflection",
                f"{goal} 发力点 绩点 科研 竞赛 材料 复试".strip(),
            ]
        else:
            # 通用查询
            fused_queries = [
                f"{stage} {goal} {what}".strip(),
                f"{what} decision reason tradeoff",
                f"{what} advice method reflection",
                f"{goal} 发力点 绩点 科研 竞赛 材料 复试".strip(),
            ]
        
        fused_queries.extend(
            f"{sub_question} profile timeline decision advice method reflection"
            for sub_question in structured_query.sub_questions
        )
        
        return RetrievalQueryBundle(
            who_query=who_query,
            what_query=what_query,
            stage_query=stage_query,
            fused_queries=fused_queries,
        )
    
    def _extract_province(self, hometown: str) -> str:
        """从家乡信息中提取省份关键词"""
        # 常见省份映射
        province_map = {
            '北京': '北京', '上海': '上海', '天津': '天津', '重庆': '重庆',
            '河北': '河北', '山西': '山西', '辽宁': '辽宁', '吉林': '吉林', '黑龙江': '黑龙江',
            '江苏': '江苏', '浙江': '浙江', '安徽': '安徽', '福建': '福建', '江西': '江西', '山东': '山东',
            '河南': '河南', '湖北': '湖北', '湖南': '湖南', '广东': '广东', '海南': '海南',
            '四川': '四川', '贵州': '贵州', '云南': '云南', '陕西': '陕西', '甘肃': '甘肃', '青海': '青海',
            '内蒙古': '内蒙古', '广西': '广西', '西藏': '西藏', '宁夏': '宁夏', '新疆': '新疆',
            '深圳': '广东', '广州': '广东', '杭州': '浙江', '成都': '四川', '武汉': '湖北',
            '西安': '陕西', '南京': '江苏', '苏州': '江苏', '郑州': '河南', '长沙': '湖南',
            '青岛': '山东', '大连': '辽宁', '厦门': '福建', '合肥': '安徽', '福州': '福建',
        }
        
        # 尝试匹配
        for city, province in province_map.items():
            if city in hometown:
                return province
        
        # 如果没有匹配到，返回原字符串
        return hometown[:2] if len(hometown) >= 2 else hometown


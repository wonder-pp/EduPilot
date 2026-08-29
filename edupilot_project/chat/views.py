from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import sys
import os
import re
import json
import math
import uuid
import logging
from pathlib import Path
from datetime import datetime
from difflib import SequenceMatcher
from django.utils import timezone

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from django.db.models import Q
from .models import (
    CourseSyllabus, SyllabusDuplicate, CourseRelation,
    SeniorMentor, AnonymousFeedback, ExcellentWork, SeniorEmployment, UserProfile,
    KnowledgePoint, CourseAnalysisReport, FeedbackAnalysis, GrowthPath,
    TeacherCourse, StudentCourse
)

USERS_FILE = Path(__file__).parent.parent.parent / "users.json"
from edupilot_agent.agent import MentorExperienceAgent
from edupilot_agent.langchain_adapter import LangChainRetrieverAdapter, load_faiss_retriever
from edupilot_agent.llm_client import JsonLLMClient



logger = logging.getLogger(__name__)

HOMETOWN_KNOWLEDGE_FILE = Path(__file__).parent.parent.parent / "hometown_knowledge.json"

def load_hometown_knowledge(hometown, major=None):
    """
    根据家乡地和专业加载相关知识
    返回格式化的知识字典，包含产业、岗位、薪资等信息
    """
    if not hometown:
        return None
    
    try:
        if os.path.exists(HOMETOWN_KNOWLEDGE_FILE):
            with open(HOMETOWN_KNOWLEDGE_FILE, 'r', encoding='utf-8') as f:
                knowledge = json.load(f)
            
            # 尝试精确匹配
            city_data = None
            for key in knowledge:
                if key in hometown or hometown in key:
                    city_data = knowledge[key]
                    break
            
            if not city_data:
                # 尝试从省份匹配
                for key in knowledge:
                    if city_data is None and knowledge[key].get('province', '') in hometown:
                        city_data = knowledge[key]
                        break
            
            if city_data:
                result = {
                    'main_industries': '、'.join(city_data.get('main_industries', [])[:5]),
                    'tech_companies': '、'.join(city_data.get('tech_companies', [])[:8]),
                    'salary_range': city_data.get('salary_range', ''),
                    'development_trend': city_data.get('development_trend', ''),
                    'resources': '、'.join(city_data.get('resources', [])[:4]),
                }
                
                # 根据专业推荐岗位
                major_str = major or ''
                if '数据科学' in major_str or '大数据' in major_str:
                    result['positions'] = '、'.join(city_data.get('positions_for_data_science', [])[:5])
                elif '智能科学' in major_str or '人工智能' in major_str or 'AI' in major_str.upper():
                    result['positions'] = '、'.join(city_data.get('positions_for_ai_science', [])[:5])
                else:
                    # 默认推荐两个方向的岗位
                    ds_pos = city_data.get('positions_for_data_science', [])[:3]
                    ai_pos = city_data.get('positions_for_ai_science', [])[:3]
                    result['positions'] = '、'.join(ds_pos + ai_pos)
                
                return result
    except Exception as e:
        logger.error(f"Failed to load hometown knowledge: {e}")
    
    return None

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load users: {e}")
            return {}
    return {}

def save_users(users):
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save users: {e}")

def generate_user_id():
    return str(uuid.uuid4())[:8]

def _merge_user_profile_from_db(frontend_profile: dict | None, user_id: str) -> dict:
    """用 user_id 查 UserProfile 表，合并到前端传入的 profile。
    前端传了就覆盖数据库值，没传就用数据库值。不再瞎给默认值。"""
    merged = dict(frontend_profile) if frontend_profile else {}
    if not user_id:
        return merged
    try:
        db_profile = UserProfile.objects.get(user_id=user_id)
        db_fields = [
            ("grade", db_profile.grade),
            ("major", db_profile.major),
            ("gpa", str(db_profile.gpa) if db_profile.gpa else ""),
            ("rank", db_profile.rank),
            ("awards", db_profile.awards),
            ("research", db_profile.research),
            ("goal", db_profile.goal),
            ("hometown", db_profile.hometown),
            ("department", db_profile.department),
            ("position", db_profile.position),
            ("role", db_profile.role),
        ]
        for key, val in db_fields:
            if val and (not merged.get(key)):
                merged[key] = val
    except UserProfile.DoesNotExist:
        pass
    return merged

# ---- 从用户问题文本 + 对话历史自动抽取 5 项匹配维度（方案 C）----
_MATCH_PROVINCES = [
    "北京", "天津", "上海", "重庆",
    "河北", "山西", "辽宁", "吉林", "黑龙江",
    "江苏", "浙江", "安徽", "福建", "江西", "山东",
    "河南", "湖北", "湖南", "广东", "海南",
    "四川", "贵州", "云南", "陕西", "甘肃", "青海", "台湾",
    "内蒙古", "广西", "西藏", "宁夏", "新疆",
    "香港", "澳门",
]

_MAJOR_KEYWORDS = [
    ("数据科学与大数据技术", ["数据科学", "大数据技术", "数据专业", "数据科学与", "大数据专业", "ds专业", "数科"]),
    ("智能科学与技术", ["智能科学", "智能专业", "智科", "ai专业", "ai科学", "智能技术"]),
]

_GOAL_KEYWORDS = [
    ("保研", ["保研", "推免", "保送到", "保研到"]),
    ("考研", ["考研", "考研究生", "准备考研", "备考研究生", "考研到"]),
    ("就业", ["就业", "找工作", "去工作", "想工作", "毕业直接工作", "进公司", "求职", "上班"]),
    ("出国", ["出国", "留学", "申请海外", "海外读研", "国外读研", "申硕", "出国读研"]),
]

_GRADE_YEAR_PAT = re.compile(r"(20\d{2})\s*级?")  # 2024 或 2024级
_GRADE_SHORT_PAT = re.compile(r"\b(\d{2})\s*级\b")   # 24级

def _map_chinese_year_name(text: str) -> str | None:
    """把"大一/大二/大三/大四/大一新生/大四毕业生"映射到 XXXX级。
    假设当前是 2026 年 8 月（大一=2025级，大二=2024级，大三=2023级，大四=2022级）"""
    now = datetime.now()
    year = now.year
    if now.month >= 9:
        freshman = year           # 9月后大一 = 当年级
    else:
        freshman = year - 1       # 9月前大一 = 去年级
    mapping = [
        (f"{freshman}级",    ["大一", "新生", "一年级"]),
        (f"{freshman-1}级",  ["大二", "二年级"]),
        (f"{freshman-2}级",  ["大三", "三年级"]),
        (f"{freshman-3}级",  ["大四", "四年级", "毕业生"]),
        (f"{freshman-4}级",  ["大五", "延毕"]),
    ]
    for grade_val, keywords in mapping:
        if any(k in text for k in keywords):
            return grade_val
    return None


def _extract_profile_from_text(question_text: str, context_text: str, existing_profile: dict) -> dict:
    """【方案C】从用户当前问题 + 对话历史里关键词抽取 5 项匹配维度。
    抽取优先级：当前问题中明确提到的 > 历史中提到的 > 已有 profile 存储值。
    返回新的 profile dict（不修改 existing_profile 本身）。"""
    result = dict(existing_profile) if existing_profile else {}

    combined_all = f"{question_text or ''}\n{context_text or ''}"
    q_lower = (question_text or "").lower()
    all_lower = combined_all.lower()

    # 1) 专业：只从当前问题抽取（不从对话历史带，避免上一轮说了这轮没说却被误带）
    if not result.get("major"):
        hit = None
        for major_val, kws in _MAJOR_KEYWORDS:
            if any(kw.lower() in q_lower for kw in kws):
                hit = major_val
                break
        if hit:
            result["major"] = hit

    # 2) 年级：只从当前问题抽取（不从历史带，避免跨轮误用）
    if not result.get("grade"):
        hit = _map_chinese_year_name(question_text or "")
        if not hit:
            m = _GRADE_YEAR_PAT.search(question_text or "")
            if m:
                hit = f"{m.group(1)}级"
        if not hit:
            m = _GRADE_SHORT_PAT.search(question_text or "")
            if m:
                hit = f"20{m.group(1)}级"
        if hit:
            result["grade"] = hit

    # 3) 家乡省份：只从当前问题抽取
    if not result.get("hometown"):
        def _find_province(txt: str) -> str | None:
            for p in _MATCH_PROVINCES:
                if p in txt:
                    return p
            return None
        hit = _find_province(question_text or "")
        if hit:
            result["hometown"] = hit

    # 4) 去向目标：只从当前问题抽取
    if not result.get("goal"):
        hit = None
        for goal_val, kws in _GOAL_KEYWORDS:
            if any(kw in (question_text or "") for kw in kws):
                hit = goal_val
                break
        if hit:
            result["goal"] = hit

    # 5) GPA：只从当前问题提取，0.0-5.0 范围
    if not result.get("gpa"):
        gpa_pat = re.compile(
            r"(?:gpa|绩点|平均分|g)[\s:：是为=]*([0-4]\.\d{1,2}|5\.00?|\d(?:\.\d{1,2})?)",
            re.IGNORECASE,
        )
        m = gpa_pat.search(question_text or "")
        if not m:
            # 兜底：问题文本里任意 0.0-5.0 范围的两位小数
            loose_pat = re.compile(r"\b([0-4]\.\d{1,2}|5\.00?)\b")
            m = loose_pat.search(question_text or "")
        if m:
            try:
                gpa_val = float(m.group(1))
                if 0.0 <= gpa_val <= 5.0:
                    result["gpa"] = str(gpa_val)
            except (ValueError, TypeError):
                pass

    return result


def _grade_to_chinese_desc(grade_str: str) -> str:
    """把"2024级"转成"2024级（大二升大三）"这种LLM不会误解的描述。
    当前2026年8月：2025级=大一升大二，2024级=大二升大三，2023级=大三升大四，2022级=大四已毕业"""
    now = datetime.now()
    year = now.year
    if now.month >= 9:
        freshman = year
    else:
        freshman = year - 1
    # freshman=2025（9月前），2025级=刚读完大一=大一升大二
    grade_map = {
        freshman: "大一升大二",
        freshman - 1: "大二升大三",
        freshman - 2: "大三升大四",
        freshman - 3: "大四已毕业",
    }
    import re as _re
    m = _re.match(r"^(20\d{2})级?", grade_str)
    if m:
        gy = int(m.group(1))
        desc = grade_map.get(gy)
        if desc:
            return f"{gy}级（{desc}）"
    return grade_str


def check_permission(request, required_role=None):
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return JsonResponse({'error': '未登录，请先登录'}, status=401)
    
    try:
        profile = UserProfile.objects.get(user_id=user_id)
        if required_role and profile.role not in [required_role, 'admin']:
            return JsonResponse({'error': '权限不足'}, status=403)
        return None, profile
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': '用户不存在'}, status=404)

def get_llm_client():
    try:
        llm = JsonLLMClient(enabled=True)
        return llm
    except Exception as e:
        logger.error(f"Failed to initialize LLM: {e}")
        return None

_agent = None

def get_agent():
    global _agent
    if _agent is not None:
        return _agent
        
    original_cwd = os.getcwd()
    project_dir = str(Path(__file__).parent.parent.parent)
    os.chdir(project_dir)
    try:
        vector_store = "edupilot_agent/data/langchain_faiss"
        retriever = load_faiss_retriever(persist_dir=vector_store, k=15)
        llm = JsonLLMClient(enabled=True)
        logger.info(f"LLM Status: {llm.status()}")
        _agent = MentorExperienceAgent(retriever=retriever, llm=llm)
        return _agent
    finally:
        os.chdir(original_cwd)

def index(request):
    return render(request, 'index.html')

@csrf_exempt
def login(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
    except:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    username = data.get('username', '')
    password = data.get('password', '')
    role = data.get('role', 'student')
    
    if not username or not password:
        return JsonResponse({'error': '请输入用户名和密码'}, status=400)
    
    users = load_users()
    user_id = None
    user_record = None
    
    for uid, user in users.items():
        if user.get('username') == username and user.get('password') == password:
            user_id = uid
            user_record = user
            break
    
    if not user_id:
        return JsonResponse({'error': '用户名或密码错误'}, status=401)
    
    actual_role = user_record.get('role', '')
    
    try:
        profile = UserProfile.objects.get(user_id=user_id)
        if not actual_role:
            actual_role = profile.role
        if not actual_role:
            actual_role = role
            profile.role = actual_role
            profile.save()
        profile_data = {
            'grade': profile.grade,
            'major': profile.major,
            'gpa': str(profile.gpa) if profile.gpa else '',
            'rank': profile.rank,
            'awards': profile.awards,
            'research': profile.research,
            'goal': profile.goal,
            'hometown': profile.hometown,
            'role': profile.role,
            'department': profile.department,
            'position': profile.position
        }
    except UserProfile.DoesNotExist:
        actual_role = user_record.get('role', role)
        profile = UserProfile.objects.create(
            user_id=user_id,
            username=username,
            role=actual_role
        )
        profile_data = {}
    
    if role != actual_role:
        if actual_role == 'admin' and role == 'teacher':
            pass
        elif actual_role == 'teacher' and role == 'admin':
            pass
        else:
            role_labels = {'student': '学生', 'teacher': '教师', 'admin': '管理员'}
            actual_label = role_labels.get(actual_role, actual_role)
            selected_label = role_labels.get(role, role)
            return JsonResponse({
                'error': f'该账号是{actual_label}账号，请选择「{actual_label}」端登录（当前选择的是「{selected_label}」端）'
            }, status=403)
    
    response_role = 'teacher' if actual_role == 'admin' else actual_role
    return JsonResponse({
        'success': True,
        'user_id': user_id,
        'username': username,
        'role': response_role,
        'profile': profile_data
    })

@csrf_exempt
def register(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
    except:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    username = data.get('username', '')
    password = data.get('password', '')
    role = data.get('role', 'student')
    
    if not username or not password:
        return JsonResponse({'error': '请输入用户名和密码'}, status=400)
    
    users = load_users()
    
    for user in users.values():
        if user.get('username') == username:
            return JsonResponse({'error': '用户名已存在'}, status=409)
    
    user_id = generate_user_id()
    users[user_id] = {
        'username': username,
        'password': password,
        'role': role,
        'created_at': datetime.now().isoformat()
    }
    
    save_users(users)
    UserProfile.objects.create(user_id=user_id, username=username, role=role)
    
    return JsonResponse({
        'success': True,
        'user_id': user_id,
        'username': username,
        'profile': {}
    })


def _anonymize_name(person_id: str) -> str:
    """对学长姓名脱敏：已脱敏的(含学长/学姐等)直接用，真实姓名取首字+*"""
    if not person_id:
        return "匿名学长"
    # 去掉 "_城市" 后缀
    name = person_id.split("_")[0].strip()
    if not name:
        return "匿名学长"
    # 已脱敏的称谓直接返回
    honorifics = ["学长", "学姐", "师兄", "师姐", "同学"]
    for h in honorifics:
        if name.endswith(h) and len(name) <= 4:
            return name
    # 纯英文/拼音名：取首字母大写 + 同学
    if all(c.isascii() and (c.isalpha() or c == '.') for c in name):
        if len(name) <= 2:
            return name.capitalize() + "同学"
        return name[0].upper() + "同学"
    # 真实中文姓名：姓氏拼音首字母大写 + 某某
    if len(name) >= 2:
        # 尝试将姓氏转为拼音首字母
        first_char = name[0]
        # 常见姓氏拼音首字母映射
        surname_pinyin = {
            '王': 'W', '李': 'L', '张': 'Z', '刘': 'L', '陈': 'C', '杨': 'Y', '黄': 'H',
            '赵': 'Z', '吴': 'W', '周': 'Z', '徐': 'X', '孙': 'S', '马': 'M', '朱': 'Z',
            '胡': 'H', '郭': 'G', '何': 'H', '高': 'G', '林': 'L', '罗': 'L', '郑': 'Z',
            '梁': 'L', '谢': 'X', '宋': 'S', '唐': 'T', '许': 'X', '韩': 'H', '冯': 'F',
            '邓': 'D', '曹': 'C', '彭': 'P', '曾': 'Z', '田': 'T', '萧': 'X', '潘': 'P',
            '袁': 'Y', '蔡': 'C', '蒋': 'J', '余': 'Y', '杜': 'D', '叶': 'Y', '程': 'C',
            '苏': 'S', '魏': 'W', '吕': 'L', '丁': 'D', '任': 'R', '沈': 'S', '姚': 'Y',
            '卢': 'L', '姜': 'J', '崔': 'C', '钟': 'Z', '谭': 'T', '陆': 'L', '汪': 'W',
            '范': 'F', '金': 'J', '石': 'S', '廖': 'L', '贾': 'J', '夏': 'X', '韦': 'W',
            '方': 'F', '邹': 'Z', '熊': 'X', '孟': 'M', '秦': 'Q', '阎': 'Y', '薛': 'X',
            '侯': 'H', '雷': 'L', '白': 'B', '龙': 'L', '段': 'D', '郝': 'H', '孔': 'K',
            '邵': 'S', '史': 'S', '毛': 'M', '常': 'C', '万': 'W', '顾': 'G', '赖': 'L',
            '武': 'W', '康': 'K', '贺': 'H', '严': 'Y', '尹': 'Y', '钱': 'Q', '施': 'S',
            '洪': 'H', '翟': 'Z', '安': 'A', '颜': 'Y', '倪': 'N', '牛': 'N', '潘': 'P',
            '温': 'W', '俞': 'Y', '鲁': 'L', '韦': 'W', '申': 'S', '葛': 'G', '章': 'Z',
            '云': 'Y', '查': 'C', '翁': 'W', '欧阳': 'O', '司马': 'S', '上官': 'S',
        }
        # 检查复姓
        if len(name) >= 3 and name[:2] in surname_pinyin:
            return surname_pinyin[name[:2]] + "某某"
        if first_char in surname_pinyin:
            return surname_pinyin[first_char] + "某某"
        # 无法映射的姓氏，用原字 + 某某
        return first_char + "某某"
    return name


# ==================== 回答脱敏 ====================

_FEMALE_NAME_CHARS = set("婷颖妍雯瑶悦佳欣思雨桐瑞丽芳燕玲娜丹琳倩婧璇瑾珂莹")
_MALE_NAME_CHARS = set("浩宇轩然博涛毅远明文俊峰强磊刚伟勇杰鹏辉豪航鑫")


def _guess_gender_by_name(name: str) -> str:
    """根据中文名字猜测性别"""
    if not name or len(name) < 2:
        return "师兄"
    given = name[1:]
    female_score = sum(1 for c in given if c in _FEMALE_NAME_CHARS)
    male_score = sum(1 for c in given if c in _MALE_NAME_CHARS)
    return "师姐" if female_score > male_score else "师兄"


def _to_honorific(person_id: str) -> str:
    """将 person_id 转为脱敏称呼（如 '常佳毅' → '常师兄'）"""
    if not person_id:
        return "某师兄"
    name = person_id.split("_")[0].strip()
    for h in ["学长", "学姐", "师兄", "师姐", "同学"]:
        if name.endswith(h) and len(name) <= 4:
            return name
    if all(c.isascii() and (c.isalpha() or c == '.') for c in name):
        return name[0].upper() + "同学"
    if len(name) >= 2:
        return f"{name[0]}{_guess_gender_by_name(name)}"
    return "某师兄"


def _desensitize_answer(answer: dict, raw_evidence: list) -> dict:
    """在LLM回答文本中替换所有真实姓名为脱敏称呼（兜底）"""
    # 构建姓名映射
    name_mapping = {}
    for ev in raw_evidence:
        pid = (ev.get("content") or {}).get("person_id", "") or ev.get("person_id", "")
        if pid and pid not in name_mapping:
            name_mapping[pid] = _to_honorific(pid)
    if not name_mapping:
        return answer

    # 按姓名长度降序排列，避免短姓名误匹配
    sorted_names = sorted(name_mapping.keys(), key=lambda x: len(x.split("_")[0]), reverse=True)

    def _replace_text(text: str) -> str:
        if not text:
            return text
        result = text
        for real_name in sorted_names:
            short_name = real_name.split("_")[0].strip()
            desensitized = name_mapping[real_name]
            if short_name and len(short_name) >= 2:
                result = result.replace(short_name, desensitized)
        return result

    # 脱敏所有文本字段
    for field in ["analysis", "decision", "reason"]:
        if answer.get(field):
            answer[field] = _replace_text(answer[field])
    if answer.get("action_plan"):
        answer["action_plan"] = [_replace_text(item) if isinstance(item, str) else item
                                 for item in answer["action_plan"]]
    if answer.get("caveats"):
        answer["caveats"] = [_replace_text(item) if isinstance(item, str) else item
                             for item in answer["caveats"]]
    if answer.get("full_text"):
        answer["full_text"] = _replace_text(answer["full_text"])
    return answer


def _extract_highlights(content_text: str, chunk_type: str, topic: str = "") -> list:
    """从证据正文里提取关键亮点用于卡片展示"""
    highlights = []
    text = content_text or ""

    # 就业类：提取公司、岗位、薪资、工作地
    if chunk_type == "employment" or "就业" in text or (topic and topic.startswith("就业案例")):
        # 从topic提取公司+岗位（格式：就业案例-字节跳动数据分析师）
        if topic and topic.startswith("就业案例-"):
            rest = topic[len("就业案例-"):]
            job_kw = ["大数据工程师", "数据分析师", "数据工程师", "算法工程师",
                      "AI产品经理", "产品经理", "AI工程师", "AI研究员", "量化分析师"]
            for kw in job_kw:
                idx = rest.find(kw)
                if idx > 0:
                    company = rest[:idx]
                    if len(company) >= 2:
                        highlights.append(f"{company} · {kw}")
                    break
        # 薪资
        m = re.search(r"应届(\d+K[×x\*]\d+薪)", text)
        if m:
            highlights.append(f"应届{m.group(1)}")
        # 工作地区
        m = re.search(r"工作(?:城市|地区|地点)[：:]\s*([^\s；;,，。、]+)", text)
        if m:
            highlights.append(f"工作地：{m.group(1)}")

    # 保研/考研类：提取录取院校、绩点、排名
    if "保研" in text or "推免" in text or "考研" in text or chunk_type in ("profile", "timeline", "decision"):
        m = re.search(r"录取院校[：:]\s*([^\s；;,，。、]+)", text)
        if m:
            highlights.append(f"保研至：{m.group(1)}")
        m = re.search(r"绩点[：:]\s*(\d+\.?\d*)", text)
        if m:
            highlights.append(f"绩点{m.group(1)}")
        m = re.search(r"专业排名[：:]\s*(\d+/\d+)", text)
        if m:
            highlights.append(f"排名{m.group(1)}")

    # 通用：target字段（去向）
    if not highlights:
        m = re.search(r"目标[：:]\s*([^\s；;,，。、]+)", text)
        if m:
            highlights.append(m.group(1))

    return highlights[:4]


def _extract_profile(content_text: str, chunk_type: str, topic: str = "",
                     content: dict | None = None) -> dict:
    """从证据正文提取个人基本档案信息，用于卡片展示"""
    text = content_text or ""
    profile = {}
    c = content or {}

    # 绩点
    m = re.search(r"绩点[：:]\s*(\d+\.?\d*)", text)
    if m:
        profile["gpa"] = m.group(1)
    elif isinstance(c.get("gpa"), (int, float)):
        profile["gpa"] = str(c["gpa"])

    # 专业排名
    m = re.search(r"专业排名[：:]\s*(\d+/\d+)", text)
    if m:
        profile["rank"] = m.group(1)
    elif c.get("gpa_rank"):
        profile["rank"] = str(c["gpa_rank"])

    # 录取院校（保研去向）
    m = re.search(r"录取院校[：:]\s*([^\s；;,，。、]+)", text)
    if m:
        profile["grad_school"] = m.group(1)
    elif c.get("target_school"):
        profile["grad_school"] = str(c["target_school"])

    # 英语能力
    m = re.search(r"英语能力[：:]\s*([^\s；;,，。、]+(?:[，,][^\s；;,，。、]+)*)", text)
    if m:
        profile["english"] = m.group(1)
    elif c.get("english"):
        profile["english"] = str(c["english"])

    # 政治面貌
    m = re.search(r"政治面貌[：:]\s*([^\s；;,，。、]+)", text)
    if m:
        profile["political"] = m.group(1)
    elif c.get("politics"):
        profile["political"] = str(c["politics"])

    # 毕业年份：从 stage "20XX级" 推算毕业年份（+4年）
    stage = str(c.get("stage", ""))
    m_year = re.search(r"(20\d{2})", stage)
    if m_year:
        grad_year = int(m_year.group(1)) + 4
        profile["grad_year"] = f"{grad_year}届"

    # 岗位类型：从 topic 或 content 中提取
    if chunk_type == "employment" or (topic and topic.startswith("就业案例")):
        # 公司+岗位
        m = re.search(r"进入(.+?)，任(.+?)，", text)
        if m:
            profile["company"] = m.group(1)
            profile["position"] = m.group(2)
        elif c.get("target_company") and c.get("target_position"):
            profile["company"] = str(c["target_company"])
            profile["position"] = str(c["target_position"])

        # 岗位类型分类
        position_text = profile.get("position", "") + " " + topic + " " + text[:200]
        job_categories = [
            ("算法工程师", ["算法", "推荐", "NLP", "CV", "计算机视觉", "机器学习"]),
            ("数据分析", ["数据分析", "BI", "商业分析", "数据挖掘"]),
            ("大数据工程", ["大数据", "数仓", "数据工程", "ETL"]),
            ("产品经理", ["产品经理", "AI产品"]),
            ("量化分析", ["量化", "风控"]),
        ]
        for cat, kws in job_categories:
            if any(kw in position_text for kw in kws):
                profile["job_category"] = cat
                break

        # 薪资范围
        m = re.search(r"应届(\d+)K[×x\*](\d+)薪", text)
        if m:
            base = int(m.group(1))
            mult = int(m.group(2))
            profile["salary"] = f"{base}K×{mult}薪"
            profile["salary_range"] = f"{base}K×{mult}薪（年包{base*mult}W）"
        elif c.get("target_position"):
            # 从普查数据无法提取精确薪资，标注行业范围
            profile["salary_range"] = ""

    # 去向类型
    future_path = str(c.get("future_path", ""))
    target = str(c.get("target", ""))
    if future_path:
        profile["future_path"] = future_path
    elif target:
        profile["future_path"] = target
    elif profile.get("grad_school"):
        profile["future_path"] = "保研"
    elif profile.get("company"):
        profile["future_path"] = "就业"

    return profile


def _extract_signature_keys(content: dict, content_text: str) -> list:
    """从证据中提取高特异性特征词，用于判断该证据是否在回答中被引用。
    只提取高辨识度实体，避免城市名/省份等宽泛词导致误匹配。"""
    keys = []
    text = content_text or ""
    topic = content.get("topic", "")

    # 公司名（从topic "就业案例-字节跳动数据分析师" 提取，高特异）
    if topic.startswith("就业案例-"):
        rest = topic[len("就业案例-"):]
        job_kw = ["大数据工程师", "数据分析师", "数据工程师", "算法工程师",
                  "AI产品经理", "产品经理", "AI工程师", "AI研究员", "量化分析师"]
        for kw in job_kw:
            idx = rest.find(kw)
            if idx > 0:
                company = rest[:idx]
                if len(company) >= 2:
                    keys.append(company)
                break

    # 完整薪资（应届XXK×YY薪，高特异；单独XXK太容易重复不用）
    m = re.search(r"应届(\d+K[×x\*]\d+薪)", text)
    if m:
        keys.append(m.group(1))

    # 录取院校（高特异）
    m = re.search(r"录取院校[：:]\s*([^\s；;,，。、]+)", text)
    if m:
        keys.append(m.group(1))

    # 绩点（较特异，3.91这种）
    m = re.search(r"绩点[：:]\s*(\d+\.\d+)", text)
    if m:
        keys.append(m.group(1))

    # 专业排名（1/63这种，高特异）
    m = re.search(r"专业排名[：:]\s*(\d+/\d+)", text)
    if m:
        keys.append(m.group(0))

    # 注：不再使用tags作为特征词，岗位名/城市名等太容易误匹配
    return keys


def _is_evidence_cited(signature_keys: list, answer_text: str) -> bool:
    """判断证据是否在LLM回答文本中被引用：任一特征词命中即认为被引用"""
    if not signature_keys or not answer_text:
        return False
    for key in signature_keys:
        if key in answer_text:
            return True
    return False


def _compute_match_degree(content: dict, content_text: str,
                          user_profile: dict | None) -> float:
    """计算学长与用户的个人信息匹配度（0-1）。

    与检索语义分数完全独立：只看用户的实际背景和学长的背景有多少重合。
    用户没提供信息 → 低分（15-25%）
    提供的信息越多且匹配 → 高分（最高90%）

    【关键】当结构化字段缺失时，从 content_text 中正则提取补全。
    """
    up = user_profile or {}
    if not up:
        return 0.18  # 未提供任何信息，仅"问题相关"的底线分

    score = 0.15  # 基础分
    matched_fields = 0
    total_fields = 0

    # --- 辅助：从 content_text 中提取缺失的结构化字段 ---
    # 专业
    ev_major = str(content.get("major", ""))
    if not ev_major:
        m = re.search(r"专业[：:]\s*([^\s；;,，。、]+)", content_text)
        if m:
            ev_major = m.group(1)
    # 年级/届
    ev_stage = str(content.get("stage", ""))
    if not ev_stage:
        m = re.search(r"(20\d{2})\s*级", content_text)
        if m:
            ev_stage = m.group(1) + "级"
    # 家乡：优先结构化字段，其次从 person_id 后缀提取，再次从文本提取
    ev_ht = str(content.get("hometown_province", ""))
    if not ev_ht:
        pid = str(content.get("person_id", ""))
        # person_id 格式如 "张学长_北京" → 取后缀省份
        if "_" in pid:
            suffix = pid.split("_")[-1].strip()
            if suffix and len(suffix) <= 4:
                ev_ht = suffix
    if not ev_ht:
        # 从文本中提取省份
        provinces = ["河北", "山西", "辽宁", "吉林", "黑龙江", "江苏", "浙江", "安徽", "福建",
                     "江西", "山东", "河南", "湖北", "湖南", "广东", "海南", "四川", "贵州",
                     "云南", "陕西", "甘肃", "青海", "台湾", "内蒙古", "广西", "西藏", "宁夏",
                     "新疆", "北京", "天津", "上海", "重庆"]
        for prov in provinces:
            if prov in content_text:
                ev_ht = prov
                break

    # --- 1. 专业匹配 (+20%) ---
    total_fields += 1
    user_major = up.get("major", "")
    if user_major and ev_major:
        # 前4个字命中即可（"数据科学" / "智能科学"）
        if user_major[:4] in ev_major or ev_major[:4] in user_major:
            score += 0.20
            matched_fields += 1

    # --- 2. 年级匹配 (+15%) ---
    total_fields += 1
    user_grade = up.get("grade", "") or up.get("stage", "")
    if user_grade and ev_stage:
        # 提取数字部分比较
        u_year = re.search(r"(\d{4})", str(user_grade))
        e_year = re.search(r"(\d{4})", ev_stage)
        if u_year and e_year:
            u_y = int(u_year.group(1))
            e_y = int(e_year.group(1))
            # 学长是往届（比用户早1-5届）最有参考价值
            if 0 < u_y - e_y <= 5:
                score += 0.15
                matched_fields += 1
            elif u_y == e_y:
                score += 0.10  # 同届参考价值稍低（还没走完）
                matched_fields += 1

    # --- 3. 家乡省份匹配 (+15%) ---
    total_fields += 1
    user_ht = up.get("hometown", "") or up.get("hometown_province", "")
    if user_ht and ev_ht:
        if user_ht[:2] in ev_ht or ev_ht[:2] in user_ht:
            score += 0.15
            matched_fields += 1

    # --- 4. 去向目标匹配 (+15%) ---
    total_fields += 1
    user_goal = up.get("goal", "") or up.get("target", "") or up.get("future_path", "")
    ev_topic = str(content.get("topic", ""))
    ev_target = str(content.get("target", ""))
    ev_fp = str(content.get("future_path", ""))
    ev_text_for_goal = ev_topic + ev_target + ev_fp + content_text[:300]
    if user_goal:
        goal_map = {
            "保研": ["保研", "推免", "夏令营"],
            "考研": ["考研", "复试"],
            "就业": ["就业", "工作", "入职", "公司"],
            "出国": ["出国", "留学", "申请"],
        }
        user_goal_key = None
        for k, kws in goal_map.items():
            if k in user_goal or any(kw in user_goal for kw in kws):
                user_goal_key = k
                break
        if user_goal_key:
            if any(kw in ev_text_for_goal for kw in goal_map[user_goal_key]):
                score += 0.15
                matched_fields += 1

    # --- 5. GPA接近 (+10%) ---
    total_fields += 1
    user_gpa = up.get("gpa", "")
    if user_gpa:
        try:
            u_gpa = float(re.search(r"(\d+\.?\d*)", str(user_gpa)).group(1))
            # 从证据中提取GPA
            gpa_m = re.search(r"绩点[：:]\s*(\d+\.?\d*)", content_text)
            if not gpa_m:
                gpa_m = re.search(r"gpa[：:]\s*(\d+\.?\d*)", content_text, re.IGNORECASE)
            if gpa_m:
                e_gpa = float(gpa_m.group(1))
                if abs(u_gpa - e_gpa) < 0.2:
                    score += 0.10
                    matched_fields += 1
                elif abs(u_gpa - e_gpa) < 0.4:
                    score += 0.05  # 接近但不完全相同
                    matched_fields += 1
        except (AttributeError, ValueError):
            pass

    # --- 6. 提供了信息但没命中 → 轻微惩罚 ---
    # 用户提供了信息但和学长完全不匹配，应该比"啥都没说"更低
    provided_fields = sum(1 for v in [up.get("major"), up.get("grade") or up.get("stage"),
                                       up.get("hometown") or up.get("hometown_province"),
                                       up.get("goal") or up.get("target"),
                                       up.get("gpa")] if v)
    if provided_fields > 0 and matched_fields == 0:
        score = 0.12  # 提供了信息但完全不匹配，比没提供还低
    elif provided_fields > 0 and matched_fields < provided_fields / 2:
        score *= 0.8  # 命中率不到一半，打8折

    # 上限90%
    return min(score, 0.90)


def _build_evidence_cards(evidence_list: list, answer_text: str = "",
                          user_profile: dict | None = None) -> list:
    """构造脱敏档案卡片：只保留回答中真正被引用的证据。

    【溯源卡来源约束】
    - ✅ 允许：deep_interview（深度访谈）、employment（就业案例）、interview_chunks里的profile类
    - ✅ 允许：public_interview（公众号访谈，至少有姓名+去向）
    - ❌ 绝对禁止：census（年级普查）数据，保护个人隐私，仅做聚合统计不展示个人

    【匹配度逻辑】
    匹配度 = 学长与用户的个人信息重合度（与检索语义相关度完全独立）
    - 用户未提供任何信息 → 15-25%（仅"问题主题相关"）
    - 专业相同 → +20%
    - 年级匹配（同届或学长是往届） → +15%
    - 家乡同省 → +15%
    - 去向目标一致 → +15%
    - GPA接近（差值<0.2） → +10%
    - 上限 90%（永远不100%）
    """
    # 先为每条证据计算特征词和引用状态
    candidates = []
    for ev in evidence_list:
        content = ev.get("content", {}) or {}
        chunk_type = ev.get("type", "")
        data_source = str(content.get("data_source", ""))

        # 【硬过滤】census 类型永远不上卡片
        if chunk_type == "census":
            continue

        content_text = content.get("content", "")
        sig_keys = _extract_signature_keys(content, content_text)
        is_cited = _is_evidence_cited(sig_keys, answer_text)
        candidates.append({
            "ev": ev,
            "content": content,
            "content_text": content_text,
            "sig_keys": sig_keys,
            "is_cited": is_cited,
            "raw_score": ev.get("score", 0),
        })

    # 优先展示被引用的证据；不足时用未引用的（按召回分数降序）补齐，最多4张
    cited = [c for c in candidates if c["is_cited"]]
    not_cited = [c for c in candidates if not c["is_cited"]]
    not_cited.sort(key=lambda c: -c.get("raw_score", 0))
    # 被引用的优先，未引用的按召回分数补位
    ordered = cited + not_cited

    # 去重：同一学长（person_id）只保留信息最全的一条（被引用优先、profile字段多的优先）
    seen_persons = {}
    for c in ordered:
        pid = c["ev"].get("person_id", "")
        if not pid:
            # 无 person_id 的直接保留（不参与去重）
            seen_persons[id(c)] = (c, 0)
            continue
        content_text = c["content_text"]
        info_richness = 0
        for pattern in [r"绩点", r"专业排名", r"录取院校", r"进入.+?，任", r"应届\d+K", r"英语能力", r"政治面貌"]:
            if re.search(pattern, content_text):
                info_richness += 1
        if c["is_cited"]:
            info_richness += 10  # 被引用的优先级更高
        if pid not in seen_persons or info_richness > seen_persons[pid][1]:
            seen_persons[pid] = (c, info_richness)
    cited = [v[0] for v in seen_persons.values()]
    # 被引用的排在前，其余按召回分数降序
    cited.sort(key=lambda c: (not c["is_cited"], -c.get("raw_score", 0)))

    # 最多展示4张
    cited = cited[:4]

    # 计算相关性等级：基于在原始evidence_list中的排名位置
    total = len(evidence_list) if evidence_list else 1
    cards = []
    for idx, c in enumerate(cited):
        ev = c["ev"]
        content = c["content"]
        chunk_type = ev.get("type", "")
        person_id = ev.get("person_id", "")
        content_text = c["content_text"]

        # 类型标签
        type_label = {
            "employment": "就业案例",
            "profile": "学长档案",
            "timeline": "成长经历",
            "decision": "关键决策",
            "advice": "经验建议",
            "method": "方法论",
            "reflection": "复盘反思",
        }.get(chunk_type, "参考证据")

        # 提取亮点
        highlights = _extract_highlights(content_text, chunk_type, content.get("topic", ""))
        if not highlights and content.get("topic"):
            highlights.append(content["topic"].replace("就业案例-", ""))

        # 匹配度：基于学长与用户的个人信息重合度（与检索语义分完全独立）
        match_score = _compute_match_degree(content, content_text, user_profile)
        match_percent = round(match_score * 100)
        if match_score >= 0.7:
            relevance_label = "高度匹配"
            relevance_level = 3
        elif match_score >= 0.45:
            relevance_label = "较好匹配"
            relevance_level = 2
        else:
            relevance_label = "一般参考"
            relevance_level = 1

        # 从 stage 推算毕业年份（如 "2022 级" → "2026届"）
        stage_str = str(content.get("stage", ""))
        m_year = re.search(r"(20\d{2})", stage_str)
        if not m_year:
            m_year = re.search(r"(20\d{2})\s*级", content_text)
        grad_year = ""
        if m_year:
            grad_year = f"{int(m_year.group(1)) + 4}届"

        card = {
            "anonymized_name": _anonymize_name(person_id),
            "type_label": type_label,
            "type": chunk_type,
            "major": content.get("major", ""),
            "stage": content.get("stage", ""),
            "grad_year": grad_year,
            "target": content.get("target", ""),
            "hometown": content.get("hometown_province", ""),
            "work_province": content.get("province", ""),
            "topic": content.get("topic", ""),
            "tags": content.get("tags", []) if isinstance(content.get("tags"), list) else [],
            "highlights": highlights,
            "profile": _extract_profile(content_text, chunk_type, content.get("topic", ""), content),
            "match_score": round(match_score, 3),
            "match_percent": match_percent,
            "relevance_label": relevance_label,
            "relevance_level": relevance_level,
            "is_cited": c["is_cited"],
        }
        cards.append(card)
    return cards


@csrf_exempt
def ask(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
    except:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    question = data.get('question', '')
    context = data.get('context', '')
    session_id = data.get('session_id', '')
    frontend_profile = data.get('user_profile', {})
    user_id = request.headers.get('X-User-ID', '')
    
    if not user_id:
        return JsonResponse({'error': '用户未认证'}, status=401)
    
    if session_id and session_id != user_id:
        return JsonResponse({'error': '无权使用该会话'}, status=403)
    
    if not session_id:
        session_id = user_id

    # 【兜底1】前端可能传空 profile，这里用 user_id 查 UserProfile 表合并
    _db_profile = _merge_user_profile_from_db(frontend_profile, user_id)
    # 记录用户"明确提供"的维度（只统计问题文本/历史/前端显式传入的，不包含数据库默认值）
    _explicit_profile_keys: set = set()
    if isinstance(frontend_profile, dict):
        for k, v in frontend_profile.items():
            if v is not None and v != "" and v != 0 and v != "0":
                _explicit_profile_keys.add(k)
    # 从文本抽出前先记住数据库已提供的键，后续区分"文本抽出的"和"本来就有的"
    _db_keys = {k for k, v in _db_profile.items() if v is not None and v != "" and v != 0 and v != "0"}
    # 【兜底2/方案C】从当前问题 + 对话历史关键词抽取 5 项匹配维度（聊天里说的就是最真实的，优先级最高）
    user_profile = _extract_profile_from_text(question, context, _db_profile)
    # 记录从文本中新增抽取出的维度 = 用户在对话中明确提及的
    for k, v in user_profile.items():
        if v is None or v == "" or v == 0 or v == "0":
            continue
        if k not in _db_keys:
            _explicit_profile_keys.add(k)
    # 只保留与匹配相关的核心维度
    _MATCH_KEYS = ("major", "grade", "hometown", "goal", "gpa", "hometown_province", "stage", "target")
    explicit_match_keys = sorted(k for k in _explicit_profile_keys if k in _MATCH_KEYS)

    logger.info(f"Received request - session: {session_id[:8] if session_id else 'none'}, question: {question[:50]}...")
    logger.info(f"User profile received(frontend): {frontend_profile}")
    logger.info(f"User profile after DB + text extraction merge: {user_profile}")

    if not question:
        return JsonResponse({'error': '请输入问题'}), 400

    try:
        agent_instance = get_agent()
    except Exception as e:
        logger.error(f"Failed to initialize agent: {e}")
        return JsonResponse({'error': '服务初始化失败，请检查日志'}), 500

    profile_context = ""
    hometown_context = ""
    employment_context = ""
    gradschool_context = ""

    # 个人资料模块已移除，不再自动注入用户背景信息
    # user_profile 仅用于后端检索加权和卡片匹配度计算，不注入到 LLM prompt 中

    # 不把对话历史拼到question里，避免污染意图检测和检索
    # 对话历史仅用于 _extract_profile_from_text 提取用户画像维度
    full_question = question

    logger.info(f"Question sent to agent (first 200 chars): {full_question[:200]}")

    logger.info("Processing query...")
    try:
        # 把grade转成中文描述传给LLM，避免"2024级"被误解为大一
        if user_profile.get("grade"):
            user_profile["grade"] = _grade_to_chinese_desc(user_profile["grade"])
        # 将user_profile传递给agent，使其能利用hometown等信息
        result = agent_instance.run(full_question, top_k=15, user_profile=user_profile)
        answer = result.get('final_answer', {})
    except Exception as e:
        logger.error(f"Agent run error: {e}")
        answer = {
            'analysis': '',
            'decision': 'AI服务暂时不可用',
            'action_plan': ['请稍后再试', '或查看课程大纲和优秀作品获取参考'],
            'reason': f'AI引擎暂时无法响应（{str(e)[:100]}）',
            'caveats': ['系统正在努力恢复中']
        }

    has_structured_data = answer.get('decision') or answer.get('reason') or (answer.get('action_plan') and len(answer.get('action_plan')) > 0) or (answer.get('caveats') and len(answer.get('caveats')) > 0)

    # 构造脱敏的信息溯源档案卡片（只保留回答中真正被引用的证据）
    raw_evidence = answer.get('evidence', []) or []
    # 合并所有回答字段用于引用检测（避免只检测 analysis 导致漏判）
    answer_parts = []
    if answer.get('analysis'):
        answer_parts.append(answer['analysis'])
    if answer.get('decision'):
        answer_parts.append(answer['decision'])
    if answer.get('action_plan'):
        answer_parts.extend(answer['action_plan'])
    if answer.get('reason'):
        answer_parts.append(answer['reason'])
    if answer.get('caveats'):
        answer_parts.extend(answer['caveats'])
    if answer.get('full_text'):
        answer_parts.append(answer['full_text'])
    answer_text = '\n'.join(answer_parts)

    # === 回答脱敏兜底：从证据中提取真实姓名，在回答文本中替换为脱敏称呼 ===
    answer = _desensitize_answer(answer, raw_evidence)
    # 重新构建 answer_text（脱敏后）
    answer_parts = []
    if answer.get('analysis'):
        answer_parts.append(answer['analysis'])
    if answer.get('decision'):
        answer_parts.append(answer['decision'])
    if answer.get('action_plan'):
        answer_parts.extend(answer['action_plan'])
    if answer.get('reason'):
        answer_parts.append(answer['reason'])
    if answer.get('caveats'):
        answer_parts.extend(answer['caveats'])
    if answer.get('full_text'):
        answer_parts.append(answer['full_text'])
    answer_text = '\n'.join(answer_parts)

    evidence_cards = _build_evidence_cards(raw_evidence, answer_text, user_profile)

    # 检索相关指标
    ev_scores = [float(ev.get("score", 0)) for ev in raw_evidence if ev.get("score")]
    # answer_match 保留：检索分数均值映射到 0–100（语义相似度参考，不作为置信度主因子）
    answer_match = round(sum(ev_scores) / len(ev_scores) * 100) if ev_scores else 0
    # 统计数据源分布
    src_counts = {"deep": 0, "public": 0, "census": 0, "employment": 0}
    for ev in raw_evidence:
        ct = ev.get("type", "")
        ds = str((ev.get("content") or {}).get("data_source", ""))
        if ct == "census":
            src_counts["census"] += 1
        elif ct == "employment" or ds == "deep_interview" or ct in ("profile", "timeline", "decision"):
            src_counts["deep"] += 1
        else:
            src_counts["public"] += 1

    # === 可信概率估算（基于检索分数、证据规模、来源质量、内部一致性，避免单一数值）
    ev_count = len(raw_evidence)
    if ev_count == 0:
        confidence = 10
    else:
        # 1) 检索分数均值 0.2~0.7 → 30~75 分（核心主轴，避免固定 baseline）
        avg_score = sum(ev_scores) / len(ev_scores) if ev_scores else 0.2
        score_based = 30 + (avg_score - 0.2) / 0.5 * 45
        score_based = max(20, min(80, score_based))
        # 2) 证据数量：log2 衰减，3→+6，8→+12，超过8不继续加
        n_bonus = min(12, int(math.log2(max(1, ev_count)) * 4))
        # 3) 来源质量系数：普查/就业/深度访谈权重高；纯公众号扣分
        n_total = ev_count
        weighted = (
            src_counts["census"] * 3.0
            + src_counts["employment"] * 2.5
            + src_counts["deep"] * 2.0
            + src_counts["public"] * 0.8
        )
        source_factor = min(1.15, weighted / max(1, n_total) / 2.0)
        source_penalty = 0
        if src_counts["public"] == n_total:
            source_penalty = -8
        if src_counts["census"] == 0 and src_counts["deep"] == 0 and src_counts["employment"] == 0:
            source_penalty = source_penalty - 3
        # 4) 一致性惩罚：≥3 条证据时，按检索分数离散系数（CV）打折扣
        if len(ev_scores) >= 3:
            mean_s = sum(ev_scores) / len(ev_scores)
            var_s = sum((s - mean_s) ** 2 for s in ev_scores) / len(ev_scores)
            std_s = math.sqrt(var_s)
            cv = std_s / max(0.0001, mean_s)
            consistency_penalty = min(10, int(cv * 20))
        else:
            consistency_penalty = 4  # 证据少于 3 条，保守扣 4 分
        confidence = score_based + n_bonus + source_penalty - consistency_penalty
        confidence = int(round(confidence * source_factor))
        confidence = max(10, min(85, confidence))
    evidence_count = ev_count

    # === 诚实的"匹配维度"说明：
    # 只有用户明确提供/提及的维度才算"相似匹配"，避免空口说"和你背景相似"
    # explicit_match_keys: 用户在问题/对话/前端里显式说过的匹配维度（major/grade/hometown/goal/gpa 等）
    # matched_counts: 这些维度在检索证据里实际命中的条数
    explicit_label_map = {
        "major": "专业", "grade": "年级", "hometown": "家乡",
        "hometown_province": "家乡", "goal": "去向目标",
        "gpa": "绩点", "stage": "年级", "target": "去向目标",
    }
    explicit_labels = []
    for k in explicit_match_keys:
        label = explicit_label_map.get(k)
        if label and label not in explicit_labels:
            explicit_labels.append(label)
    matched_counts = {}
    ev_contents = [ev.get("content") or {} for ev in raw_evidence]
    if "专业" in explicit_labels and user_profile.get("major"):
        mv = user_profile["major"][:2]
        matched_counts["专业"] = sum(1 for c in ev_contents if mv in str(c.get("major", "")) or mv in str(c))
    if "家乡" in explicit_labels and user_profile.get("hometown"):
        hv = user_profile["hometown"]
        matched_counts["家乡"] = sum(1 for c in ev_contents if hv in str(c.get("hometown", "")) or hv in str(c.get("hometown_province", "")) or hv in str(c))
    if "年级" in explicit_labels and user_profile.get("grade"):
        gv = str(user_profile["grade"])[:4]
        matched_counts["年级"] = sum(1 for c in ev_contents if gv in str(c.get("grade", "")) or gv in str(c.get("stage", "")))
    if "绩点" in explicit_labels and user_profile.get("gpa"):
        gv = str(user_profile["gpa"])[:3]
        matched_counts["绩点"] = sum(1 for c in ev_contents if gv in str(c.get("gpa", "")) or gv in str(c))
    if "去向目标" in explicit_labels and user_profile.get("goal"):
        tv = user_profile["goal"][:2]
        matched_counts["去向目标"] = sum(1 for c in ev_contents if tv in str(c.get("goal", "")) or tv in str(c.get("target", "")) or tv in str(c.get("future_path", "")) or tv in str(c))
    match_context = {
        "has_explicit": len(explicit_labels) > 0,
        "explicit_labels": explicit_labels,
        "matched_counts": matched_counts,
    }

    # === 回答正文诚实化：当用户没有提供任何匹配维度时，去掉"和你背景相似/相似案例的师哥师姐"这类虚假措辞
    def _normalize_honest(full_text: str) -> str:
        if not full_text:
            return full_text
        if match_context["has_explicit"]:
            return full_text
        # 去掉或替换虚假相似措辞
        reps = [
            ("和你背景相似的", "往届"),
            ("和你情况相似的", "往届"),
            ("与你背景相似的", "往届"),
            ("与你情况相似的", "往届"),
            ("背景相似的", "往届"),
            ("情况相似的", "往届"),
            ("经历相似的", "往届"),
            ("相似背景", "往届毕业生"),
            ("相似案例", "往届毕业生案例"),
            ("相似经历的", "往届"),
            ("相似学生", "往届学生"),
            ("和你相似的", "往届"),
            ("和你同背景的", "往届"),
            ("与你相似的", "往届"),
            ("同背景", "往届"),
            ("背景相近的", "往届"),
            ("基于N条相似案例，", ""),  # 清理 LLM 未填占位
        ]
        t = full_text
        for old, new in reps:
            if old in t:
                t = t.replace(old, new)
        # 清理："往届的学长学姐" / "往届的师哥师姐" 去"的"，以及 "往届往届" 回退
        t = re.sub(r"往届的(师哥|师兄|学长|学姐)", r"往届\1", t)
        t = re.sub(r"(往届\s*){2,}", "往届", t)
        return t

    if has_structured_data:
        for kk in ('analysis', 'decision', 'reason'):
            if answer.get(kk) and isinstance(answer[kk], str):
                answer[kk] = _normalize_honest(answer[kk])
        if isinstance(answer.get('action_plan'), list):
            answer['action_plan'] = [_normalize_honest(x) if isinstance(x, str) else x for x in answer['action_plan']]
        if isinstance(answer.get('caveats'), list):
            answer['caveats'] = [_normalize_honest(x) if isinstance(x, str) else x for x in answer['caveats']]
    # 对 full_text 以及 analysis（natural 模式 has_structured_data=False 时正文可能在 analysis）统一兜底
    if isinstance(answer.get('full_text'), str):
        answer['full_text'] = _normalize_honest(answer['full_text'])
    if isinstance(answer.get('analysis'), str) and not has_structured_data:
        answer['analysis'] = _normalize_honest(answer['analysis'])

    if has_structured_data:
        response = {
            'analysis': answer.get('analysis', ''),
            'decision': answer.get('decision', ''),
            'action_plan': answer.get('action_plan', []),
            'reason': answer.get('reason', ''),
            'caveats': answer.get('caveats', []),
            'evidence': raw_evidence[:3],
            'evidence_cards': evidence_cards,
            'answer_match': answer_match,
            'source_counts': src_counts,
            'confidence': confidence,
            'evidence_count': evidence_count,
            'match_context': match_context,
        }
    else:
        response = {
            'full_text': answer.get('analysis', ''),
            'evidence': raw_evidence[:3],
            'evidence_cards': evidence_cards,
            'answer_match': answer_match,
            'source_counts': src_counts,
            'confidence': confidence,
            'evidence_count': evidence_count,
            'match_context': match_context,
        }

    logger.info(f"Response generated successfully")

    return JsonResponse(response)


# ==================== 课程大纲管理 API ====================

def get_current_academic_year():
    now = datetime.now()
    year = now.year
    month = now.month
    if month >= 9:
        return f"{year}-{year + 1}"
    else:
        return f"{year - 1}-{year}"


@csrf_exempt
def syllabus_upload(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    permission_result = check_permission(request, 'teacher')
    if isinstance(permission_result, JsonResponse):
        return permission_result
    
    try:
        content_type = request.headers.get('Content-Type', '')
        
        if 'application/json' in content_type:
            data = json.loads(request.body)
            files = {}
        else:
            data = request.POST
            files = request.FILES
        
        course_code = data.get('course_code', '')
        course_name = data.get('course_name', '')
        
        if not course_code or not course_name:
            return JsonResponse({'error': '课程代码和课程名称不能为空'}, status=400)
        
        if CourseSyllabus.objects.filter(course_code=course_code).exists():
            return JsonResponse({'error': '课程代码已存在'}, status=409)
        
        user_id = request.headers.get('X-User-ID', '')
        created_by = None
        if user_id:
            try:
                created_by = UserProfile.objects.get(user_id=user_id)
            except UserProfile.DoesNotExist:
                pass
        
        file_upload = files.get('file_upload') if 'file_upload' in files else None
        
        academic_year = data.get('academic_year', '') or get_current_academic_year()
        
        teacher_name = data.get('teacher_name', '')
        if not teacher_name and created_by:
            teacher_name = created_by.username
        
        syllabus = CourseSyllabus.objects.create(
            course_code=course_code,
            course_name=course_name,
            course_name_en=data.get('course_name_en', ''),
            credit=data.get('credit', '0.0'),
            semester=data.get('semester', 'autumn'),
            grade=data.get('grade', ''),
            major=data.get('major', ''),
            teacher_name=teacher_name,
            created_by=created_by,
            course_objectives=data.get('course_objectives', ''),
            course_content=data.get('course_content', ''),
            teaching_methods=data.get('teaching_methods', ''),
            assessment_methods=data.get('assessment_methods', ''),
            reference_materials=data.get('reference_materials', ''),
            prerequisite_courses=data.get('prerequisite_courses', ''),
            file_upload=file_upload,
        )
        
        if created_by:
            semester = data.get('semester', 'autumn')
            try:
                TeacherCourse.objects.create(
                    teacher=created_by,
                    course=syllabus,
                    semester=semester,
                    academic_year=academic_year
                )
            except Exception as e:
                logger.warning(f"Failed to create TeacherCourse for course creator: {e}")

        # 上传后自动提取知识点
        kp_count = 0
        try:
            kp_count = len(sync_knowledge_points(syllabus))
            logger.info(f"Auto-extracted {kp_count} knowledge points for course {syllabus.course_code}")
        except Exception as e:
            logger.warning(f"Failed to auto-extract knowledge points: {e}")

        return JsonResponse({'success': True, 'course_id': syllabus.id, 'kp_count': kp_count})

    except Exception as e:
        logger.error(f"Syllabus upload error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def syllabus_update(request, syllabus_id):
    """编辑更新课程大纲（教师只能修改自己上传的）"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    permission_result = check_permission(request, 'teacher')
    if isinstance(permission_result, JsonResponse):
        return permission_result
    profile = permission_result[1] if isinstance(permission_result, tuple) else None

    try:
        syllabus = CourseSyllabus.objects.get(id=syllabus_id)
    except CourseSyllabus.DoesNotExist:
        return JsonResponse({'error': '课程不存在'}, status=404)

    # 所有权校验：admin 可以改所有，教师只能改自己上传的（按 username 聚合）
    if profile and profile.role == 'teacher':
        if syllabus.created_by is None or syllabus.created_by.username != profile.username:
            return JsonResponse({'error': '无权修改其他老师上传的课程大纲'}, status=403)

    try:
        content_type = request.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            data = json.loads(request.body)
            files = {}
        else:
            data = request.POST
            files = request.FILES

        # 课程代码唯一性校验（排除自身）
        new_code = data.get('course_code', '')
        if new_code and new_code != syllabus.course_code:
            if CourseSyllabus.objects.filter(course_code=new_code).exists():
                return JsonResponse({'error': '课程代码已被其他课程占用'}, status=409)

        # 更新字段
        for field in ['course_code', 'course_name', 'course_name_en', 'credit',
                      'semester', 'grade', 'major', 'teacher_name',
                      'course_objectives', 'course_content', 'teaching_methods',
                      'assessment_methods', 'reference_materials', 'prerequisite_courses']:
            if field in data:
                setattr(syllabus, field, data[field])

        if 'file_upload' in files:
            syllabus.file_upload = files['file_upload']

        syllabus.save()

        # 同步更新知识点（如果课程内容有变化）
        try:
            sync_knowledge_points(syllabus)
        except Exception as e:
            logger.warning(f"Failed to sync knowledge points after update: {e}")

        return JsonResponse({'success': True, 'course_id': syllabus.id})

    except Exception as e:
        logger.error(f"Syllabus update error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


def syllabus_list(request):
    major = request.GET.get('major', '')
    grade = request.GET.get('grade', '')

    queryset = CourseSyllabus.objects.all()

    user_id = request.headers.get('X-User-ID', '')
    if user_id:
        try:
            profile = UserProfile.objects.get(user_id=user_id)
            if profile.role == 'student':
                # 学生仅看到本专业本年级的课程
                if profile.major:
                    queryset = queryset.filter(major__icontains=profile.major)
                if profile.grade:
                    queryset = queryset.filter(grade__icontains=profile.grade)
            elif profile.role == 'teacher':
                # 教师仅看到自己上传的课程大纲（按 username 聚合：同一教师名可能有多个账号）
                queryset = queryset.filter(created_by__username=profile.username)
            # admin 可见全部课程
        except UserProfile.DoesNotExist:
            pass

    if major:
        queryset = queryset.filter(major__icontains=major)
    if grade:
        queryset = queryset.filter(grade__icontains=grade)
    
    syllabi = []
    for s in queryset:
        syllabi.append({
            'id': s.id,
            'course_code': s.course_code,
            'course_name': s.course_name,
            'course_name_en': s.course_name_en,
            'credit': str(s.credit),
            'semester': s.get_semester_display(),
            'grade': s.grade,
            'major': s.major,
            'teacher_name': s.teacher_name,
            'created_at': s.created_at.isoformat()
        })
    
    return JsonResponse({'syllabi': syllabi})

def syllabus_detail(request, syllabus_id):
    try:
        syllabus = CourseSyllabus.objects.get(id=syllabus_id)
    except CourseSyllabus.DoesNotExist:
        return JsonResponse({'error': '课程不存在'}, status=404)

    # 教师只能查看自己上传的课程详情（admin 除外；按 username 聚合，避免同教师多账号时看不到）
    user_id = request.headers.get('X-User-ID', '')
    if user_id:
        try:
            profile = UserProfile.objects.get(user_id=user_id)
            if profile.role == 'teacher':
                if (syllabus.created_by is None) or (syllabus.created_by.username != profile.username):
                    return JsonResponse({'error': '无权查看其他老师上传的课程详情'}, status=403)
        except UserProfile.DoesNotExist:
            pass

    teachers = []
    for tc in syllabus.teachers.all():
        display_name = syllabus.teacher_name or tc.teacher.username
        teachers.append({
            'teacher_id': tc.teacher.user_id,
            'teacher_name': display_name,
            'department': tc.teacher.department,
            'position': tc.teacher.position,
            'email': tc.teacher.email,
            'phone': tc.teacher.phone,
            'semester': tc.get_semester_display(),
            'academic_year': tc.academic_year
        })

    if not teachers and syllabus.created_by:
        display_name = syllabus.teacher_name or syllabus.created_by.username
        teachers.append({
            'teacher_id': syllabus.created_by.user_id,
            'teacher_name': display_name,
            'department': syllabus.created_by.department,
            'position': syllabus.created_by.position,
            'email': syllabus.created_by.email,
            'phone': syllabus.created_by.phone,
            'semester': '',
            'academic_year': ''
        })

    if not teachers and syllabus.teacher_name:
        teachers.append({
            'teacher_id': '',
            'teacher_name': syllabus.teacher_name,
            'department': '',
            'position': '',
            'email': '',
            'phone': '',
            'semester': '',
            'academic_year': ''
        })

    feedbacks = []
    feedback_queryset = syllabus.anonymousfeedback_set.all().order_by('-created_at')

    if user_id:
        try:
            profile = UserProfile.objects.get(user_id=user_id)
            if profile.role == 'teacher':
                teaching_course_ids = [tc.course.id for tc in profile.teaching_courses.all()]
                created_course_ids = list(CourseSyllabus.objects.filter(created_by=profile).values_list('id', flat=True))
                all_my_course_ids = list(set(teaching_course_ids + created_course_ids))
                feedback_queryset = feedback_queryset.filter(
                    Q(is_public=True) |
                    Q(is_public=False) & (Q(target_teacher=profile) | Q(related_course__id__in=all_my_course_ids))
                )
            elif profile.role == 'student':
                enrolled_course_ids = [sc.course.id for sc in profile.enrolled_courses.all()]
                feedback_queryset = feedback_queryset.filter(
                    Q(is_public=True) |
                    Q(is_public=False) & Q(related_course__id__in=enrolled_course_ids)
                )
        except UserProfile.DoesNotExist:
            pass

    feedback_queryset = feedback_queryset[:20]

    for fb in feedback_queryset:
        feedbacks.append({
            'id': fb.id,
            'title': fb.title,
            'content': fb.content,
            'feedback_type': fb.get_feedback_type_display(),
            'is_anonymous': fb.is_anonymous,
            'is_public': fb.is_public,
            'is_resolved': fb.is_resolved,
            'resolution_content': fb.resolution_content,
            'created_at': fb.created_at.isoformat()
        })

    # 提取知识点（保证提取过）
    kp_qs = KnowledgePoint.objects.filter(course=syllabus)
    if kp_qs.count() == 0:
        try:
            sync_knowledge_points(syllabus)
            kp_qs = KnowledgePoint.objects.filter(course=syllabus)
        except Exception:
            pass
    knowledge_points = [
        {'name': p.point_name, 'category': p.point_category or '其他'}
        for p in kp_qs
    ]

    return JsonResponse({
        'id': syllabus.id,
        'course_code': syllabus.course_code,
        'course_name': syllabus.course_name,
        'course_name_en': syllabus.course_name_en,
        'credit': str(syllabus.credit),
        'semester': syllabus.get_semester_display(),
        'semester_raw': syllabus.semester,
        'grade': syllabus.grade,
        'major': syllabus.major,
        'teacher_name': syllabus.teacher_name,
        'course_objectives': syllabus.course_objectives,
        'course_content': syllabus.course_content,
        'teaching_methods': syllabus.teaching_methods,
        'assessment_methods': syllabus.assessment_methods,
        'reference_materials': syllabus.reference_materials,
        'prerequisite_courses': syllabus.prerequisite_courses,
        'file_url': request.build_absolute_uri(syllabus.file_upload.url) if syllabus.file_upload else None,
        'created_at': syllabus.created_at.isoformat(),
        'updated_at': syllabus.updated_at.isoformat(),
        'teachers': teachers,
        'feedbacks': feedbacks,
        'feedback_count': syllabus.anonymousfeedback_set.count(),
        'knowledge_points': knowledge_points
    })

@csrf_exempt
def syllabus_delete(request, syllabus_id):
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    permission_result = check_permission(request, 'teacher')
    if isinstance(permission_result, JsonResponse):
        return permission_result
    profile = permission_result[1] if isinstance(permission_result, tuple) else None

    try:
        syllabus = CourseSyllabus.objects.get(id=syllabus_id)
        # 所有权校验：admin 可以删所有，教师只能删自己上传的（按 username 聚合）
        if profile and profile.role == 'teacher':
            if syllabus.created_by is None or syllabus.created_by.username != profile.username:
                return JsonResponse({'error': '无权删除其他老师上传的课程大纲'}, status=403)
        syllabus.delete()
        return JsonResponse({'success': True})
    except CourseSyllabus.DoesNotExist:
        return JsonResponse({'error': '课程大纲不存在'}, status=404)

# ==================== 课程查重 API ====================

def calculate_similarity(text1, text2):
    return SequenceMatcher(None, text1, text2).ratio() * 100


# 智能科学与技术领域知识点关键词词典（按类别组织，用于知识点维度查重）
KNOWLEDGE_KEYWORDS = {
    '数学基础': [
        '微积分', '极限', '导数', '微分', '积分', '梯度', '泰勒展开', '偏导数',
        '矩阵', '向量', '特征值', '特征向量', '奇异值分解', 'SVD', '行列式',
        '线性变换', '正交', '二次型', '矩阵分解', '概率', '条件概率', '贝叶斯',
        '贝叶斯定理', '最大似然估计', '高斯分布', '正态分布', '假设检验',
        '方差分析', '回归分析', '随机变量', '期望', '方差', '协方差',
        '大数定律', '中心极限定理', '参数估计', '贝叶斯估计',
    ],
    '数据结构与算法': [
        '算法复杂度', '时间复杂度', '空间复杂度', '递归', '排序', '冒泡排序',
        '快速排序', '归并排序', '堆排序', '二分查找', '哈希表', '链表', '栈',
        '队列', '二叉树', '二叉搜索树', '平衡树', '堆', '图', '邻接矩阵',
        '邻接表', '深度优先搜索', '广度优先搜索', '最短路径', '最小生成树',
        '动态规划', '贪心算法', '回溯', '分支限界', '分治', 'NP完全',
        '启发式搜索', '遗传算法', '模拟退火', '网络流', '旅行商问题',
    ],
    '人工智能经典': [
        '人工智能', '智能Agent', '搜索', '启发式搜索', 'A*算法', '博弈搜索',
        'Minimax', 'Alpha-Beta剪枝', '知识表示', '推理', '谓词逻辑',
        '产生式规则', '语义网络', '本体', '不确定性推理', '贝叶斯网络',
        '模糊推理', '规划', '专家系统', '人工智能伦理',
    ],
    '机器学习': [
        '机器学习', '监督学习', '无监督学习', '线性回归', '逻辑回归',
        '损失函数', '梯度下降', '正则化', 'L1正则化', 'L2正则化', '交叉验证',
        '过拟合', '偏差-方差', '决策树', '随机森林', '支持向量机', 'SVM',
        '核方法', '核函数', '朴素贝叶斯', 'K近邻', 'KNN', 'K-Means',
        '层次聚类', '聚类', 'PCA', 't-SNE', '降维', '特征提取', '特征选择',
        '集成学习', 'Boosting', 'XGBoost', '强化学习', 'Q-Learning',
        '分类', '回归', '模型评估', 'scikit-learn',
    ],
    '深度学习': [
        '深度学习', '神经网络', '感知机', '多层感知机', 'MLP', '前向传播',
        '反向传播', '激活函数', 'ReLU', 'Sigmoid', 'Tanh', '交叉熵',
        '优化算法', 'SGD', 'Adam', 'Dropout', 'BatchNorm', '批归一化',
        '卷积神经网络', 'CNN', '卷积层', '池化层', 'LeNet', 'ResNet',
        '循环神经网络', 'RNN', 'LSTM', 'GRU', '注意力机制', '自注意力',
        'Transformer', '生成对抗网络', 'GAN', '自编码器', 'VAE',
        '迁移学习', '微调', 'PyTorch', 'TensorFlow',
    ],
    '模式识别': [
        '模式识别', '贝叶斯决策', '概率密度估计', '参数估计', '非参数估计',
        '线性判别', 'Fisher线性判别', 'Fisher判别', 'LDA', '近邻法则',
        '隐马尔可夫模型', 'HMM', '特征工程', '图像识别', '语音识别',
    ],
    '计算机视觉': [
        '计算机视觉', '图像处理', '图像采集', '图像数字化', '灰度化',
        '滤波', '边缘检测', 'Sobel', 'Canny', '图像特征', 'HOG', 'SIFT',
        'SURF', '图像分类', '目标检测', 'R-CNN', 'YOLO', 'SSD',
        '图像分割', '语义分割', 'FCN', 'U-Net', '实例分割', 'Mask R-CNN',
        '人脸识别', '姿态估计', '视觉Transformer', 'ViT', '目标跟踪', 'OpenCV',
    ],
    '自然语言处理': [
        '自然语言处理', '中文分词', '词性标注', '命名实体识别', 'NER',
        '词向量', 'Word2Vec', 'GloVe', '句法分析', '依存句法', '成分句法',
        '文本分类', '情感分析', '序列标注', '机器翻译', 'Seq2Seq',
        '预训练语言模型', 'BERT', 'GPT', '问答系统', '对话系统',
        '大语言模型', 'Prompt工程', 'HuggingFace', 'Transformers',
    ],
}


def extract_knowledge_points(syllabus):
    """
    从课程大纲中提取知识点。
    采用「领域关键词匹配 + 智能分词补充」策略：
    1. 优先匹配领域关键词词典中的术语（高质量）
    2. 补充大纲中所有专业术语，用于建立课程关联
    返回 (知识点列表, 类别映射)
    """
    import re

    text = f"{syllabus.course_objectives or ''} {syllabus.course_content or ''}"
    if not text.strip():
        return [], {}

    found_points = {}  # point_name -> category

    # 1. 领域关键词匹配（精确）—— 优先级最高
    for category, keywords in KNOWLEDGE_KEYWORDS.items():
        for kw in keywords:
            if kw in text and kw not in found_points:
                found_points[kw] = category

    # 2. 提取课程内容中所有有价值的专业术语
    # 专业术语特征词
    tech_patterns = (
        '算法', '模型', '方法', '理论', '系统', '函数', '变换',
        '分解', '估计', '检验', '分析', '网络', '架构', '结构',
        '学习', '训练', '优化', '计算', '处理', '识别', '分类',
        '回归', '聚类', '降维', '检测', '分割', '合成', '生成',
        '导数', '微分', '积分', '矩阵', '向量', '概率', '统计',
        '神经网络', '深度学习', '机器学习', '人工智能',
        '计算机', '算法', '复杂度', '递归', '排序', '查找',
        '数据结构', '编程语言', '面向对象', '数据库',
        '图像处理', '自然语言', '语音识别', '模式识别',
    )
    
    # 需要过滤的前缀（纯教学措辞，非知识点）
    bad_prefixes = ('掌握', '理解', '学习', '了解', '熟悉', '培养', '运用', '使用',
                    '能够', '能运用', '具备', '建立', '提高', '加强', '重点', '强调',
                    '讲解', '介绍', '包括', '以及', '结合', '通过', '采用', '基于',
                    '要求', '目标', '内容', '方式', '过程', '结果', '主要')
    
    # 需要过滤的后缀（章节标题、概述类）
    bad_suffixes = ('第一章', '第二章', '第三章', '第四章', '第五章', '第六章',
                    '第七章', '第八章', '第九章', '第十章', '概述', '简介', '入门',
                    '概览', '导论', '前言', '绪论', '基础', '知识', '内容', '方法')
    
    # 完全由虚词组成的词
    bad_only = ('的', '了', '和', '与', '及', '或', '在', '为', '是', '对',
                '从', '由', '其', '该', '可', '等', '类', '化', '性', '中',
                '上', '下', '内', '外', '间', '后', '前', '进行', '通过',
                '学习', '掌握', '理解', '了解', '熟悉')

    tokens = re.split(r'[，,。.；;：:、（）()\s\n\r\t]+', text)
    for token in tokens:
        token = token.strip()
        if not (2 <= len(token) <= 10):
            continue
        if token.isdigit():
            continue
        if token.isascii() and len(token) <= 2:
            continue
        if token.startswith('第') and any(c.isdigit() for c in token):
            continue
        # 过滤教学措辞开头
        if any(token.startswith(v) for v in bad_prefixes):
            continue
        # 过滤章节标题
        if any(token.endswith(s) for s in bad_suffixes):
            continue
        # 如果 token 完全由坏词组成，跳过
        if all(c in ''.join(bad_only) for c in token):
            continue
        # 必须包含专业术语特征之一（避免噪声）
        has_tech = any(p in token for p in tech_patterns)
        if not has_tech:
            continue
        # 检查是否已经存在
        if token not in found_points:
            found_points[token] = '其他'

    return list(found_points.keys()), found_points


def sync_knowledge_points(syllabus):
    """提取并持久化知识点到 KnowledgePoint 表，返回知识点名称列表"""
    points, point_map = extract_knowledge_points(syllabus)

    # 清空原有知识点再写入
    KnowledgePoint.objects.filter(course=syllabus).delete()
    for point_name in points:
        KnowledgePoint.objects.create(
            course=syllabus,
            point_name=point_name,
            point_category=point_map.get(point_name, '其他'),
            importance=60,
        )
    return points


@csrf_exempt
def extract_knowledge_points_view(request):
    """提取课程知识点 API：支持单门（syllabus_id）或全部（不传）"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = {}

    syllabus_id = data.get('syllabus_id')
    if syllabus_id:
        syllabi = CourseSyllabus.objects.filter(id=syllabus_id)
    else:
        syllabi = CourseSyllabus.objects.all()

    results = []
    total_points = 0
    for s in syllabi:
        points = sync_knowledge_points(s)
        results.append({
            'course_id': s.id,
            'course_code': s.course_code,
            'course_name': s.course_name,
            'points_count': len(points),
            'points': points[:20],  # 仅返回前20个用于预览
        })
        total_points += len(points)

    return JsonResponse({
        'success': True,
        'courses_count': len(results),
        'total_points': total_points,
        'results': results,
    })


def course_knowledge_points(request, syllabus_id):
    """获取某门课程的全部知识点"""
    try:
        syllabus = CourseSyllabus.objects.get(id=syllabus_id)
    except CourseSyllabus.DoesNotExist:
        return JsonResponse({'error': '课程不存在'}, status=404)

    points = KnowledgePoint.objects.filter(course=syllabus).order_by('-importance', 'point_name')
    data = [{
        'id': p.id,
        'point_name': p.point_name,
        'point_category': p.point_category,
        'importance': p.importance,
    } for p in points]

    # 按类别分组统计
    categories = {}
    for p in data:
        cat = p['point_category'] or '其他'
        categories[cat] = categories.get(cat, 0) + 1

    return JsonResponse({
        'course_id': syllabus.id,
        'course_name': syllabus.course_name,
        'points': data,
        'points_count': len(data),
        'categories': categories,
    })


@csrf_exempt
def duplicate_check_for_syllabus(request):
    """单门课程与全库课程的内容查重（教师端）。

    支持三种入参（按优先级）：
      1) syllabus_id：从库里选一门已有课程，对其内容做查重；
      2) course_content + course_code/course_name：教师直接粘贴文本内容；
      3) file_upload：教师上传文档/文本文件，读取其内容后查重。

    返回：{
      'queried_course': { course_code, course_name, points_count, points: [...] },
      'duplicates': [ { course_id, course_code, course_name, similarity_score, kp_jaccard,
                        text_similarity, overlap_count, overlap_points:[{name,category}],
                        course_points_count, queried_points_count, is_high_overlap } ],
      'summary': { total_compared, overlapped_courses, high_risk_count, risk_level }
    }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    permission_result = check_permission(request, 'teacher')
    if isinstance(permission_result, JsonResponse):
        return permission_result
    # check_permission 成功时返回 (None, profile)
    profile = permission_result[1] if isinstance(permission_result, tuple) else None

    try:
        content_type_header = request.headers.get('Content-Type', '')
        if 'multipart/form-data' in content_type_header:
            payload = request.POST
            files = request.FILES
        elif 'application/json' in content_type_header:
            payload = json.loads(request.body) if request.body else {}
            files = {}
        else:
            try:
                payload = json.loads(request.body) if request.body else {}
            except Exception:
                payload = request.POST
            files = {}

        syllabus_id = payload.get('syllabus_id')
        course_code = (payload.get('course_code') or '').strip()
        course_name = (payload.get('course_name') or '').strip()
        objectives = (payload.get('course_objectives') or '').strip()
        content_text = (payload.get('course_content') or payload.get('content') or '').strip()
        uploaded_file = files.get('file') or (files.getlist('file')[0] if (hasattr(files, 'getlist') and files.getlist('file')) else None) or files.get('file_upload')

        # ---------- 收集待查重课程资料 ----------
        queried_meta = {}
        if syllabus_id:
            try:
                syllabus = CourseSyllabus.objects.get(id=int(syllabus_id))
                course_code = course_code or syllabus.course_code or ''
                course_name = course_name or syllabus.course_name or ''
                objectives = objectives or (syllabus.course_objectives or '')
                content_text = content_text or (syllabus.course_content or '')
                queried_meta = {
                    'syllabus_id': syllabus.id,
                    'course_code': syllabus.course_code,
                    'course_name': syllabus.course_name,
                    'major': syllabus.major,
                    'grade': syllabus.grade,
                    'semester': syllabus.get_semester_display() if syllabus.semester else '',
                }
            except (CourseSyllabus.DoesNotExist, ValueError, TypeError):
                return JsonResponse({'error': '指定的课程不存在'}, status=404)
        else:
            # 支持上传文件：读取纯文本/pdf/docx 内容的最简单方式（纯文本尝试）
            if uploaded_file is not None:
                raw_bytes = uploaded_file.read()
                try:
                    content_text = raw_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        content_text = raw_bytes.decode('gbk')
                    except Exception:
                        content_text = raw_bytes.decode('utf-8', errors='ignore')
                course_name = course_name or uploaded_file.name

            if not content_text and not objectives:
                return JsonResponse({'error': '请提供课程内容：选择已有课程、粘贴大纲文字或上传文件'}, status=400)
            if not course_name:
                return JsonResponse({'error': '请填写课程名称'}, status=400)

        # ---------- 提取待查重课程知识点 ----------
        class TempSyllabus:
            def __init__(self, objectives, content):
                self.course_objectives = objectives
                self.course_content = content

        temp_sy = TempSyllabus(objectives, content_text)
        try:
            q_points_list, q_points_map = extract_knowledge_points(temp_sy)
        except Exception as e:
            logger.warning(f"extract_knowledge_points for query failed: {e}")
            q_points_list, q_points_map = [], {}
        q_points_set = set(q_points_list)

        queried_course = {
            'course_code': course_code or '',
            'course_name': course_name or '待查重课程',
            'points_count': len(q_points_set),
            'knowledge_points': [{'name': n, 'category': q_points_map.get(n, '其他')}
                                 for n in sorted(q_points_set)[:50]],
            'major': queried_meta.get('major', ''),
            'grade': queried_meta.get('grade', ''),
            'semester': queried_meta.get('semester', ''),
        }

        if len(q_points_set) == 0:
            return JsonResponse({
                'queried_course': queried_course,
                'duplicates': [],
                'summary': {
                    'total_compared': 0,
                    'overlapped_courses': 0,
                    'high_risk_count': 0,
                    'risk_level': 'low',
                    'hint': '未从输入内容中检测到知识点，请补充课程目标或章节内容后重试',
                },
            })

        # ---------- 全库准备（排除当前教师的所有课程） ----------
        # 教师提交的课程只与其他老师上传的课程进行比对，杜绝自己多门课之间互相比
        all_syllabi_qs = CourseSyllabus.objects.all()
        if profile and profile.role == 'teacher':
            # 1) 核心：与 syllabus_list 对齐，按 created_by__username 聚合所有归属该教师的课程
            self_qs_core = CourseSyllabus.objects.none()
            if profile.username:
                self_qs_core = CourseSyllabus.objects.filter(created_by__username=profile.username)

            # 2) 兜底：按 FK 直接命中 / user_id 命中也一起收进来
            self_qs_extra = CourseSyllabus.objects.none()
            if hasattr(profile, 'pk'):
                self_qs_extra = self_qs_extra | CourseSyllabus.objects.filter(created_by=profile)
            if profile.user_id:
                self_qs_extra = self_qs_extra | CourseSyllabus.objects.filter(created_by__user_id=profile.user_id)

            self_ids = set(self_qs_core.values_list('id', flat=True)) | set(self_qs_extra.values_list('id', flat=True))

            # 3) teacher_name 兜底：把上述"自己的课"中出现过的教师姓名全部收集，再按 teacher_name 排除
            self_teacher_names = list(
                CourseSyllabus.objects.filter(id__in=self_ids)
                .exclude(teacher_name='').exclude(teacher_name__isnull=True)
                .values_list('teacher_name', flat=True).distinct()
            )
            q_exclude = Q(id__in=self_ids)
            if self_teacher_names:
                q_exclude = q_exclude | Q(teacher_name__in=self_teacher_names)

            all_syllabi_qs = all_syllabi_qs.exclude(q_exclude)

            # 若是已有课程查重，再排除自身ID（防止自身精确命中，理论上上面已经排除，再兜底一次）
            current_syllabus_id = queried_meta.get('syllabus_id')
            if current_syllabus_id:
                all_syllabi_qs = all_syllabi_qs.exclude(id=current_syllabus_id)
        elif profile and profile.role == 'admin':
            # admin 仅排除当前选中课程自身
            current_syllabus_id = queried_meta.get('syllabus_id')
            if current_syllabus_id:
                all_syllabi_qs = all_syllabi_qs.exclude(id=current_syllabus_id)
        else:
            # 未识别身份时仅排除自身选中的课程
            exclude_id = queried_meta.get('syllabus_id')
            if exclude_id:
                all_syllabi_qs = all_syllabi_qs.exclude(id=exclude_id)
        all_syllabi = list(all_syllabi_qs)

        # 保证库中课程都提取过知识点
        library_map = {}
        for s in all_syllabi:
            existing = KnowledgePoint.objects.filter(course=s)
            if existing.count() == 0:
                try:
                    sync_knowledge_points(s)
                    existing = KnowledgePoint.objects.filter(course=s)
                except Exception as e:
                    logger.warning(f"sync_knowledge_points for course {s.id} failed: {e}")
                    existing = []
            library_map[s.id] = {
                'syllabus': s,
                'points': {p.point_name: (p.point_category or '其他') for p in existing},
            }

        queried_full_text = f"{objectives} {content_text}"

        duplicates = []
        for s_id, info in library_map.items():
            lib_points = info['points']
            lib_set = set(lib_points.keys())
            overlap = q_points_set & lib_set
            union = q_points_set | lib_set

            kp_jaccard = (len(overlap) / len(union) * 100) if union else 0.0
            try:
                s = info['syllabus']
                lib_full_text = f"{s.course_objectives or ''} {s.course_content or ''}"
                text_sim = calculate_similarity(queried_full_text, lib_full_text)
            except Exception:
                text_sim = 0.0
            combined_score = kp_jaccard * 0.7 + text_sim * 0.3

            # 触发阈值：Jaccard >= 8% 或重叠点 >= 3
            if kp_jaccard < 8 and len(overlap) < 3:
                continue

            overlap_detail = []
            for pt in sorted(overlap):
                cat = q_points_map.get(pt) or lib_points.get(pt) or '其他'
                overlap_detail.append({'name': pt, 'category': cat})

            s = info['syllabus']
            duplicates.append({
                'compared_course_id': s.id,
                'compared_course_code': s.course_code or '',
                'compared_course_name': s.course_name or '',
                'teacher_name': s.teacher_name or '',
                'major': s.major or '',
                'grade': s.grade or '',
                'overall_similarity': round(combined_score, 2),
                'similarity_score': round(combined_score, 2),
                'knowledge_similarity': round(kp_jaccard, 2),
                'kp_jaccard': round(kp_jaccard, 2),
                'text_similarity': round(text_sim, 2),
                'overlap_count': len(overlap),
                'overlap_points': overlap_detail,
                'compared_points_count': len(lib_set),
                'queried_points_count': len(q_points_set),
                'is_high_overlap': combined_score >= 60,
                'high_risk': combined_score >= 60,
            })

        duplicates.sort(key=lambda d: d['similarity_score'], reverse=True)

        high_risk_count = sum(1 for d in duplicates if d['is_high_overlap'])
        overlapped_courses = len(duplicates)
        if high_risk_count > 0:
            risk_level = 'high'
        elif overlapped_courses > 0:
            risk_level = 'medium'
        else:
            risk_level = 'low'

        return JsonResponse({
            'queried_course': queried_course,
            'duplicates': duplicates,
            'summary': {
                'total_compared': len(library_map),
                'overlapped_courses': overlapped_courses,
                'high_risk_count': high_risk_count,
                'risk_level': risk_level,
            },
        })

    except Exception as e:
        logger.error(f"duplicate_check_for_syllabus error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# ==================== 课程关联 API ====================

def course_relations(request):
    course_id = request.GET.get('course_id', '')
    
    if course_id:
        relations = CourseRelation.objects.filter(Q(source_course_id=course_id) | Q(target_course_id=course_id))
    else:
        relations = CourseRelation.objects.all()
    
    result = []
    for r in relations:
        result.append({
            'id': r.id,
            'source_course_id': r.source_course.id,
            'source_course_code': r.source_course.course_code,
            'source_course_name': r.source_course.course_name,
            'target_course_id': r.target_course.id,
            'target_course_code': r.target_course.course_code,
            'target_course_name': r.target_course.course_name,
            'relation_type': r.get_relation_type_display(),
            'relation_type_raw': r.relation_type,
            'description': r.description,
            'strength': r.strength,
            'verified': r.verified
        })

    return JsonResponse({'relations': result})

@csrf_exempt
def course_relation_create(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        
        source_id = data.get('source_course_id')
        target_id = data.get('target_course_id')
        relation_type = data.get('relation_type')
        
        if not source_id or not target_id or not relation_type:
            return JsonResponse({'error': '源课程、目标课程和关联类型不能为空'}, status=400)
        
        source = CourseSyllabus.objects.get(id=source_id)
        target = CourseSyllabus.objects.get(id=target_id)
        
        relation = CourseRelation.objects.create(
            source_course=source,
            target_course=target,
            relation_type=relation_type,
            description=data.get('description', ''),
            strength=data.get('strength', 50),
            verified=data.get('verified', False)
        )
        
        return JsonResponse({'success': True, 'relation_id': relation.id})
    
    except CourseSyllabus.DoesNotExist:
        return JsonResponse({'error': '课程不存在'}, status=404)
    except Exception as e:
        logger.error(f"Relation create error: {e}")
        return JsonResponse({'error': str(e)}, status=500)

def course_relation_graph(request):
    syllabi = CourseSyllabus.objects.all()
    relations = CourseRelation.objects.all()

    # 按课程代码前缀推断层级分组（用于节点着色）
    def course_group(code):
        if not code:
            return 'other'
        code = code.upper()
        if code.startswith('IST1'):
            return 'basic'      # 基础课
        if code.startswith('IST2'):
            return 'core'       # 专业核心
        if code.startswith('IST3'):
            return 'applied'    # 专业方向/应用
        if code.startswith('CS'):
            return 'core'
        return 'other'

    group_labels = {
        'basic': '基础课',
        'core': '专业核心',
        'applied': '专业方向',
        'other': '其他',
    }

    nodes = []
    for s in syllabi:
        group = course_group(s.course_code)
        nodes.append({
            'id': s.id,
            'label': s.course_name,
            'code': s.course_code,
            'semester': s.get_semester_display(),
            'semester_raw': s.semester,
            'grade': s.grade,
            'major': s.major,
            'credit': str(s.credit),
            'group': group,
            'group_label': group_labels.get(group, '其他'),
            'points_count': KnowledgePoint.objects.filter(course=s).count(),
        })

    edges = []
    for r in relations:
        edges.append({
            'id': r.id,
            'source': r.source_course.id,
            'target': r.target_course.id,
            'source_label': r.source_course.course_name,
            'target_label': r.target_course.course_name,
            'relation': r.get_relation_type_display(),
            'relation_type': r.relation_type,
            'strength': r.strength,
            'verified': r.verified,
            'description': r.description or '',
        })

    return JsonResponse({
        'nodes': nodes,
        'edges': edges,
        'groups': group_labels,
    })


# 知识点先修依赖映射： prerequisite_kp -> [dependent_kps]
# 表示"先修知识点"是"依赖知识点"的基础
KP_PREREQUISITES = {
    # 数学基础 → 机器学习/深度学习
    '梯度': ['梯度下降', '反向传播', '优化算法', 'SGD', 'Adam'],
    '导数': ['梯度', '梯度下降', '偏导数'],
    '极限': ['导数', '梯度'],
    '矩阵': ['神经网络', '卷积神经网络', '注意力机制', '特征值', '奇异值分解', '主成分分析', '因子分析', '判别分析'],
    '向量': ['词向量', '神经网络', '支持向量机', 'SVM', '注意力机制', 'Word2Vec', '主成分分析', '因子分析', '判别分析'],
    '特征值': ['PCA', '降维', '奇异值分解', 'SVD', '主成分分析', '因子分析', '判别分析'],
    '特征向量': ['PCA', '降维', '奇异值分解', 'SVD'],
    '奇异值分解': ['PCA', '降维'],
    'SVD': ['PCA', '降维'],
    '概率': ['贝叶斯', '朴素贝叶斯', '贝叶斯网络', '隐马尔可夫模型', 'HMM', '高斯分布', '条件概率'],
    '条件概率': ['贝叶斯', '朴素贝叶斯', '贝叶斯定理'],
    '贝叶斯': ['朴素贝叶斯', '贝叶斯网络', '贝叶斯决策', '贝叶斯定理'],
    '贝叶斯定理': ['朴素贝叶斯', '贝叶斯网络', '贝叶斯决策'],
    '高斯分布': ['概率密度估计', '贝叶斯决策', '参数估计'],
    '最大似然估计': ['逻辑回归', '损失函数', '参数估计'],
    '假设检验': ['模型评估', '交叉验证'],
    '方差': ['偏差-方差', '正则化', 'BatchNorm', '批归一化', '方差分析', '主成分分析', '因子分析'],
    '协方差': ['主成分分析', '因子分析', '判别分析', '聚类分析'],
    '正态分布': ['主成分分析', '因子分析', '判别分析', '回归分析'],
    '回归分析': ['回归', '主成分分析', '因子分析'],
    '聚类分析': ['聚类', '主成分分析'],
    '判别分析': ['分类', '线性判别', 'Fisher判别', '主成分分析'],
    '主成分分析': ['因子分析', '判别分析'],
    '因子分析': ['主成分分析', '对应分析'],
    '对应分析': ['因子分析'],
    '对数线性模型': ['回归分析', '方差分析'],
    # 机器学习内部依赖
    '梯度下降': ['反向传播', '优化算法', 'SGD', 'Adam', '损失函数'],
    '损失函数': ['反向传播', '交叉熵', '梯度下降'],
    '线性回归': ['逻辑回归', '损失函数', '梯度下降'],
    '逻辑回归': ['分类', '损失函数'],
    '监督学习': ['分类', '回归', '线性回归', '逻辑回归', '决策树'],
    '无监督学习': ['聚类', 'K-Means', '层次聚类', '降维'],
    '分类': ['图像分类', '文本分类', '情感分析', 'SVM', '支持向量机'],
    '聚类': ['K-Means', '层次聚类'],
    'PCA': ['降维', 't-SNE'],
    '正则化': ['Dropout', 'L1正则化', 'L2正则化'],
    '过拟合': ['正则化', 'Dropout', '交叉验证'],
    '交叉验证': ['模型评估'],
    '决策树': ['随机森林', '集成学习', 'XGBoost'],
    '集成学习': ['随机森林', 'Boosting', 'XGBoost'],
    '支持向量机': ['SVM', '核方法', '核函数'],
    'SVM': ['核方法', '核函数'],
    # 机器学习 → 深度学习
    '机器学习': ['深度学习', '模式识别', '神经网络'],
    '神经网络': ['深度学习', '卷积神经网络', 'CNN', '循环神经网络', 'RNN', '反向传播', '感知机'],
    '感知机': ['神经网络', '多层感知机', 'MLP'],
    '多层感知机': ['MLP', '神经网络', '深度学习'],
    # 深度学习内部
    '反向传播': ['卷积神经网络', 'CNN', '循环神经网络', 'RNN', 'ResNet', '梯度下降'],
    '激活函数': ['ReLU', 'Sigmoid', 'Tanh', '神经网络'],
    'ReLU': ['ResNet', '卷积神经网络', 'CNN'],
    'Dropout': ['ResNet', '正则化'],
    'BatchNorm': ['ResNet', '批归一化'],
    '优化算法': ['SGD', 'Adam', '梯度下降'],
    '梯度下降': ['反向传播', '优化算法', 'SGD', 'Adam'],
    # 深度学习 → CV/NLP
    '卷积神经网络': ['CNN', '目标检测', '图像分割', 'ResNet', 'YOLO', '图像分类', '视觉Transformer', 'ViT'],
    'CNN': ['目标检测', '图像分割', 'ResNet', 'YOLO', '图像分类', '视觉Transformer', 'ViT'],
    '循环神经网络': ['RNN', 'LSTM', 'GRU', 'Seq2Seq', '机器翻译'],
    'RNN': ['LSTM', 'GRU', 'Seq2Seq', '机器翻译'],
    'LSTM': ['Seq2Seq', '机器翻译'],
    '注意力机制': ['Transformer', '自注意力', 'BERT', 'GPT', '视觉Transformer', 'ViT'],
    '自注意力': ['Transformer', 'BERT', 'GPT'],
    'Transformer': ['BERT', 'GPT', '视觉Transformer', 'ViT', '预训练语言模型'],
    '词向量': ['Word2Vec', 'GloVe', 'BERT', '预训练语言模型'],
    'Word2Vec': ['BERT', '预训练语言模型', 'GloVe'],
    'Seq2Seq': ['机器翻译', '注意力机制', 'Transformer'],
    '迁移学习': ['微调', 'BERT', '预训练语言模型'],
    # 模式识别关联
    '贝叶斯决策': ['朴素贝叶斯', '贝叶斯网络', '分类'],
    '参数估计': ['最大似然估计', '概率密度估计', '贝叶斯估计'],
    '特征提取': ['特征选择', 'PCA', '降维', 'HOG', 'SIFT', '卷积神经网络', 'CNN'],
    'Fisher判别': ['LDA', '线性判别', '特征选择'],
    '线性判别': ['LDA', 'Fisher判别', '特征选择'],
    '隐马尔可夫模型': ['HMM', '序列标注', '命名实体识别', 'NER'],
    'K-Means': ['聚类', '层次聚类'],
    # NLP 特有
    '中文分词': ['词性标注', '命名实体识别', 'NER'],
    '命名实体识别': ['NER', '序列标注'],
    '预训练语言模型': ['BERT', 'GPT', '大语言模型'],
    '大语言模型': ['GPT', 'Prompt工程', '问答系统', '对话系统'],
    # CV 特有
    '图像处理': ['边缘检测', '图像分类', '滤波', '灰度化'],
    '边缘检测': ['Sobel', 'Canny', '图像特征'],
    '图像特征': ['HOG', 'SIFT', 'SURF', '特征提取'],
    '目标检测': ['YOLO', 'R-CNN', 'SSD'],
    '图像分割': ['语义分割', 'FCN', 'U-Net', '实例分割', 'Mask R-CNN'],
    # 算法/数据结构关联
    '算法复杂度': ['时间复杂度', '空间复杂度', '动态规划'],
    '动态规划': ['最长公共子序列', '背包问题'],
    '搜索': ['启发式搜索', 'A*算法', '深度优先搜索', '广度优先搜索'],
    '图': ['最短路径', '邻接矩阵', '邻接表', '深度优先搜索', '广度优先搜索'],
    '排序': ['快速排序', '归并排序', '堆排序'],
    '二叉树': ['二叉搜索树', '堆', '平衡树'],
    # AI 经典
    '启发式搜索': ['A*算法', '博弈搜索'],
    'A*算法': ['博弈搜索', 'Minimax'],
    '知识表示': ['推理', '专家系统', '语义网络'],
    '推理': ['不确定性推理', '贝叶斯网络', '专家系统'],
}


def course_knowledge_graph(request):
    """
    知识点级别的课程关联图谱数据。
    返回分层课程（含知识点列表）+ 知识点级连接（哪个课的哪个知识点 → 哪个课的哪个知识点）。
    """
    syllabi = list(CourseSyllabus.objects.all())
    relations = list(CourseRelation.objects.all())

    def course_group(code):
        if not code:
            return 'other'
        code = code.upper()
        if code.startswith('IST1'):
            return 'basic'
        if code.startswith('IST2'):
            return 'core'
        if code.startswith('IST3'):
            return 'applied'
        if code.startswith('CS'):
            return 'core'
        return 'other'

    group_labels = {
        'basic': '基础课', 'core': '专业核心', 'applied': '专业方向', 'other': '其他',
    }
    group_order = {'basic': 0, 'core': 1, 'applied': 2, 'other': 3}

    # 收集每门课的知识点 {course_id: {kp_name: category}}
    course_kps = {}
    for s in syllabi:
        kps = {}
        for p in KnowledgePoint.objects.filter(course=s):
            kps[p.point_name] = p.point_category or '其他'
        course_kps[s.id] = kps

    # 课程信息
    courses = {}
    for s in syllabi:
        group = course_group(s.course_code)
        kps = course_kps.get(s.id, {})
        # 知识点列表（按类别排序，重要的在前）
        kp_list = sorted(
            [{'name': k, 'category': v} for k, v in kps.items()],
            key=lambda x: (0 if x['category'] != '其他' else 1, x['name'])
        )
        courses[s.id] = {
            'id': s.id,
            'name': s.course_name,
            'code': s.course_code,
            'group': group,
            'group_label': group_labels.get(group, '其他'),
            'knowledge_points': kp_list[:15],  # 限制每门课显示15个知识点
            'kp_count': len(kps),
        }

    # 计算知识点级连接
    kp_connections = []
    seen_pairs = set()  # 去重 (source_course, source_kp, target_course, target_kp)

    # 1. 基于课程级先修关系 + KP_PREREQUISITES 的知识点连接
    for r in relations:
        if r.relation_type != 'prerequisite':
            continue

        src_id = r.source_course.id
        tgt_id = r.target_course.id
        src_kps = set(course_kps.get(src_id, {}).keys())
        tgt_kps = set(course_kps.get(tgt_id, {}).keys())

        for src_kp in src_kps:
            dependents = KP_PREREQUISITES.get(src_kp, [])
            for tgt_kp in dependents:
                if tgt_kp in tgt_kps and src_kp != tgt_kp:
                    key = (src_id, src_kp, tgt_id, tgt_kp)
                    if key not in seen_pairs:
                        seen_pairs.add(key)
                        kp_connections.append({
                            'source_course': src_id,
                            'target_course': tgt_id,
                            'source_kp': src_kp,
                            'target_kp': tgt_kp,
                            'connection_type': 'prerequisite',
                            'relation_type': r.relation_type,
                            'relation_label': r.get_relation_type_display(),
                        })

    # 2. 自动关联：相同知识点连接（跨课程共享的知识点）
    # 遍历所有课程对，找到共享的知识点
    course_list = list(syllabi)
    for i, s1 in enumerate(course_list):
        for j, s2 in enumerate(course_list):
            if i >= j:
                continue
            if s1.id == s2.id:
                continue

            group1 = course_group(s1.course_code)
            group2 = course_group(s2.course_code)

            kps1 = set(course_kps.get(s1.id, {}).keys())
            kps2 = set(course_kps.get(s2.id, {}).keys())
            shared_kps = kps1 & kps2

            if not shared_kps:
                continue

            src_id, tgt_id = s1.id, s2.id
            relation_label = '共享'

            if group_order[group1] < group_order[group2]:
                src_id, tgt_id = s1.id, s2.id
            elif group_order[group1] > group_order[group2]:
                src_id, tgt_id = s2.id, s1.id
            else:
                if s1.id < s2.id:
                    src_id, tgt_id = s1.id, s2.id
                else:
                    src_id, tgt_id = s2.id, s1.id

            for shared_kp in shared_kps:
                key = (src_id, shared_kp, tgt_id, shared_kp)
                if key not in seen_pairs:
                    seen_pairs.add(key)
                    kp_connections.append({
                        'source_course': src_id,
                        'target_course': tgt_id,
                        'source_kp': shared_kp,
                        'target_kp': shared_kp,
                        'connection_type': 'shared',
                        'relation_type': 'shared',
                        'relation_label': relation_label,
                    })

    # 按层级分组课程（用于分层布局）
    layers = {'basic': [], 'core': [], 'applied': [], 'other': []}
    for s in syllabi:
        group = course_group(s.course_code)
        layers[group].append(s.id)

    return JsonResponse({
        'courses': courses,
        'layers': layers,
        'group_labels': group_labels,
        'kp_connections': kp_connections,
        'total_courses': len(syllabi),
        'total_connections': len(kp_connections),
    })


@csrf_exempt
def course_relation_delete(request, relation_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        relation = CourseRelation.objects.get(id=relation_id)
        relation.delete()
        return JsonResponse({'success': True})
    except CourseRelation.DoesNotExist:
        return JsonResponse({'error': '关联不存在'}, status=404)

@csrf_exempt
def course_relation_verify(request, relation_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        relation = CourseRelation.objects.get(id=relation_id)
        relation.verified = True
        relation.save()
        return JsonResponse({'success': True})
    except CourseRelation.DoesNotExist:
        return JsonResponse({'error': '关联不存在'}, status=404)


# ==================== 匿名反馈 API ====================

def feedback_list(request):
    feedback_type = request.GET.get('feedback_type', '')
    is_resolved = request.GET.get('is_resolved', '')
    feedback_scope = request.GET.get('scope', 'all')
    course_id = request.GET.get('course_id', '')
    
    user_id = request.headers.get('X-User-ID', '')
    queryset = AnonymousFeedback.objects.all()
    
    if user_id:
        try:
            profile = UserProfile.objects.get(user_id=user_id)
            
            if profile.role == 'teacher':
                teaching_course_ids = [tc.course.id for tc in profile.teaching_courses.all()]
                created_course_ids = list(CourseSyllabus.objects.filter(created_by=profile).values_list('id', flat=True))
                all_my_course_ids = list(set(teaching_course_ids + created_course_ids))
                if feedback_scope == 'my_courses':
                    queryset = queryset.filter(
                        Q(is_public=False) & 
                        (Q(target_teacher=profile) | Q(related_course__id__in=all_my_course_ids))
                    )
                elif feedback_scope == 'public':
                    queryset = queryset.filter(is_public=True)
                else:
                    queryset = queryset.filter(
                        Q(is_public=True) |
                        (Q(is_public=False) & (Q(target_teacher=profile) | Q(related_course__id__in=all_my_course_ids)))
                    )
            elif profile.role == 'student':
                enrolled_course_ids = [sc.course.id for sc in profile.enrolled_courses.all()]
                if feedback_scope == 'my_courses':
                    queryset = queryset.filter(
                        Q(is_public=False) & Q(related_course__id__in=enrolled_course_ids)
                    )
                elif feedback_scope == 'public':
                    queryset = queryset.filter(is_public=True)
                else:
                    queryset = queryset.filter(
                        Q(is_public=True) |
                        (Q(is_public=False) & Q(related_course__id__in=enrolled_course_ids))
                    )
        except UserProfile.DoesNotExist:
            pass
    
    if feedback_type:
        queryset = queryset.filter(feedback_type=feedback_type)
    if is_resolved:
        queryset = queryset.filter(is_resolved=(is_resolved == 'true'))
    if course_id:
        queryset = queryset.filter(related_course_id=course_id)
    
    feedbacks = []
    for f in queryset:
        fb_data = {
            'id': f.id,
            'feedback_type': f.get_feedback_type_display(),
            'feedback_type_raw': f.feedback_type,
            'title': f.title,
            'content': f.content,
            'rating': f.rating,
            'severity': f.get_severity_display(),
            'severity_raw': f.severity,
            'tags': [t.strip() for t in f.tags.split(',') if t.strip()] if f.tags else [],
            'related_course': {
                'id': f.related_course.id,
                'course_code': f.related_course.course_code,
                'course_name': f.related_course.course_name,
                'teacher_name': f.related_course.teacher_name
            } if f.related_course else None,
            'is_anonymous': f.is_anonymous,
            'is_public': f.is_public,
            'is_resolved': f.is_resolved,
            'resolution_content': f.resolution_content,
            'image': f.image.url if f.image else None,
            'created_by_id': f.created_by.id if f.created_by else None,
            'created_at': f.created_at.isoformat(),
            'resolved_at': f.resolved_at.isoformat() if f.resolved_at else None
        }
        feedbacks.append(fb_data)
    
    return JsonResponse({'feedbacks': feedbacks})

@csrf_exempt
def feedback_create(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    permission_result = check_permission(request)
    if isinstance(permission_result, JsonResponse):
        return permission_result

    # 仅学生可提交反馈，教师/管理员仅可查看与处理
    _, profile = permission_result
    if profile.role != 'student':
        return JsonResponse({'error': '仅学生可提交反馈'}, status=403)

    try:
        # 支持 multipart/form-data（带图片）和 application/json 两种提交方式
        content_type = request.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            data = json.loads(request.body)
            files = {}
        else:
            data = request.POST
            files = request.FILES

        feedback_type = data.get('feedback_type', 'other')
        title = data.get('title', '')
        content = data.get('content', '')

        if not title or not content:
            return JsonResponse({'error': '标题和内容不能为空'}, status=400)

        related_course = None
        course_id = data.get('related_course') or data.get('related_course_id')
        if course_id:
            try:
                related_course = CourseSyllabus.objects.get(id=course_id)
            except CourseSyllabus.DoesNotExist:
                pass

        target_teacher = None
        teacher_id = data.get('target_teacher')
        if teacher_id:
            try:
                target_teacher = UserProfile.objects.get(user_id=teacher_id)
            except UserProfile.DoesNotExist:
                pass

        is_anonymous = data.get('is_anonymous', True)
        if isinstance(is_anonymous, str):
            is_anonymous = is_anonymous.lower() == 'true' or is_anonymous == 'on'
        is_public = data.get('is_public', False)
        if isinstance(is_public, str):
            is_public = is_public.lower() == 'true'

        feedback = AnonymousFeedback.objects.create(
            feedback_type=feedback_type,
            title=title,
            content=content,
            rating=int(data.get('rating', 5)) if data.get('rating') else 5,
            severity=data.get('severity', 'medium'),
            tags=data.get('tags', ''),
            related_course=related_course,
            target_teacher=target_teacher,
            is_anonymous=is_anonymous,
            is_public=is_public,
            image=files.get('image') if files else None,
            created_by=profile,
        )

        return JsonResponse({'success': True, 'feedback_id': feedback.id})

    except Exception as e:
        logger.error(f"Feedback create error: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def feedback_resolve(request, feedback_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        resolution_content = data.get('resolution_content', '')
        
        feedback = AnonymousFeedback.objects.get(id=feedback_id)
        
        user_id = request.headers.get('X-User-ID', '')
        if user_id:
            try:
                profile = UserProfile.objects.get(user_id=user_id)
                if profile.role in ['teacher', 'admin']:
                    teaching_course_ids = [tc.course.id for tc in profile.teaching_courses.all()]
                    created_course_ids = list(CourseSyllabus.objects.filter(created_by=profile).values_list('id', flat=True))
                    all_my_course_ids = list(set(teaching_course_ids + created_course_ids))
                    if feedback.related_course and feedback.related_course.id not in all_my_course_ids and feedback.target_teacher != profile and not feedback.is_public:
                        return JsonResponse({'error': '无权处理此反馈'}, status=403)
            except UserProfile.DoesNotExist:
                pass
        
        feedback.is_resolved = True
        feedback.resolution_content = resolution_content
        feedback.resolved_at = timezone.now()
        feedback.save()
        
        return JsonResponse({'success': True})
    
    except AnonymousFeedback.DoesNotExist:
        return JsonResponse({'error': '反馈不存在'}, status=404)

@csrf_exempt
def feedback_delete(request, feedback_id):
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        feedback = AnonymousFeedback.objects.get(id=feedback_id)
        
        user_id = request.headers.get('X-User-ID', '')
        if not user_id:
            return JsonResponse({'error': '请先登录'}, status=401)
        
        try:
            profile = UserProfile.objects.get(user_id=user_id)
            
            if profile.role == 'student':
                if feedback.created_by and feedback.created_by.user_id == user_id:
                    feedback.delete()
                    return JsonResponse({'success': True})
                else:
                    return JsonResponse({'error': '只能删除自己提交的反馈'}, status=403)
            else:
                return JsonResponse({'error': '教师/管理员不能删除学生反馈，可清除回复'}, status=403)
        
        except UserProfile.DoesNotExist:
            return JsonResponse({'error': '用户不存在'}, status=404)
    
    except AnonymousFeedback.DoesNotExist:
        return JsonResponse({'error': '反馈不存在'}, status=404)

@csrf_exempt
def feedback_clear_resolution(request, feedback_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        feedback = AnonymousFeedback.objects.get(id=feedback_id)
        
        user_id = request.headers.get('X-User-ID', '')
        if not user_id:
            return JsonResponse({'error': '请先登录'}, status=401)
        
        try:
            profile = UserProfile.objects.get(user_id=user_id)
            if profile.role not in ['teacher', 'admin']:
                return JsonResponse({'error': '仅教师/管理员可清除回复'}, status=403)
        except UserProfile.DoesNotExist:
            return JsonResponse({'error': '用户不存在'}, status=404)
        
        feedback.is_resolved = False
        feedback.resolution_content = ''
        feedback.resolved_at = None
        feedback.save()
        
        return JsonResponse({'success': True})
    
    except AnonymousFeedback.DoesNotExist:
        return JsonResponse({'error': '反馈不存在'}, status=404)

# ==================== 优秀作品 API ====================

def excellent_work_list(request):
    work_type = request.GET.get('work_type', '')
    is_featured = request.GET.get('is_featured', '')
    
    queryset = ExcellentWork.objects.all()
    
    if work_type:
        queryset = queryset.filter(work_type=work_type)
    if is_featured:
        queryset = queryset.filter(is_featured=(is_featured == 'true'))
    
    works = []
    for w in queryset:
        works.append({
            'id': w.id,
            'title': w.title,
            'description': w.description,
            'work_type': w.get_work_type_display(),
            'author_name': w.author_name,
            'author_major': w.author_major,
            'author_graduation_year': w.author_graduation_year,
            'supervisor': w.supervisor,
            'awards': w.awards,
            'cover_image': request.build_absolute_uri(w.cover_image.url) if w.cover_image else None,
            'file_url': request.build_absolute_uri(w.file_upload.url) if w.file_upload else None,
            'link': w.link,
            'is_featured': w.is_featured,
            'created_by': w.created_by.user_id if w.created_by else None,
            'created_at': w.created_at.isoformat()
        })
    
    return JsonResponse({'works': works})

def excellent_work_detail(request, work_id):
    try:
        work = ExcellentWork.objects.get(id=work_id)
        return JsonResponse({
            'id': work.id,
            'title': work.title,
            'description': work.description,
            'work_type': work.work_type,
            'work_type_label': work.get_work_type_display(),
            'author_name': work.author_name,
            'author_major': work.author_major,
            'author_graduation_year': work.author_graduation_year,
            'supervisor': work.supervisor,
            'awards': work.awards,
            'cover_image': request.build_absolute_uri(work.cover_image.url) if work.cover_image else None,
            'file_url': request.build_absolute_uri(work.file_upload.url) if work.file_upload else None,
            'link': work.link,
            'is_featured': work.is_featured,
            'created_at': work.created_at.isoformat()
        })
    except ExcellentWork.DoesNotExist:
        return JsonResponse({'error': '作品不存在'}, status=404)

@csrf_exempt
def excellent_work_create(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    permission_result = check_permission(request, 'teacher')
    if isinstance(permission_result, JsonResponse):
        return permission_result
    
    try:
        content_type = request.headers.get('Content-Type', '')
        
        if 'application/json' in content_type:
            data = json.loads(request.body)
            files = {}
        else:
            data = request.POST
            files = request.FILES
        
        title = data.get('title', '')
        description = data.get('description', '')
        
        if not title or not description:
            return JsonResponse({'error': '作品名称和描述不能为空'}, status=400)
        
        user_id = request.headers.get('X-User-ID', '')
        created_by = None
        if user_id:
            try:
                created_by = UserProfile.objects.get(user_id=user_id)
            except UserProfile.DoesNotExist:
                pass
        
        cover_image = files.get('cover_image') if 'cover_image' in files else None
        file_upload = files.get('file_upload') if 'file_upload' in files else None
        
        work = ExcellentWork.objects.create(
            title=title,
            description=description,
            work_type=data.get('work_type', 'other'),
            author_name=data.get('author_name', ''),
            author_major=data.get('author_major', ''),
            author_graduation_year=data.get('author_graduation_year', ''),
            supervisor=data.get('supervisor', ''),
            awards=data.get('awards', ''),
            cover_image=cover_image,
            file_upload=file_upload,
            link=data.get('link', ''),
            is_featured=data.get('is_featured', False) == 'true',
            created_by=created_by
        )
        
        return JsonResponse({'success': True, 'work_id': work.id})
    
    except Exception as e:
        logger.error(f"Work create error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def excellent_work_delete(request, work_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    permission_result = check_permission(request, 'teacher')
    if isinstance(permission_result, JsonResponse):
        return permission_result
    
    try:
        work = ExcellentWork.objects.get(id=work_id)
        
        pass
        
        work.delete()
        return JsonResponse({'success': True, 'message': '删除成功'})
    except ExcellentWork.DoesNotExist:
        return JsonResponse({'error': '作品不存在'}, status=404)
    except Exception as e:
        logger.error(f"Work delete error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def excellent_work_update(request, work_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    permission_result = check_permission(request, 'teacher')
    if isinstance(permission_result, JsonResponse):
        return permission_result
    
    try:
        work = ExcellentWork.objects.get(id=work_id)
        
        pass
        
        content_type = request.headers.get('Content-Type', '')
        
        if 'application/json' in content_type:
            data = json.loads(request.body)
            files = {}
        else:
            data = request.POST
            files = request.FILES
        
        if 'title' in data:
            work.title = data.get('title', '')
        if 'description' in data:
            work.description = data.get('description', '')
        if 'work_type' in data:
            work.work_type = data.get('work_type', 'other')
        if 'author_name' in data:
            work.author_name = data.get('author_name', '')
        if 'author_major' in data:
            work.author_major = data.get('author_major', '')
        if 'author_graduation_year' in data:
            work.author_graduation_year = data.get('author_graduation_year', '')
        if 'supervisor' in data:
            work.supervisor = data.get('supervisor', '')
        if 'awards' in data:
            work.awards = data.get('awards', '')
        if 'link' in data:
            work.link = data.get('link', '')
        if 'is_featured' in data:
            work.is_featured = data.get('is_featured', False) == 'true'
        
        if 'cover_image' in files:
            work.cover_image = files.get('cover_image')
        if 'file_upload' in files:
            work.file_upload = files.get('file_upload')
        
        work.save()
        
        return JsonResponse({'success': True, 'work_id': work.id})
    
    except ExcellentWork.DoesNotExist:
        return JsonResponse({'error': '作品不存在'}, status=404)
    except Exception as e:
        logger.error(f"Work update error: {e}")
        return JsonResponse({'error': str(e)}, status=500)

# ==================== 学长就业 API ====================

def senior_employment_list(request):
    employment_type = request.GET.get('employment_type', '')
    industry = request.GET.get('industry', '')
    is_featured = request.GET.get('is_featured', '')
    
    queryset = SeniorEmployment.objects.all()
    
    if employment_type:
        queryset = queryset.filter(employment_type=employment_type)
    if industry:
        queryset = queryset.filter(industry__icontains=industry)
    if is_featured:
        queryset = queryset.filter(is_featured=(is_featured == 'true'))
    
    employments = []
    for idx, e in enumerate(queryset):
        senior_name = e.senior.name
        if senior_name and len(senior_name) > 0:
            display_name = senior_name[0] + '学长'
        else:
            display_name = '学长'
        employments.append({
            'id': e.id,
            'senior_id': e.senior.id,
            'senior_name': display_name,
            'senior_major': e.senior.major,
            'senior_graduation_year': e.senior.graduation_year,
            'employment_type': e.get_employment_type_display(),
            'company_name': e.company_name,
            'company_logo': request.build_absolute_uri(e.company_logo.url) if e.company_logo else None,
            'industry': e.industry,
            'position': e.position,
            'department': e.department,
            'salary_range': e.salary_range,
            'location': e.location,
            'work_summary': e.work_summary,
            'recruitment_tips': e.recruitment_tips,
            'is_featured': e.is_featured,
            'created_at': e.created_at.isoformat()
        })
    
    return JsonResponse({'employments': employments})

def senior_employment_detail(request, employment_id):
    try:
        employment = SeniorEmployment.objects.get(id=employment_id)
        return JsonResponse({
            'id': employment.id,
            'senior_id': employment.senior.id,
            'senior_name': employment.senior.name,
            'senior_major': employment.senior.major,
            'senior_graduation_year': employment.senior.graduation_year,
            'senior_avatar': request.build_absolute_uri(employment.senior.avatar.url) if employment.senior.avatar else None,
            'employment_type': employment.get_employment_type_display(),
            'company_name': employment.company_name,
            'company_logo': request.build_absolute_uri(employment.company_logo.url) if employment.company_logo else None,
            'industry': employment.industry,
            'position': employment.position,
            'department': employment.department,
            'salary_range': employment.salary_range,
            'location': employment.location,
            'work_summary': employment.work_summary,
            'recruitment_tips': employment.recruitment_tips,
            'is_featured': employment.is_featured,
            'created_at': employment.created_at.isoformat()
        })
    except SeniorEmployment.DoesNotExist:
        return JsonResponse({'error': '就业信息不存在'}, status=404)


@csrf_exempt
def senior_employment_create(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    permission_result = check_permission(request, 'teacher')
    if isinstance(permission_result, JsonResponse):
        return permission_result
    
    try:
        content_type = request.headers.get('Content-Type', '')
        
        if 'application/json' in content_type:
            data = json.loads(request.body)
            files = {}
        else:
            data = request.POST
            files = request.FILES
        
        senior_name = data.get('senior_name', '').strip()
        senior_major = data.get('senior_major', '').strip()
        senior_graduation_year = data.get('senior_graduation_year', '').strip()

        if not senior_name:
            return JsonResponse({'error': '请填写学长姓名'}, status=400)
        if not senior_major:
            return JsonResponse({'error': '请填写学长所学专业'}, status=400)
        if not senior_graduation_year:
            return JsonResponse({'error': '请填写学长毕业年份'}, status=400)

        senior = SeniorMentor.objects.create(
            name=senior_name,
            major=senior_major,
            graduation_year=senior_graduation_year,
            current_status=data.get('company_name', ''),
            company=data.get('company_name', ''),
            position=data.get('position', ''),
            mentor_type='career',
        )
        
        company_logo = files.get('company_logo') if 'company_logo' in files else None
        
        employment = SeniorEmployment.objects.create(
            senior=senior,
            employment_type=data.get('employment_type', 'fulltime'),
            company_name=data.get('company_name', ''),
            company_logo=company_logo,
            industry=data.get('industry', ''),
            position=data.get('position', ''),
            department=data.get('department', ''),
            salary_range=data.get('salary_range', ''),
            location=data.get('location', ''),
            work_summary=data.get('work_summary', ''),
            recruitment_tips=data.get('recruitment_tips', ''),
            is_featured=data.get('is_featured', False) == 'true',
        )
        return JsonResponse({'success': True, 'employment_id': employment.id})
    except Exception as e:
        logger.error(f"Senior employment create error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def senior_employment_update(request, employment_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    permission_result = check_permission(request, 'teacher')
    if isinstance(permission_result, JsonResponse):
        return permission_result
    
    try:
        employment = SeniorEmployment.objects.get(id=employment_id)
        
        content_type = request.headers.get('Content-Type', '')
        
        if 'application/json' in content_type:
            data = json.loads(request.body)
            files = {}
        else:
            data = request.POST
            files = request.FILES
        
        if 'senior_name' in data:
            employment.senior.name = data.get('senior_name', '')
        if 'senior_major' in data:
            employment.senior.major = data.get('senior_major', '')
        if 'senior_graduation_year' in data:
            employment.senior.graduation_year = data.get('senior_graduation_year', '')
        if 'company_name' in data:
            employment.senior.current_status = data.get('company_name', '')
            employment.senior.company = data.get('company_name', '')
        if 'position' in data:
            employment.senior.position = data.get('position', '')
        
        employment.senior.save()
        
        if 'employment_type' in data:
            employment.employment_type = data.get('employment_type', 'fulltime')
        if 'company_name' in data:
            employment.company_name = data.get('company_name', '')
        if 'company_logo' in files:
            employment.company_logo = files.get('company_logo')
        if 'industry' in data:
            employment.industry = data.get('industry', '')
        if 'position' in data:
            employment.position = data.get('position', '')
        if 'department' in data:
            employment.department = data.get('department', '')
        if 'salary_range' in data:
            employment.salary_range = data.get('salary_range', '')
        if 'location' in data:
            employment.location = data.get('location', '')
        if 'work_summary' in data:
            employment.work_summary = data.get('work_summary', '')
        if 'recruitment_tips' in data:
            employment.recruitment_tips = data.get('recruitment_tips', '')
        if 'is_featured' in data:
            employment.is_featured = data.get('is_featured', False) == 'true'
        
        employment.save()
        
        return JsonResponse({'success': True, 'employment_id': employment.id})
    
    except SeniorEmployment.DoesNotExist:
        return JsonResponse({'error': '就业信息不存在'}, status=404)
    except Exception as e:
        logger.error(f"Senior employment update error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def senior_employment_delete(request, employment_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    permission_result = check_permission(request, 'teacher')
    if isinstance(permission_result, JsonResponse):
        return permission_result
    
    try:
        employment = SeniorEmployment.objects.get(id=employment_id)
        employment.delete()
        return JsonResponse({'success': True, 'message': '删除成功'})
    except SeniorEmployment.DoesNotExist:
        return JsonResponse({'error': '就业信息不存在'}, status=404)
    except Exception as e:
        logger.error(f"Senior employment delete error: {e}")
        return JsonResponse({'error': str(e)}, status=500)

# ==================== AI智能分析 API ====================

@csrf_exempt
def ai_analyze_syllabus(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        syllabus_id = data.get('syllabus_id')
        
        if not syllabus_id:
            return JsonResponse({'error': '课程ID不能为空'}, status=400)
        
        syllabus = CourseSyllabus.objects.get(id=syllabus_id)
        
        llm = get_llm_client()
        result = None
        
        if llm:
            full_text = f"""课程名称: {syllabus.course_name}
课程目标: {syllabus.course_objectives}
课程内容: {syllabus.course_content}
先修课程: {syllabus.prerequisite_courses}
考核方式: {syllabus.assessment_methods}"""
            
            prompt = f"""请分析以下课程教学大纲，提取结构化信息：

大纲内容：
{full_text}

请输出JSON格式，包含以下字段：
1. objectives: 课程目标列表（3-5个）
2. knowledge_points: 知识点列表，每个知识点包含name(名称), category(类别), description(描述), importance(重要程度1-100)
3. prerequisites: 先修知识要求
4. suggestions: 课程优化建议（3-5条）"""
            
            try:
                response = llm.call(prompt)
                result = json.loads(response)
            except:
                pass
        
        if result is None:
            objectives = []
            if syllabus.course_objectives:
                for line in syllabus.course_objectives.replace('；', ';').replace('\n', ';').split(';'):
                    line = line.strip()
                    if line and len(line) > 5:
                        objectives.append(line[:100])
                    if len(objectives) >= 5:
                        break
            if not objectives:
                objectives = ['掌握课程基本概念和原理', '培养相关技能和实践能力', '建立学科思维方法', '提升问题解决能力', '了解学科前沿发展']
            
            knowledge_points = []
            if syllabus.course_content:
                for line in syllabus.course_content.replace('\n', ';').split(';'):
                    line = line.strip()
                    if line and len(line) > 5 and len(knowledge_points) < 10:
                        knowledge_points.append({
                            'name': line[:60],
                            'category': '核心内容',
                            'description': line[:100],
                            'importance': 70
                        })
            if not knowledge_points:
                knowledge_points = [
                    {'name': '基本概念', 'category': '基础', 'description': '课程基本概念和术语', 'importance': 80},
                    {'name': '核心原理', 'category': '核心', 'description': '课程核心原理和方法', 'importance': 90},
                    {'name': '实践应用', 'category': '应用', 'description': '知识的实际应用', 'importance': 75},
                ]
            
            suggestions = [
                '建议增加案例分析和实践教学环节',
                '建议采用多样化教学方法（如翻转课堂、项目驱动）',
                '建议完善课程考核评价体系',
                '建议加强学生自主学习能力培养',
            ]
            
            result = {
                'objectives': objectives,
                'knowledge_points': knowledge_points,
                'prerequisites': syllabus.prerequisite_courses or '无特殊要求',
                'suggestions': suggestions,
                'offline_mode': True
            }
        
        CourseAnalysisReport.objects.filter(course=syllabus).delete()
        report = CourseAnalysisReport.objects.create(
            course=syllabus,
            ai_extracted_objectives=result.get('objectives', []),
            ai_extracted_points=result.get('knowledge_points', []),
            optimization_suggestions='\n'.join(result.get('suggestions', [])),
            coverage_analysis={}
        )
        
        for point in result.get('knowledge_points', []):
            KnowledgePoint.objects.create(
                course=syllabus,
                point_name=point.get('name', ''),
                point_category=point.get('category', ''),
                description=point.get('description', ''),
                importance=point.get('importance', 50)
            )
        
        return JsonResponse({
            'success': True,
            'report_id': report.id,
            'analysis': result
        })
    
    except CourseSyllabus.DoesNotExist:
        return JsonResponse({'error': '课程大纲不存在'}, status=404)
    except Exception as e:
        logger.error(f"AI syllabus analysis error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


def feedback_analysis_summary(request):
    feedback_type = request.GET.get('feedback_type', '')
    
    queryset = AnonymousFeedback.objects.all()
    if feedback_type:
        queryset = queryset.filter(feedback_type=feedback_type)
    
    analyses = FeedbackAnalysis.objects.filter(feedback__in=queryset)
    
    sentiment_stats = {'positive': 0, 'neutral': 0, 'negative': 0}
    all_topics = {}
    all_keywords = {}
    
    for analysis in analyses:
        label = analysis.sentiment_label
        if label in ['正面', '积极']:
            sentiment_stats['positive'] += 1
        elif label in ['负面', '消极']:
            sentiment_stats['negative'] += 1
        else:
            sentiment_stats['neutral'] += 1
        
        for topic in analysis.topics or []:
            all_topics[topic] = all_topics.get(topic, 0) + 1
        
        for keyword in analysis.keywords or []:
            all_keywords[keyword] = all_keywords.get(keyword, 0) + 1
    
    top_topics = sorted(all_topics.items(), key=lambda x: -x[1])[:5]
    top_keywords = sorted(all_keywords.items(), key=lambda x: -x[1])[:10]
    
    return JsonResponse({
        'total_feedbacks': queryset.count(),
        'analyzed_count': analyses.count(),
        'sentiment_stats': sentiment_stats,
        'top_topics': [{'topic': t[0], 'count': t[1]} for t in top_topics],
        'top_keywords': [{'keyword': k[0], 'count': k[1]} for k in top_keywords]
    })

@csrf_exempt
def ai_generate_growth_path(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        path_type = data.get('path_type')
        
        if not user_id or not path_type:
            return JsonResponse({'error': '用户ID和路径类型不能为空'}, status=400)
        
        try:
            profile = UserProfile.objects.get(user_id=user_id)
        except UserProfile.DoesNotExist:
            return JsonResponse({'error': '用户不存在'}, status=404)
        
        llm = get_llm_client()
        if not llm:
            return JsonResponse({'error': 'AI服务不可用'}, status=500)
        
        path_type_map = {
            'graduate_exam': '考研',
            'graduate_recommend': '保研',
            'employment': '就业',
            'research': '科研',
            'competition': '竞赛',
            'study_abroad': '出国留学'
        }
        
        user_info = f"""学生信息：
年级: {profile.grade}
专业: {profile.major}
GPA: {profile.gpa}
排名: {profile.rank}
获奖记录: {profile.awards}
科研经历: {profile.research}
未来目标: {profile.goal}"""
        
        prompt = f"""请为以下学生生成{path_type_map.get(path_type, path_type)}方向的个性化成长路径：

{user_info}

请输出JSON格式，包含以下字段：
1. path_name: 路径名称
2. stages: 阶段规划列表，每个阶段包含stage(阶段名称), duration(时长), tasks(任务列表)
3. recommended_courses: 推荐课程列表
4. resources: 推荐学习资源列表
5. estimated_duration: 预计总时长
6. key_points: 关键注意事项"""
        
        try:
            response = llm.call(prompt)
            result = json.loads(response)
        except:
            result = {
                'path_name': f'{path_type_map.get(path_type, path_type)}成长路径',
                'stages': [],
                'recommended_courses': [],
                'resources': [],
                'estimated_duration': '',
                'key_points': []
            }
        
        growth_path = GrowthPath.objects.create(
            user=profile,
            path_type=path_type,
            path_name=result.get('path_name', f'{path_type_map.get(path_type, path_type)}成长路径'),
            stages=result.get('stages', []),
            recommended_courses=result.get('recommended_courses', []),
            resources=result.get('resources', []),
            estimated_duration=result.get('estimated_duration', '')
        )
        
        return JsonResponse({
            'success': True,
            'path_id': growth_path.id,
            'growth_path': result
        })
    
    except Exception as e:
        logger.error(f"AI growth path error: {e}")
        return JsonResponse({'error': str(e)}, status=500)

def user_growth_paths(request):
    user_id = request.GET.get('user_id', '') or request.headers.get('X-User-ID', '')
    
    if not user_id:
        return JsonResponse({'error': '用户ID不能为空'}, status=400)
    
    try:
        profile = UserProfile.objects.get(user_id=user_id)
        paths = GrowthPath.objects.filter(user=profile)
        
        path_list = []
        path_type_map = {
            'graduate_exam': '考研',
            'graduate_recommend': '保研',
            'employment': '就业',
            'research': '科研',
            'competition': '竞赛',
            'study_abroad': '出国留学'
        }
        
        for path in paths:
            path_list.append({
                'id': path.id,
                'path_type': path.path_type,
                'path_type_label': path_type_map.get(path.path_type, path.path_type),
                'path_name': path.path_name,
                'stages': path.stages or [],
                'recommended_courses': path.recommended_courses or [],
                'resources': path.resources or [],
                'estimated_duration': path.estimated_duration,
                'created_at': path.created_at.isoformat()
            })
        
        return JsonResponse({'paths': path_list})
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': '用户不存在'}, status=404)

# ==================== 权限与角色 API ====================

def get_current_user(request):
    user_id = request.GET.get('user_id', '') or request.headers.get('X-User-ID', '')
    
    if not user_id:
        return JsonResponse({'error': '用户ID不能为空'}, status=400)
    
    try:
        profile = UserProfile.objects.get(user_id=user_id)
        
        teaching_courses = []
        for tc in profile.teaching_courses.all():
            teaching_courses.append({
                'course_id': tc.course.id,
                'course_code': tc.course.course_code,
                'course_name': tc.course.course_name,
                'semester': tc.get_semester_display(),
                'academic_year': tc.academic_year
            })
        
        enrolled_courses = []
        for sc in profile.enrolled_courses.all():
            enrolled_courses.append({
                'course_id': sc.course.id,
                'course_code': sc.course.course_code,
                'course_name': sc.course.course_name,
                'semester': sc.get_semester_display(),
                'academic_year': sc.academic_year,
                'grade': sc.grade
            })
        
        return JsonResponse({
            'user_id': profile.user_id,
            'username': profile.username,
            'role': profile.role,
            'role_label': dict(profile.ROLE_CHOICES).get(profile.role, profile.role),
            'department': profile.department,
            'position': profile.position,
            'grade': profile.grade,
            'major': profile.major,
            'gpa': str(profile.gpa) if profile.gpa else '',
            'rank': profile.rank,
            'awards': profile.awards,
            'research': profile.research,
            'goal': profile.goal,
            'email': profile.email,
            'phone': profile.phone,
            'hometown': profile.hometown,
            'profile_completed': profile.profile_completed,
            'teaching_courses': teaching_courses,
            'enrolled_courses': enrolled_courses
        })
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': '用户不存在'}, status=404)


@csrf_exempt
def data_overview(request):
    """聚合学长就业数据：去向分布、薪资区间、热门公司、热门行业"""
    try:
        employments = SeniorEmployment.objects.select_related('senior').all()

        # 去向分布
        type_map = {
            'fulltime': '全职就业',
            'graduate': '升学深造',
            'study_abroad': '出国留学',
            'startup': '创业',
            'other': '其他',
        }
        type_counts = {}
        for emp in employments:
            label = type_map.get(emp.employment_type, '其他')
            type_counts[label] = type_counts.get(label, 0) + 1

        total_emp = sum(type_counts.values())
        direction_dist = []
        for label, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            direction_dist.append({
                'label': label,
                'count': count,
                'pct': round(count / total_emp * 100, 1) if total_emp else 0
            })

        # 薪资区间分布
        salary_brackets = [
            ('8K以下', 0, 8),
            ('8-12K', 8, 12),
            ('12-15K', 12, 15),
            ('15-20K', 15, 20),
            ('20-30K', 20, 30),
            ('30K以上', 30, 999),
        ]
        bracket_counts = {b[0]: 0 for b in salary_brackets}
        for emp in employments:
            s = emp.salary_range or ''
            nums = re.findall(r'(\d+(?:\.\d+)?)', s)
            if nums:
                try:
                    avg_sal = sum(float(n) for n in nums) / len(nums)
                    for label, lo, hi in salary_brackets:
                        if lo <= avg_sal < hi:
                            bracket_counts[label] += 1
                            break
                except ValueError:
                    pass

        total_sal = sum(bracket_counts.values())
        salary_dist = []
        for label, lo, hi in salary_brackets:
            count = bracket_counts[label]
            if count > 0:
                salary_dist.append({
                    'label': label,
                    'count': count,
                    'pct': round(count / total_sal * 100, 1) if total_sal else 0
                })

        # 热门公司
        company_counts = {}
        for emp in employments:
            name = (emp.company_name or '').strip()
            if name:
                company_counts[name] = company_counts.get(name, 0) + 1
        top_companies = sorted(company_counts.items(), key=lambda x: -x[1])[:8]

        # 热门行业
        industry_counts = {}
        for emp in employments:
            ind = (emp.industry or '').strip()
            if ind:
                industry_counts[ind] = industry_counts.get(ind, 0) + 1
        top_industries = sorted(industry_counts.items(), key=lambda x: -x[1])[:6]

        # 总样本数
        total_seniors = SeniorMentor.objects.count()

        return JsonResponse({
            'success': True,
            'total_seniors': total_seniors,
            'total_employment': total_emp,
            'direction_dist': direction_dist,
            'salary_dist': salary_dist,
            'top_companies': [{'name': c[0], 'count': c[1]} for c in top_companies],
            'top_industries': [{'name': c[0], 'count': c[1]} for c in top_industries],
        })
    except Exception as e:
        logger.error(f"data_overview error: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
# -*- coding: utf-8 -*-
"""把 DB 的 SeniorEmployment 同步成 employment chunks 追加到 employment_cases.json
然后重建 FAISS 索引，让 AI 检索能召回扩充后的样本"""
import json
import os
from pathlib import Path
from django.core.management.base import BaseCommand
from chat.models import SeniorEmployment

DATA_DIR = Path(__file__).resolve().parents[4] / 'edupilot_agent' / 'data'
CASES_FILE = DATA_DIR / 'employment_cases.json'
FAISS_DIR = DATA_DIR / 'langchain_faiss'

# 工作地→省份映射（chunks 里需要 province 字段）
LOC_PROVINCE = {
    '北京': '北京市', '上海': '上海市', '深圳': '广东省', '广州': '广东省',
    '杭州': '浙江省', '成都': '四川省', '天津': '天津市', '武汉': '湖北省',
    '南京': '江苏省', '合肥': '安徽省', '美国': '海外', '新加坡': '海外', '瑞士': '海外',
}

TYPE_LABEL = {
    'fulltime': '就业',
    'graduate': '升学深造',
    'study_abroad': '出国留学',
    'startup': '创业',
    'other': '其他',
}


def _build_chunk(emp, idx):
    """把一条 SeniorEmployment 转成 employment chunk 格式"""
    senior = emp.senior
    major = senior.major or ''
    year = senior.graduation_year or ''
    loc = emp.location or ''
    province = LOC_PROVINCE.get(loc, '')
    etype = TYPE_LABEL.get(emp.employment_type, '就业')
    company = emp.company_name or ''
    position = emp.position or ''
    salary = emp.salary_range or ''
    industry = emp.industry or ''

    # 拼接 content：仿照现有 emp_case_xxx 的叙述风格
    parts = [f'{senior.name}，{major}专业{year}级。']
    if emp.employment_type == 'fulltime':
        parts.append(f'毕业后进入{company}（{industry}），任{position}。')
        if salary:
            parts.append(f'薪资：应届{salary}。')
        parts.append(senior.experience_summary or '')
    elif emp.employment_type == 'graduate':
        parts.append(f'毕业后保研/考研至{company}，方向{position}。')
        parts.append(senior.experience_summary or '')
    elif emp.employment_type == 'study_abroad':
        parts.append(f'毕业后赴{loc}留学，就读{company}，方向{position}。')
        parts.append(senior.experience_summary or '')
    elif emp.employment_type == 'startup':
        parts.append(f'毕业后自主创业，创办{company}，任{position}，位于{loc}。')
        parts.append(senior.experience_summary or '')
    else:
        parts.append(f'毕业后去向：{company}，{position}。')

    content = ''.join(parts)
    tags = [etype, loc, company, position, industry]
    tags = [t for t in tags if t]

    return {
        'chunk_id': f'emp_db_{idx:03d}',
        'type': 'employment',
        'person_id': f'{senior.name}_{loc}',
        'major': major,
        'province': province,
        'hometown_province': '',
        'stage': f'{year}级',
        'topic': f'就业案例-{company}{position}',
        'content': content,
        'tags': tags,
    }


class Command(BaseCommand):
    help = '同步 DB SeniorEmployment 到 employment_cases.json 并重建 FAISS 索引'

    def add_arguments(self, parser):
        parser.add_argument('--rebuild-index', action='store_true', help='同步后重建 FAISS 索引')

    def handle(self, *args, **options):
        # 1. 读取现有 cases
        existing = []
        if CASES_FILE.exists():
            existing = json.loads(CASES_FILE.read_text(encoding='utf-8'))
        existing_ids = {c.get('chunk_id') for c in existing}
        self.stdout.write(f'现有 employment chunks: {len(existing)} 条')

        # 2. 从 DB 生成新 chunks（只追加不重复的）
        new_chunks = []
        emps = SeniorEmployment.objects.select_related('senior').all().order_by('id')
        for i, emp in enumerate(emps, 1):
            chunk = _build_chunk(emp, i)
            if chunk['chunk_id'] not in existing_ids:
                new_chunks.append(chunk)

        if not new_chunks:
            self.stdout.write(self.style.WARNING('没有新增 chunks（DB 数据已全部同步过）'))
        else:
            merged = existing + new_chunks
            CASES_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding='utf-8')
            self.stdout.write(self.style.SUCCESS(
                f'追加 {len(new_chunks)} 条 employment chunks → {CASES_FILE.name}（现共 {len(merged)} 条）'
            ))

        # 3. 可选：重建 FAISS 索引
        if options.get('rebuild_index'):
            self._rebuild_index()
        else:
            self.stdout.write(self.style.NOTICE(
                '提示：如需让 AI 检索命中新数据，需重建 FAISS 索引：\n'
                '  python manage.py sync_employment_chunks --rebuild-index'
            ))

    def _rebuild_index(self):
        import shutil
        import tempfile
        self.stdout.write('开始重建 FAISS 索引...')
        project_root = DATA_DIR.parents[1]  # EduPilot/
        os.chdir(project_root)
        # 用英文临时目录写索引，避开 Windows 中文路径导致 faiss fopen 失败的问题
        tmp_dir = tempfile.mkdtemp(prefix='edupilot_faiss_')
        try:
            from edupilot_agent.langchain_index import build_vector_store
            kb = ','.join([
                'edupilot_agent/data/interview_chunks.json',
                'edupilot_agent/data/employment_cases.json',
                'edupilot_agent/data/deep_interview_2024.json',
                'edupilot_agent/data/public_interview_2024.json',
            ])
            build_vector_store(kb_path=kb, persist_dir=tmp_dir)
            # 复制到目标中文路径
            FAISS_DIR.mkdir(parents=True, exist_ok=True)
            for fname in os.listdir(tmp_dir):
                src = os.path.join(tmp_dir, fname)
                dst = FAISS_DIR / fname
                shutil.copy2(src, dst)
            self.stdout.write(self.style.SUCCESS(
                f'FAISS 索引重建完成，已写入 {FAISS_DIR}'
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'索引重建失败: {e}'))
            self.stdout.write(self.style.NOTICE(
                '可能原因：缺少 embedding API key（DASHSCOPE_API_KEY/EMBEDDING_API_KEY）。'
                '请在 .env 配置后重试，或手动跑：python -m edupilot_agent.langchain_index'
            ))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

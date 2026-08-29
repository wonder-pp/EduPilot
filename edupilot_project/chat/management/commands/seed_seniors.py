# -*- coding: utf-8 -*-
"""扩充学长就业样本数据（脱敏化名 + 真实分布），用于数据概览面板可视化"""
from django.core.management.base import BaseCommand
from chat.models import SeniorMentor, SeniorEmployment

# 两个专业
MAJOR_DS = '数据科学与大数据技术'
MAJOR_AI = '智能科学与技术'

# 数据列表：每条 = (name, major, year, type, company, industry, position, salary, location)
# 就业类型 fulltime=全职 / graduate=升学 / study_abroad=留学 / startup=创业 / other=其他
SENIORS = [
    # ========== 数据科学与大数据技术 22 条 ==========
    # 全职就业 14
    ('陈思远', MAJOR_DS, '2022', 'fulltime', '字节跳动', '互联网', '数据工程师', '22K', '北京'),
    ('林宇航', MAJOR_DS, '2021', 'fulltime', '阿里巴巴', '互联网', '算法工程师', '25K', '杭州'),
    ('王梓涵', MAJOR_DS, '2023', 'fulltime', '美团', '互联网', '后端开发工程师', '18K', '北京'),
    ('张博文', MAJOR_DS, '2020', 'fulltime', '腾讯', '互联网', '大数据开发工程师', '24K', '深圳'),
    ('刘晨曦', MAJOR_DS, '2022', 'fulltime', '华为', '通信', '数据分析师', '20K', '深圳'),
    ('李泽楷', MAJOR_DS, '2023', 'fulltime', '百度', '互联网', '推荐算法工程师', '19K', '北京'),
    ('赵睿', MAJOR_DS, '2021', 'fulltime', '京东', '互联网', '数据工程师', '21K', '北京'),
    ('孙浩然', MAJOR_DS, '2020', 'fulltime', '拼多多', '互联网', '算法工程师', '26K', '上海'),
    ('周明轩', MAJOR_DS, '2022', 'fulltime', '网易', '互联网', '数据开发工程师', '18K', '杭州'),
    ('吴俊杰', MAJOR_DS, '2023', 'fulltime', '快手', '互联网', '大数据工程师', '20K', '北京'),
    ('郑凯', MAJOR_DS, '2021', 'fulltime', '招商银行', '金融科技', '数据分析师', '16K', '深圳'),
    ('钱伟', MAJOR_DS, '2022', 'fulltime', '中信证券', '金融科技', '量化研究员', '22K', '北京'),
    ('冯天宇', MAJOR_DS, '2020', 'fulltime', '商汤科技', '人工智能', 'CV算法工程师', '23K', '上海'),
    ('梁文静', MAJOR_DS, '2022', 'fulltime', '滴滴', '互联网', '数据分析师', '17K', '北京'),
    # 升学深造 5
    ('杨子轩', MAJOR_DS, '2022', 'graduate', '复旦大学', '科研', '计算机技术（保研）', '', '上海'),
    ('罗婧', MAJOR_DS, '2021', 'graduate', '天津大学', '科研', '人工智能（保研）', '', '天津'),
    ('彭浩', MAJOR_DS, '2021', 'graduate', '中国科学技术大学', '科研', '数据科学（考研）', '', '合肥'),
    ('许文博', MAJOR_DS, '2023', 'graduate', '浙江大学', '科研', '大数据（保研）', '', '杭州'),
    ('蔡明', MAJOR_DS, '2021', 'graduate', '南京大学', '科研', '机器学习（保研）', '', '南京'),
    # 出国留学 2
    ('苏婉清', MAJOR_DS, '2022', 'study_abroad', '卡内基梅隆大学', '科研', '计算机硕士', '', '美国'),
    ('范晓琳', MAJOR_DS, '2023', 'study_abroad', '苏黎世联邦理工', '科研', 'AI硕士', '', '瑞士'),
    # 创业 1
    ('高俊豪', MAJOR_DS, '2020', 'startup', '自主创业', '创业', '创始人', '', '上海'),

    # ========== 智能科学与技术 18 条 ==========
    # 全职就业 10
    ('陈雨桐', MAJOR_AI, '2021', 'fulltime', '商汤科技', '人工智能', 'CV算法工程师', '24K', '上海'),
    ('林泽', MAJOR_AI, '2022', 'fulltime', '旷视科技', '人工智能', '算法工程师', '22K', '北京'),
    ('王昊', MAJOR_AI, '2023', 'fulltime', '科大讯飞', '人工智能', 'NLP工程师', '18K', '合肥'),
    ('张晨', MAJOR_AI, '2020', 'fulltime', '阿里巴巴', '互联网', '算法专家', '28K', '杭州'),
    ('刘洋', MAJOR_AI, '2022', 'fulltime', '腾讯', '人工智能', 'AI研究员', '26K', '深圳'),
    ('赵敏', MAJOR_AI, '2021', 'fulltime', '字节跳动', '互联网', '推荐算法工程师', '23K', '北京'),
    ('钱浩', MAJOR_AI, '2023', 'fulltime', '百度', '人工智能', '自动驾驶算法工程师', '20K', '北京'),
    ('李博', MAJOR_AI, '2020', 'fulltime', '滴滴', '互联网', '数据科学家', '25K', '北京'),
    ('周磊', MAJOR_AI, '2023', 'fulltime', '招商银行', '金融科技', 'AI风控工程师', '17K', '深圳'),
    ('吴佳', MAJOR_AI, '2021', 'fulltime', '中信证券', '金融科技', '量化工程师', '21K', '北京'),
    # 升学深造 5
    ('王磊', MAJOR_AI, '2023', 'graduate', '复旦大学', '科研', '智能科学（保研）', '', '上海'),
    ('高晨', MAJOR_AI, '2021', 'graduate', '上海交通大学', '科研', '模式识别（保研）', '', '上海'),
    ('林帆', MAJOR_AI, '2022', 'graduate', '浙江大学', '科研', '计算机视觉（保研）', '', '杭州'),
    ('沈佳琪', MAJOR_AI, '2023', 'graduate', '中山大学', '科研', '智能科学（保研）', '', '广州'),
    ('韩雪', MAJOR_AI, '2022', 'graduate', '华中科技大学', '科研', '人工智能（保研）', '', '武汉'),
    # 出国留学 2
    ('顾文豪', MAJOR_AI, '2021', 'study_abroad', '新加坡国立大学', '科研', '数据科学硕士', '', '新加坡'),
    ('徐颖', MAJOR_AI, '2022', 'study_abroad', '斯坦福大学', '科研', 'AI硕士', '', '美国'),
    # 创业 1
    ('郑雪', MAJOR_AI, '2022', 'startup', '自主创业', '创业', 'AI产品创始人', '', '上海'),
]


def _build_education(major, year, company):
    return f'{year}届{major}本科，于{company}就职/深造'


def _build_summary(major, year, company, position, salary):
    if salary:
        return f'{year}年毕业后加入{company}担任{position}，薪资{salary}，工作中持续深耕{major}相关技术。'
    return f'{year}年毕业后进入{company}攻读{position}，继续{major}方向的研究。'


def _build_skills(major, etype):
    if etype == 'fulltime':
        return 'Python,SQL,机器学习,数据建模,大数据开发'
    if etype in ('graduate', 'study_abroad'):
        return '科研论文,算法基础,数学建模,Python'
    if etype == 'startup':
        return '产品设计,团队管理,商业洞察'
    return '通用技能'


def _build_advice(major):
    return f'建议学弟学妹在校期间扎实{major}基础，多参加项目实战和竞赛，绩点和排名是保研/求职的关键。'


class Command(BaseCommand):
    help = '扩充学长就业样本数据（脱敏化名 + 真实分布）'

    def handle(self, *args, **options):
        created = 0
        skipped = 0
        for (name, major, year, etype, company, industry, position, salary, loc) in SENIORS:
            mentor, was_created = SeniorMentor.objects.get_or_create(
                name=name,
                defaults={
                    'major': major,
                    'graduation_year': year,
                    'current_status': f'就职于{company}' if etype == 'fulltime' else f'就读于{company}',
                    'company': company if etype == 'fulltime' else '',
                    'position': position,
                    'education_background': _build_education(major, year, company),
                    'experience_summary': _build_summary(major, year, company, position, salary),
                    'skills': _build_skills(major, etype),
                    'achievements': '',
                    'advice': _build_advice(major),
                    'mentor_type': 'career' if etype == 'fulltime' else 'academic',
                    'tags': f'{major},{year}届,{company}',
                },
            )
            if not was_created:
                skipped += 1
                continue
            SeniorEmployment.objects.create(
                senior=mentor,
                employment_type=etype,
                company_name=company,
                industry=industry,
                position=position,
                salary_range=salary,
                location=loc,
                work_summary=_build_summary(major, year, company, position, salary),
                recruitment_tips=_build_advice(major),
            )
            created += 1

        total_mentors = SeniorMentor.objects.count()
        total_emp = SeniorEmployment.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f'完成：新增 {created} 位学长，跳过(已存在) {skipped} 位。'
            f'当前库内：学长档案 {total_mentors} 条，就业去向 {total_emp} 条。'
        ))

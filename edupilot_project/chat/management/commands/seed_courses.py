"""
智能科学与技术专业课程大纲模拟数据种子脚本

用法：
    python manage.py seed_courses            # 追加创建（跳过已存在的课程代码）
    python manage.py seed_courses --fresh    # 先清空再创建（谨慎使用）

创建 12 门覆盖数学基础、计算机基础、AI 核心、专业方向、应用方向的课程，
并在课程间建立逻辑关联（先修/同修/进阶/关联/互补）。
"""
from django.core.management.base import BaseCommand
from chat.models import (
    CourseSyllabus, CourseRelation, KnowledgePoint,
    TeacherCourse, UserProfile,
)

MAJOR = '智能科学与技术'
GRADE = '2024级'

# 12 门课程大纲数据
COURSES = [
    {
        'course_code': 'IST101',
        'course_name': '高等数学',
        'course_name_en': 'Advanced Mathematics',
        'credit': '5.0',
        'semester': 'autumn',
        'course_objectives': '掌握微积分的基本理论与方法，理解极限、连续、导数、积分的核心概念，培养数学推理与抽象思维能力，为后续机器学习、最优化等课程奠定数学基础。',
        'course_content': '函数与极限；导数与微分；微分中值定理与导数应用；不定积分与定积分；多元函数微分学；重积分；曲线积分与曲面积分；无穷级数；常微分方程。重点讲解梯度、泰勒展开、极值问题等与机器学习相关的内容。',
        'teaching_methods': '课堂讲授为主，配合习题课与数学实验',
        'assessment_methods': '平时成绩20%+期中考试30%+期末考试50%',
        'reference_materials': '《高等数学》同济大学第七版；《微积分》清华大学出版社',
        'prerequisite_courses': '',
    },
    {
        'course_code': 'IST102',
        'course_name': '线性代数',
        'course_name_en': 'Linear Algebra',
        'credit': '3.0',
        'semester': 'autumn',
        'course_objectives': '理解矩阵、向量空间、线性变换等基本概念，掌握矩阵运算、行列式、特征值与特征向量、奇异值分解等方法，为机器学习、深度学习、计算机视觉提供数学工具。',
        'course_content': '行列式；矩阵及其运算；向量组的线性相关性与矩阵的秩；线性方程组；特征值与特征向量；相似矩阵与矩阵对角化；二次型；奇异值分解（SVD）；矩阵的梯度与求导。强调矩阵分解在降维与推荐系统中的应用。',
        'teaching_methods': '课堂讲授+MATLAB/Python矩阵运算实验',
        'assessment_methods': '平时20%+实验20%+期末60%',
        'reference_materials': '《线性代数》同济大学；《线性代数及其应用》David C. Lay',
        'prerequisite_courses': '高等数学',
    },
    {
        'course_code': 'IST103',
        'course_name': '概率论与数理统计',
        'course_name_en': 'Probability and Statistics',
        'credit': '3.0',
        'semester': 'spring',
        'course_objectives': '掌握随机事件、概率分布、数字特征、参数估计、假设检验等基本理论，理解贝叶斯思想与最大似然估计，为机器学习中的概率模型提供理论基础。',
        'course_content': '随机事件与概率；一维与多维随机变量及其分布；随机变量的数字特征；大数定律与中心极限定理；样本与抽样分布；参数估计（最大似然估计、贝叶斯估计）；假设检验；方差分析与回归分析。重点讲解贝叶斯定理、高斯分布、条件概率在机器学习中的应用。',
        'teaching_methods': '课堂讲授+统计软件R/Python实验',
        'assessment_methods': '平时20%+实验20%+期末60%',
        'reference_materials': '《概率论与数理统计》浙江大学；《统计学习方法》李航',
        'prerequisite_courses': '高等数学,线性代数',
    },
    {
        'course_code': 'IST104',
        'course_name': '程序设计基础',
        'course_name_en': 'Programming Fundamentals',
        'credit': '3.0',
        'semester': 'autumn',
        'course_objectives': '掌握Python语言的基本语法与编程范式，理解数据类型、控制结构、函数、面向对象编程，培养计算思维与代码实践能力，为后续算法与AI实验提供工具支撑。',
        'course_content': 'Python语法基础；数据类型与运算符；控制结构（顺序、分支、循环）；函数与模块；列表、字典、集合、元组；字符串处理；文件读写；面向对象编程（类、继承、多态）；异常处理；NumPy与Pandas入门。穿插AI算法的代码实现示例。',
        'teaching_methods': '讲授+上机实践，项目驱动',
        'assessment_methods': '平时30%+实验项目30%+期末40%',
        'reference_materials': '《Python编程：从入门到实践》；《流畅的Python》',
        'prerequisite_courses': '',
    },
    {
        'course_code': 'IST105',
        'course_name': '数据结构',
        'course_name_en': 'Data Structures',
        'credit': '4.0',
        'semester': 'spring',
        'course_objectives': '掌握线性表、栈、队列、树、图等基本数据结构的逻辑结构、存储结构及算法实现，理解算法复杂度分析，为高效实现AI算法奠定基础。',
        'course_content': '算法复杂度分析（时间复杂度、空间复杂度）；线性表（顺序表、链表）；栈与队列；递归；树与二叉树（遍历、二叉搜索树、平衡树、堆）；图（邻接矩阵、邻接表、DFS、BFS、最短路径、最小生成树）；查找（二分查找、哈希表）；排序（冒泡、快排、归并、堆排序）。强调在AI中的图算法与树搜索应用。',
        'teaching_methods': '讲授+上机实验，LeetCode刷题实践',
        'assessment_methods': '平时20%+实验30%+期末50%',
        'reference_materials': '《数据结构》严蔚敏；《算法导论》CLRS',
        'prerequisite_courses': '程序设计基础',
    },
    {
        'course_code': 'IST106',
        'course_name': '算法设计与分析',
        'course_name_en': 'Algorithm Design and Analysis',
        'credit': '3.0',
        'semester': 'autumn',
        'course_objectives': '掌握分治、动态规划、贪心、回溯、分支限界等算法设计策略，理解NP完全性理论，培养分析问题与设计高效算法的能力。',
        'course_content': '算法复杂度与渐进记号；分治法（归并排序、快速排序、最近点对）；动态规划（最长公共子序列、背包问题、最优二叉搜索树）；贪心算法（活动安排、哈夫曼编码）；回溯法与分支限界（N皇后、旅行商）；图算法（最短路径、网络流）；NP完全性理论；启发式搜索与优化算法（遗传算法、模拟退火）简介。',
        'teaching_methods': '讲授+算法实验，ACM赛题训练',
        'assessment_methods': '平时20%+实验30%+期末50%',
        'reference_materials': '《算法导论》CLRS；《算法设计与分析》王晓东',
        'prerequisite_courses': '数据结构',
    },
    {
        'course_code': 'IST201',
        'course_name': '人工智能导论',
        'course_name_en': 'Introduction to Artificial Intelligence',
        'credit': '3.0',
        'semester': 'autumn',
        'course_objectives': '理解人工智能的基本概念、发展历史与流派，掌握搜索、知识表示、推理、规划等经典AI方法，建立对智能科学的整体认知框架。',
        'course_content': 'AI发展史与流派（符号主义、连接主义、行为主义）；智能Agent；问题求解与搜索（盲目搜索、启发式搜索、A*算法、博弈搜索Minimax与Alpha-Beta剪枝）；知识表示与推理（谓词逻辑、产生式规则、语义网络、本体）；不确定性推理（贝叶斯网络、模糊推理）；规划；专家系统简介；机器学习与深度学习概览；人工智能伦理。',
        'teaching_methods': '讲授+案例研讨+AI实验',
        'assessment_methods': '平时20%+项目报告30%+期末50%',
        'reference_materials': '《人工智能：一种现代方法》Russell & Norvig；《人工智能》李开复',
        'prerequisite_courses': '数据结构,概率论与数理统计',
    },
    {
        'course_code': 'IST202',
        'course_name': '机器学习',
        'course_name_en': 'Machine Learning',
        'credit': '4.0',
        'semester': 'spring',
        'course_objectives': '系统掌握监督学习、无监督学习、强化学习的主要算法原理与实现，理解模型评估、过拟合、正则化等核心概念，能运用机器学习方法解决实际问题。',
        'course_content': '机器学习概述；线性回归与逻辑回归；损失函数与梯度下降；正则化（L1、L2）；模型评估与交叉验证；偏差-方差分解；决策树与随机森林；支持向量机SVM与核方法；朴素贝叶斯；K近邻；K-Means与层次聚类；降维（PCA、t-SNE）；集成学习（Boosting、XGBoost）；神经网络基础；强化学习（Q-Learning）入门。使用scikit-learn进行实战。',
        'teaching_methods': '讲授+Kaggle项目实战',
        'assessment_methods': '平时20%+课程项目40%+期末40%',
        'reference_materials': '《机器学习》周志华；《统计学习方法》李航；《Pattern Recognition and ML》Bishop',
        'prerequisite_courses': '概率论与数理统计,线性代数,程序设计基础',
    },
    {
        'course_code': 'IST203',
        'course_name': '深度学习',
        'course_name_en': 'Deep Learning',
        'credit': '4.0',
        'semester': 'autumn',
        'course_objectives': '深入理解神经网络的前向传播与反向传播原理，掌握卷积神经网络、循环神经网络、Transformer等主流架构，能使用PyTorch实现深度学习模型解决图像与序列任务。',
        'course_content': '神经网络基础（感知机、多层感知机MLP）；前向传播与反向传播算法；激活函数（ReLU、Sigmoid、Tanh）；损失函数（交叉熵、MSE）；优化算法（梯度下降、SGD、Adam）；正则化（Dropout、BatchNorm）；卷积神经网络CNN（卷积层、池化层、LeNet、ResNet）；循环神经网络RNN与LSTM、GRU；注意力机制与Transformer；生成对抗网络GAN；自编码器与VAE；迁移学习与微调。使用PyTorch框架实战。',
        'teaching_methods': '讲授+PyTorch实验+论文阅读',
        'assessment_methods': '平时20%+课程项目40%+期末40%',
        'reference_materials': '《深度学习》Ian Goodfellow；《动手学深度学习》李沐',
        'prerequisite_courses': '机器学习,线性代数',
    },
    {
        'course_code': 'IST204',
        'course_name': '模式识别',
        'course_name_en': 'Pattern Recognition',
        'credit': '3.0',
        'semester': 'spring',
        'course_objectives': '掌握统计模式识别的基本理论与方法，理解特征提取、分类器设计、聚类分析等核心环节，能运用模式识别技术解决图像与信号识别问题。',
        'course_content': '模式识别概述；贝叶斯决策理论；概率密度估计（参数估计与非参数估计）；线性判别函数与Fisher线性判别；支持向量机在模式识别中的应用；近邻法则；特征提取与选择（PCA、LDA）；聚类分析（K-Means、层次聚类、DBSCAN）；隐马尔可夫模型HMM；模式识别在图像识别、语音识别中的应用。与机器学习有部分内容重叠，但更侧重统计决策与特征工程。',
        'teaching_methods': '讲授+模式识别实验',
        'assessment_methods': '平时20%+实验30%+期末50%',
        'reference_materials': '《模式识别》边肇祺；《Pattern Classification》Duda',
        'prerequisite_courses': '概率论与数理统计,线性代数',
    },
    {
        'course_code': 'IST301',
        'course_name': '计算机视觉',
        'course_name_en': 'Computer Vision',
        'credit': '3.0',
        'semester': 'spring',
        'course_objectives': '掌握图像处理与计算机视觉的基本原理与方法，理解图像特征提取、目标检测、图像分割等任务，能使用深度学习方法构建视觉识别系统。',
        'course_content': '计算机视觉概述；图像采集与数字化；图像预处理（灰度化、滤波、边缘检测Sobel/Canny）；图像特征（HOG、SIFT、SURF）；图像分类与卷积神经网络CNN；目标检测（R-CNN系列、YOLO、SSD）；图像分割（语义分割FCN、U-Net、实例分割Mask R-CNN）；人脸识别；姿态估计；视觉Transformer（ViT）；目标跟踪。使用OpenCV与PyTorch实战。',
        'teaching_methods': '讲授+视觉项目实战',
        'assessment_methods': '平时20%+项目40%+期末40%',
        'reference_materials': '《计算机视觉：算法与应用》Szeliski；《动手学计算机视觉》',
        'prerequisite_courses': '深度学习,线性代数',
    },
    {
        'course_code': 'IST302',
        'course_name': '自然语言处理',
        'course_name_en': 'Natural Language Processing',
        'credit': '3.0',
        'semester': 'spring',
        'course_objectives': '掌握自然语言处理的基本理论与方法，理解词法分析、句法分析、语义理解等任务，能使用深度学习方法构建文本处理与语言模型系统。',
        'course_content': '自然语言处理概述；中文分词（HMM、CRF）；词性标注与命名实体识别；词向量（Word2Vec、GloVe）；句法分析（依存句法、成分句法）；文本分类与情感分析；序列标注；机器翻译（Seq2Seq、注意力机制）；预训练语言模型（BERT、GPT、Transformer）；问答系统与对话系统；大语言模型与Prompt工程。使用HuggingFace Transformers实战。',
        'teaching_methods': '讲授+NLP项目实战',
        'assessment_methods': '平时20%+项目40%+期末40%',
        'reference_materials': '《自然语言处理实战》；《Speech and Language Processing》Jurafsky',
        'prerequisite_courses': '深度学习,概率论与数理统计',
    },
]

# 课程关联关系（源课程代码, 目标课程代码, 关联类型, 描述, 强度）
RELATIONS = [
    ('IST101', 'IST102', 'related', '高等数学与线性代数共同构成工科数学基础，相互渗透', 75),
    ('IST101', 'IST103', 'prerequisite', '概率统计需要极限、微积分等高数知识作为前置', 85),
    ('IST102', 'IST103', 'related', '线性代数的矩阵、向量在多元概率分布中广泛使用', 70),
    ('IST104', 'IST105', 'prerequisite', '数据结构需要程序设计基础作为编码工具', 90),
    ('IST105', 'IST106', 'prerequisite', '算法设计与分析建立在数据结构之上', 90),
    ('IST101', 'IST202', 'prerequisite', '机器学习中的梯度、优化依赖微积分基础', 80),
    ('IST102', 'IST202', 'prerequisite', '机器学习大量使用矩阵运算与特征值分解', 85),
    ('IST103', 'IST202', 'prerequisite', '机器学习的概率模型依赖概率统计', 90),
    ('IST103', 'IST201', 'prerequisite', '人工智能中的不确定性推理需要概率论', 75),
    ('IST105', 'IST201', 'prerequisite', 'AI搜索与知识表示需要数据结构基础', 70),
    ('IST201', 'IST202', 'advanced', '机器学习是人工智能的核心子领域进阶', 80),
    ('IST202', 'IST203', 'advanced', '深度学习是机器学习的进阶方向，神经网络是其子集', 95),
    ('IST202', 'IST204', 'related', '机器学习与模式识别在分类、聚类上高度重叠', 85),
    ('IST203', 'IST204', 'complementary', '深度学习与模式识别在特征学习上互补', 65),
    ('IST203', 'IST301', 'advanced', '计算机视觉深度依赖深度学习（CNN）', 90),
    ('IST203', 'IST302', 'advanced', '自然语言处理深度依赖深度学习（Transformer）', 90),
    ('IST102', 'IST203', 'prerequisite', '深度学习的矩阵运算、反向传播依赖线性代数', 85),
    ('IST301', 'IST302', 'related', 'CV与NLP同为深度学习应用方向，方法可迁移', 60),
    ('IST106', 'IST201', 'complementary', '算法设计中的搜索策略与AI搜索相呼应', 55),
    ('IST104', 'IST202', 'prerequisite', '机器学习实验需要Python编程能力', 80),
]


class Command(BaseCommand):
    help = '种子智能科学与技术专业课程大纲数据'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fresh',
            action='store_true',
            help='先清空现有大纲/关联/知识点再创建（谨慎使用）',
        )

    def handle(self, *args, **options):
        fresh = options.get('fresh', False)

        if fresh:
            KnowledgePoint.objects.all().delete()
            CourseRelation.objects.all().delete()
            SyllabusDuplicate = self._get_duplicate_model()
            if SyllabusDuplicate:
                SyllabusDuplicate.objects.all().delete()
            # 仅清理 IST 开头的课程，保留其它
            CourseSyllabus.objects.filter(course_code__startswith='IST').delete()
            self.stdout.write(self.style.WARNING('已清空 IST 课程及关联数据'))

        created_courses = {}
        updated = 0
        for c in COURSES:
            obj, created = CourseSyllabus.objects.update_or_create(
                course_code=c['course_code'],
                defaults={
                    'course_name': c['course_name'],
                    'course_name_en': c['course_name_en'],
                    'credit': c['credit'],
                    'semester': c['semester'],
                    'grade': GRADE,
                    'major': MAJOR,
                    'teacher_name': '待分配',
                    'course_objectives': c['course_objectives'],
                    'course_content': c['course_content'],
                    'teaching_methods': c['teaching_methods'],
                    'assessment_methods': c['assessment_methods'],
                    'reference_materials': c['reference_materials'],
                    'prerequisite_courses': c['prerequisite_courses'],
                },
            )
            created_courses[c['course_code']] = obj
            if created:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'课程数据就绪：新建 {updated} 门，共 {len(created_courses)} 门 IST 课程'
        ))

        # 建立课程关联
        rel_created = 0
        for src_code, tgt_code, rel_type, desc, strength in RELATIONS:
            src = created_courses.get(src_code)
            tgt = created_courses.get(tgt_code)
            if not src or not tgt:
                continue
            _, r_created = CourseRelation.objects.get_or_create(
                source_course=src,
                target_course=tgt,
                relation_type=rel_type,
                defaults={
                    'description': desc,
                    'strength': strength,
                    'verified': True,
                },
            )
            if r_created:
                rel_created += 1

        self.stdout.write(self.style.SUCCESS(
            f'课程关联就绪：新建 {rel_created} 条关联'
        ))

        self.stdout.write(self.style.WARNING(
            '\n下一步建议：\n'
            '  1. 调用 POST /syllabus/extract_knowledge_points 提取全部课程知识点\n'
            '  2. 调用 POST /syllabus/check_duplicates 进行知识点维度查重\n'
            '  3. 访问教师端「内容查重」「课程关联」页面查看效果'
        ))

    @staticmethod
    def _get_duplicate_model():
        try:
            from chat.models import SyllabusDuplicate
            return SyllabusDuplicate
        except Exception:
            return None

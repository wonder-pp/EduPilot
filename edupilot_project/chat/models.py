from django.db import models


class CourseSyllabus(models.Model):
    SEMESTER_CHOICES = [
        ('spring', '春季学期'),
        ('autumn', '秋季学期'),
    ]
    
    course_code = models.CharField(max_length=50, unique=True, verbose_name='课程代码')
    course_name = models.CharField(max_length=200, verbose_name='课程名称')
    course_name_en = models.CharField(max_length=200, blank=True, verbose_name='英文名称')
    credit = models.DecimalField(max_digits=4, decimal_places=2, verbose_name='学分')
    semester = models.CharField(max_length=10, choices=SEMESTER_CHOICES, verbose_name='开课学期')
    grade = models.CharField(max_length=20, verbose_name='适用年级')
    major = models.CharField(max_length=100, verbose_name='适用专业')
    teacher_name = models.CharField(max_length=100, verbose_name='授课教师')
    created_by = models.ForeignKey('UserProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_courses', verbose_name='创建教师')
    course_objectives = models.TextField(verbose_name='课程目标')
    course_content = models.TextField(verbose_name='课程内容')
    teaching_methods = models.TextField(blank=True, verbose_name='教学方法')
    assessment_methods = models.TextField(blank=True, verbose_name='考核方式')
    reference_materials = models.TextField(blank=True, verbose_name='参考资料')
    prerequisite_courses = models.CharField(max_length=500, blank=True, verbose_name='先修课程')
    file_upload = models.FileField(upload_to='syllabus/', blank=True, verbose_name='大纲文件')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    def __str__(self):
        return f"{self.course_code} - {self.course_name}"
    
    class Meta:
        verbose_name = '课程大纲'
        verbose_name_plural = '课程大纲'


class SyllabusDuplicate(models.Model):
    syllabus1 = models.ForeignKey(CourseSyllabus, on_delete=models.CASCADE, related_name='duplicate_source', verbose_name='课程1')
    syllabus2 = models.ForeignKey(CourseSyllabus, on_delete=models.CASCADE, related_name='duplicate_target', verbose_name='课程2')
    similarity_score = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='相似度')
    duplicate_content = models.TextField(blank=True, verbose_name='重复内容摘要')
    status = models.CharField(max_length=20, choices=[
        ('pending', '待处理'),
        ('confirmed', '已确认'),
        ('resolved', '已解决'),
    ], default='pending', verbose_name='状态')
    checked_at = models.DateTimeField(null=True, blank=True, verbose_name='检测时间')
    
    def __str__(self):
        return f"{self.syllabus1.course_name} vs {self.syllabus2.course_name} ({self.similarity_score}%)"
    
    class Meta:
        verbose_name = '大纲查重结果'
        verbose_name_plural = '大纲查重结果'


class CourseRelation(models.Model):
    RELATION_TYPE_CHOICES = [
        ('prerequisite', '先修'),
        ('corequisite', '同修'),
        ('advanced', '进阶'),
        ('related', '关联'),
        ('complementary', '互补'),
    ]
    
    source_course = models.ForeignKey(CourseSyllabus, on_delete=models.CASCADE, related_name='outgoing_relations', verbose_name='源课程')
    target_course = models.ForeignKey(CourseSyllabus, on_delete=models.CASCADE, related_name='incoming_relations', verbose_name='目标课程')
    relation_type = models.CharField(max_length=20, choices=RELATION_TYPE_CHOICES, verbose_name='关联类型')
    description = models.TextField(blank=True, verbose_name='关联描述')
    strength = models.IntegerField(default=50, verbose_name='关联强度(1-100)')
    verified = models.BooleanField(default=False, verbose_name='已验证')
    
    def __str__(self):
        return f"{self.source_course.course_name} -> {self.target_course.course_name} ({self.get_relation_type_display()})"
    
    class Meta:
        verbose_name = '课程关联'
        verbose_name_plural = '课程关联'


class SeniorMentor(models.Model):
    GRADUATION_YEAR_CHOICES = [(str(y), str(y)) for y in range(2010, 2030)]
    
    name = models.CharField(max_length=100, verbose_name='姓名')
    avatar = models.ImageField(upload_to='senior_avatars/', blank=True, verbose_name='头像')
    major = models.CharField(max_length=100, verbose_name='专业')
    graduation_year = models.CharField(max_length=4, choices=GRADUATION_YEAR_CHOICES, verbose_name='毕业年份')
    current_status = models.CharField(max_length=200, verbose_name='当前状态')
    company = models.CharField(max_length=200, blank=True, verbose_name='就职单位')
    position = models.CharField(max_length=100, blank=True, verbose_name='职位')
    education_background = models.TextField(verbose_name='教育背景')
    experience_summary = models.TextField(verbose_name='经验总结')
    skills = models.CharField(max_length=500, blank=True, verbose_name='技能标签')
    achievements = models.TextField(blank=True, verbose_name='主要成就')
    advice = models.TextField(blank=True, verbose_name='给学弟学妹的建议')
    contact_available = models.BooleanField(default=True, verbose_name='可联系')
    mentor_type = models.CharField(max_length=20, choices=[
        ('academic', '学术导师'),
        ('career', '职业导师'),
        ('competition', '竞赛导师'),
        ('life', '生活导师'),
    ], default='career', verbose_name='导师类型')
    tags = models.CharField(max_length=500, blank=True, verbose_name='标签')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    def __str__(self):
        return f"{self.name} ({self.major} {self.graduation_year})"
    
    class Meta:
        verbose_name = '学长导师'
        verbose_name_plural = '学长导师'


class AnonymousFeedback(models.Model):
    FEEDBACK_TYPE_CHOICES = [
        ('course', '课程反馈'),
        ('teacher', '教师评价'),
        ('facility', '设施建议'),
        ('management', '管理建议'),
        ('other', '其他'),
    ]
    
    feedback_type = models.CharField(max_length=20, choices=FEEDBACK_TYPE_CHOICES, verbose_name='反馈类型')
    title = models.CharField(max_length=200, verbose_name='标题')
    content = models.TextField(verbose_name='反馈内容')
    rating = models.IntegerField(default=5, verbose_name='评分(1-5星)')
    severity = models.CharField(max_length=10, default='medium', choices=[('low','低'),('medium','中'),('high','高')], verbose_name='严重程度')
    tags = models.CharField(max_length=300, blank=True, verbose_name='标签(逗号分隔)')
    related_course = models.ForeignKey(CourseSyllabus, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='关联课程')
    target_teacher = models.ForeignKey('UserProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='feedbacks', verbose_name='目标教师')
    is_anonymous = models.BooleanField(default=True, verbose_name='匿名')
    is_public = models.BooleanField(default=False, verbose_name='公开反馈')
    is_resolved = models.BooleanField(default=False, verbose_name='已解决')
    resolution_content = models.TextField(blank=True, verbose_name='处理结果')
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name='处理时间')
    image = models.ImageField(upload_to='feedback_images/', blank=True, verbose_name='反馈图片')
    created_by = models.ForeignKey('UserProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_feedbacks', verbose_name='提交者')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='提交时间')
    
    def __str__(self):
        return f"{self.get_feedback_type_display()}: {self.title}"
    
    class Meta:
        verbose_name = '匿名反馈'
        verbose_name_plural = '匿名反馈'


class ExcellentWork(models.Model):
    WORK_TYPE_CHOICES = [
        ('thesis', '毕业论文'),
        ('design', '设计作品'),
        ('competition', '竞赛作品'),
        ('research', '科研成果'),
        ('innovation', '创新项目'),
        ('other', '其他'),
    ]
    
    title = models.CharField(max_length=300, verbose_name='作品名称')
    description = models.TextField(verbose_name='作品描述')
    work_type = models.CharField(max_length=20, choices=WORK_TYPE_CHOICES, verbose_name='作品类型')
    author_name = models.CharField(max_length=100, verbose_name='作者姓名')
    author_major = models.CharField(max_length=100, verbose_name='作者专业')
    author_graduation_year = models.CharField(max_length=4, verbose_name='毕业年份')
    supervisor = models.CharField(max_length=100, blank=True, verbose_name='指导教师')
    awards = models.CharField(max_length=500, blank=True, verbose_name='获奖情况')
    cover_image = models.ImageField(upload_to='excellent_works/', blank=True, verbose_name='封面图片')
    file_upload = models.FileField(upload_to='excellent_works/', blank=True, verbose_name='作品文件')
    link = models.URLField(blank=True, verbose_name='外部链接')
    is_featured = models.BooleanField(default=False, verbose_name='精选展示')
    created_by = models.ForeignKey('UserProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_works', verbose_name='创建教师')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    def __str__(self):
        return self.title
    
    class Meta:
        verbose_name = '优秀作品'
        verbose_name_plural = '优秀作品'


class SeniorEmployment(models.Model):
    EMPLOYMENT_TYPE_CHOICES = [
        ('fulltime', '全职工作'),
        ('graduate', '升学'),
        ('study_abroad', '出国留学'),
        ('startup', '创业'),
        ('other', '其他'),
    ]
    
    senior = models.ForeignKey(SeniorMentor, on_delete=models.CASCADE, related_name='employment', verbose_name='学长')
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, verbose_name='就业类型')
    company_name = models.CharField(max_length=200, verbose_name='单位名称')
    company_logo = models.ImageField(upload_to='company_logos/', blank=True, verbose_name='单位Logo')
    industry = models.CharField(max_length=100, verbose_name='所属行业')
    position = models.CharField(max_length=100, verbose_name='职位')
    department = models.CharField(max_length=100, blank=True, verbose_name='部门')
    salary_range = models.CharField(max_length=50, blank=True, verbose_name='薪资范围')
    location = models.CharField(max_length=100, verbose_name='工作地点')
    work_summary = models.TextField(blank=True, verbose_name='工作心得')
    recruitment_tips = models.TextField(blank=True, verbose_name='求职建议')
    is_featured = models.BooleanField(default=False, verbose_name='精选展示')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    def __str__(self):
        return f"{self.senior.name} - {self.company_name} ({self.position})"
    
    class Meta:
        verbose_name = '学长就业'
        verbose_name_plural = '学长就业'


class KnowledgePoint(models.Model):
    course = models.ForeignKey(CourseSyllabus, on_delete=models.CASCADE, related_name='knowledge_points', verbose_name='所属课程')
    point_name = models.CharField(max_length=200, verbose_name='知识点名称')
    point_category = models.CharField(max_length=100, blank=True, verbose_name='知识点类别')
    description = models.TextField(blank=True, verbose_name='知识点描述')
    importance = models.IntegerField(default=50, verbose_name='重要程度(1-100)')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    def __str__(self):
        return f"{self.point_name} ({self.course.course_name})"
    
    class Meta:
        verbose_name = '知识点'
        verbose_name_plural = '知识点'


class CourseAnalysisReport(models.Model):
    course = models.OneToOneField(CourseSyllabus, on_delete=models.CASCADE, related_name='analysis_report', verbose_name='课程')
    ai_extracted_objectives = models.JSONField(blank=True, null=True, verbose_name='AI提取的课程目标')
    ai_extracted_points = models.JSONField(blank=True, null=True, verbose_name='AI提取的知识点')
    optimization_suggestions = models.TextField(blank=True, verbose_name='优化建议')
    coverage_analysis = models.JSONField(blank=True, null=True, verbose_name='知识点覆盖分析')
    generated_at = models.DateTimeField(auto_now_add=True, verbose_name='生成时间')
    
    def __str__(self):
        return f"分析报告: {self.course.course_name}"
    
    class Meta:
        verbose_name = '课程分析报告'
        verbose_name_plural = '课程分析报告'


class FeedbackAnalysis(models.Model):
    feedback = models.OneToOneField(AnonymousFeedback, on_delete=models.CASCADE, related_name='analysis', verbose_name='反馈')
    sentiment_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='情感得分(-1到1)')
    sentiment_label = models.CharField(max_length=20, blank=True, verbose_name='情感标签')
    topics = models.JSONField(blank=True, null=True, verbose_name='主题分类')
    keywords = models.JSONField(blank=True, null=True, verbose_name='关键词')
    summary = models.TextField(blank=True, verbose_name='反馈摘要')
    analyzed_at = models.DateTimeField(auto_now_add=True, verbose_name='分析时间')
    
    def __str__(self):
        return f"分析: {self.feedback.title}"
    
    class Meta:
        verbose_name = '反馈分析'
        verbose_name_plural = '反馈分析'


class GrowthPath(models.Model):
    user = models.ForeignKey('UserProfile', on_delete=models.CASCADE, related_name='growth_paths', verbose_name='用户')
    path_type = models.CharField(max_length=20, choices=[
        ('graduate_exam', '考研'),
        ('graduate_recommend', '保研'),
        ('employment', '就业'),
        ('research', '科研'),
        ('competition', '竞赛'),
        ('study_abroad', '出国留学'),
    ], verbose_name='路径类型')
    path_name = models.CharField(max_length=200, verbose_name='路径名称')
    stages = models.JSONField(blank=True, null=True, verbose_name='阶段规划')
    recommended_courses = models.JSONField(blank=True, null=True, verbose_name='推荐课程')
    resources = models.JSONField(blank=True, null=True, verbose_name='推荐资源')
    estimated_duration = models.CharField(max_length=100, blank=True, verbose_name='预计时长')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    def __str__(self):
        return f"{self.path_name} - {self.user.username}"
    
    class Meta:
        verbose_name = '成长路径'
        verbose_name_plural = '成长路径'


class TeacherCourse(models.Model):
    teacher = models.ForeignKey('UserProfile', on_delete=models.CASCADE, related_name='teaching_courses', verbose_name='教师')
    course = models.ForeignKey(CourseSyllabus, on_delete=models.CASCADE, related_name='teachers', verbose_name='课程')
    semester = models.CharField(max_length=10, choices=[
        ('spring', '春季学期'),
        ('autumn', '秋季学期'),
    ], verbose_name='学期')
    academic_year = models.CharField(max_length=10, verbose_name='学年')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    def __str__(self):
        return f"{self.teacher.username} - {self.course.course_name}"
    
    class Meta:
        verbose_name = '教师授课'
        verbose_name_plural = '教师授课'
        unique_together = ('teacher', 'course', 'semester', 'academic_year')


class StudentCourse(models.Model):
    student = models.ForeignKey('UserProfile', on_delete=models.CASCADE, related_name='enrolled_courses', verbose_name='学生')
    course = models.ForeignKey(CourseSyllabus, on_delete=models.CASCADE, related_name='students', verbose_name='课程')
    semester = models.CharField(max_length=10, choices=[
        ('spring', '春季学期'),
        ('autumn', '秋季学期'),
    ], verbose_name='学期')
    academic_year = models.CharField(max_length=10, verbose_name='学年')
    grade = models.CharField(max_length=20, blank=True, verbose_name='成绩')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='选课时间')
    
    def __str__(self):
        return f"{self.student.username} - {self.course.course_name}"
    
    class Meta:
        verbose_name = '学生选课'
        verbose_name_plural = '学生选课'
        unique_together = ('student', 'course', 'semester', 'academic_year')


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('student', '学生'),
        ('teacher', '教师'),
        ('admin', '管理员'),
    ]
    
    user_id = models.CharField(max_length=50, unique=True, verbose_name='用户ID')
    username = models.CharField(max_length=100, verbose_name='用户名')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student', verbose_name='角色')
    grade = models.CharField(max_length=20, blank=True, verbose_name='年级')
    major = models.CharField(max_length=100, blank=True, verbose_name='专业')
    gpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True, verbose_name='GPA')
    rank = models.CharField(max_length=50, blank=True, verbose_name='排名')
    awards = models.TextField(blank=True, verbose_name='获奖记录')
    research = models.TextField(blank=True, verbose_name='科研经历')
    goal = models.TextField(blank=True, verbose_name='未来目标')
    department = models.CharField(max_length=100, blank=True, verbose_name='所属院系')
    position = models.CharField(max_length=100, blank=True, verbose_name='职位')
    email = models.CharField(max_length=100, blank=True, verbose_name='邮箱')
    phone = models.CharField(max_length=20, blank=True, verbose_name='联系电话')
    hometown = models.CharField(max_length=100, blank=True, verbose_name='家乡地（省份/城市）')
    profile_completed = models.BooleanField(default=False, verbose_name='信息已完善')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    def __str__(self):
        return self.username
    
    class Meta:
        verbose_name = '用户档案'
        verbose_name_plural = '用户档案'
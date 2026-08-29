from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login', views.login, name='login'),
    path('register', views.register, name='register'),
    path('ask', views.ask, name='ask'),

    # 课程大纲管理
    path('syllabus/upload', views.syllabus_upload, name='syllabus_upload'),
    path('syllabus/list', views.syllabus_list, name='syllabus_list'),
    path('syllabus/<int:syllabus_id>', views.syllabus_detail, name='syllabus_detail'),
    path('syllabus/<int:syllabus_id>/update', views.syllabus_update, name='syllabus_update'),
    path('syllabus/<int:syllabus_id>/delete', views.syllabus_delete, name='syllabus_delete'),
    
    # 课程查重
    path('syllabus/extract_knowledge_points', views.extract_knowledge_points_view, name='extract_knowledge_points'),
    path('syllabus/<int:syllabus_id>/knowledge_points', views.course_knowledge_points, name='course_knowledge_points'),
    path('duplicate/check_for_syllabus', views.duplicate_check_for_syllabus, name='duplicate_check_for_syllabus'),
    
    # 课程关联
    path('course/relations', views.course_relations, name='course_relations'),
    path('course/relation/create', views.course_relation_create, name='course_relation_create'),
    path('course/relation/graph', views.course_relation_graph, name='course_relation_graph'),
    path('course/knowledge_graph', views.course_knowledge_graph, name='course_knowledge_graph'),
    path('relations/list', views.course_relation_graph, name='relations_list'),
    path('course/relation/<int:relation_id>/delete', views.course_relation_delete, name='course_relation_delete'),
    path('course/relation/<int:relation_id>/verify', views.course_relation_verify, name='course_relation_verify'),

    # 匿名反馈
    path('feedback/list', views.feedback_list, name='feedback_list'),
    path('feedback/create', views.feedback_create, name='feedback_create'),
    path('feedback/<int:feedback_id>/resolve', views.feedback_resolve, name='feedback_resolve'),
    path('feedback/<int:feedback_id>/delete', views.feedback_delete, name='feedback_delete'),
    path('feedback/<int:feedback_id>/clear_resolution', views.feedback_clear_resolution, name='feedback_clear_resolution'),
    
    # 优秀作品
    path('work/list', views.excellent_work_list, name='excellent_work_list'),
    path('works/list', views.excellent_work_list, name='excellent_work_list_plural'),
    path('work/<int:work_id>', views.excellent_work_detail, name='excellent_work_detail'),
    path('work/create', views.excellent_work_create, name='excellent_work_create'),
    path('work/<int:work_id>/update', views.excellent_work_update, name='excellent_work_update'),
    path('work/<int:work_id>/delete', views.excellent_work_delete, name='excellent_work_delete'),
    
    # 学长就业
    path('employment/list', views.senior_employment_list, name='senior_employment_list'),
    path('employment/<int:employment_id>', views.senior_employment_detail, name='senior_employment_detail'),
    path('employment/create', views.senior_employment_create, name='senior_employment_create'),
    path('employment/<int:employment_id>/update', views.senior_employment_update, name='senior_employment_update'),
    path('employment/<int:employment_id>/delete', views.senior_employment_delete, name='senior_employment_delete'),
    
    # 成长路径
    path('growth_path/list', views.user_growth_paths, name='growth_path_list'),
    
    # AI智能分析
    path('ai/analyze_syllabus', views.ai_analyze_syllabus, name='ai_analyze_syllabus'),
    path('ai/feedback_summary', views.feedback_analysis_summary, name='feedback_analysis_summary'),
    path('ai/generate_growth_path', views.ai_generate_growth_path, name='ai_generate_growth_path'),
    path('ai/user_growth_paths', views.user_growth_paths, name='user_growth_paths'),
    
    # 权限与角色
    path('user/get_current', views.get_current_user, name='get_current_user'),
    # 数据概览
    path('api/data_overview', views.data_overview, name='data_overview'),
]
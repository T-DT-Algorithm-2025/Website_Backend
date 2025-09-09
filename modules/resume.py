import os
from flask import request, jsonify, session, send_file
from core.global_params import flask_app, global_config
import logging
import datetime

from utils import SQL

available_positions = ['算法组', '电控组', '机械组', '运营组']
available_2st_positions = ['运营组']

logger = logging.getLogger(__name__)

@flask_app.route('/recruit/apply', methods=['POST'])
async def apply_recruit():
    """
    提交招聘申请
    """
    uid = session['uid'] if 'uid' in session else None
    if not uid:
        return jsonify(success=False, error="用户未登录")
    
    data = request.json
    recruit_id = data.get('recruit_id')
    if not recruit_id:
        return jsonify(success=False, error="未提供招聘ID")
    resume_text = data.get('resume_text', '')
    submit_time = datetime.datetime.now()
    status = 0  # 初始状态为未处理
    first_choice = data.get('1st_choice', '')
    if not first_choice:
        return jsonify(success=False, error="必须提供第一志愿")
    if first_choice not in available_positions:
        return jsonify(success=False, error="第一志愿选择无效")
    second_choice = data.get('2nd_choice', '')
    if second_choice and second_choice not in available_2st_positions:
        return jsonify(success=False, error="第二志愿选择无效")
    if first_choice == second_choice and second_choice != '':
        return jsonify(success=False, error="第一志愿和第二志愿不能相同")
    self_intro = data.get('self_intro', '')
    if not self_intro:
        return jsonify(success=False, error="自我介绍不能为空")
    skills = data.get('skills', '')
    if not skills:
        return jsonify(success=False, error="技能不能为空")
    projects = data.get('projects', '')
    if not projects:
        return jsonify(success=False, error="项目经历不能为空")
    awards = data.get('awards', '')
    if not awards:
        return jsonify(success=False, error="获奖经历不能为空")
    grade_point = data.get('grade_point', '')
    grade_rank = data.get('grade_rank', '')
    additional_file = request.files['additional_file'] if 'additional_file' in request.files else None
    additional_file_path = ''
    real_head_img = request.files['real_head_img'] if 'real_head_img' in request.files else None
    if not real_head_img:
        return jsonify(success=False, error="必须上传正面照")
    if not real_head_img.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
        return jsonify(success=False, error="正面照格式不支持,仅支持png/jpg/jpeg")
    if not os.path.exists('photos'):
        os.makedirs('photos')
    real_head_img_path = f'photos/{uid}_{recruit_id}_{int(datetime.datetime.now().timestamp())}_real.jpg'
    real_head_img.save(real_head_img_path)

    if additional_file:
        filename = additional_file.filename
        if '.' in filename and filename.rsplit('.', 1)[1].lower() in global_config.get('allowed_content_extensions', []):
            save_path = os.path.join('uploads', f"{uid}_{recruit_id}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}")
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            additional_file.save(save_path)
            additional_file_path = save_path
        else:
            return jsonify(success=False, error="附加文件格式不支持")
    
    submit_id = f"{uid}_{recruit_id}_{int(datetime.datetime.now().timestamp())}"
    try:
        with SQL() as sql:
            sql.insert('resume_submit', {'submit_id': submit_id, 'uid': uid, 'recruit_id': recruit_id, 'submit_time': submit_time, 'status': status})
            sql.insert('resume_info', {
                'submit_id': submit_id,
                '1st_choice': first_choice,
                '2nd_choice': second_choice,
                'self_intro': self_intro,
                'skills': skills,
                'projects': projects,
                'awards': awards,
                'grade_point': grade_point,
                'grade_rank': grade_rank,
                'additional_file_path': additional_file_path
            })
            sql.insert('resume_user_real_head_img', {
                'uid': uid,
                'real_head_img_path': real_head_img_path
            })
        logger.info(f"User {uid} applied for recruit {recruit_id} with submit ID {submit_id}")
        return jsonify(success=True, submit_id=submit_id)
    except Exception as e:
        logger.error(f"Error applying for recruit: {e}")
        return jsonify(success=False, error="提交申请时发生错误")

@flask_app.route('/resume/download/<submit_id>', methods=['GET'])
async def download_additional_file(submit_id):
    """
    下载用户的附加文件
    """
    uid = session['uid'] if 'uid' in session else None
    if not uid:
        return jsonify(success=False, error="用户未登录")
    is_admin = False
    if 'uid' in session:
        with SQL() as sql:
            permission_info = sql.fetch_one('userpermission', {'uid': session['uid']})
            if permission_info and (permission_info.get('is_main_leader_admin') or permission_info.get('is_group_leader_admin')):
                is_admin = True

    try:
        with SQL() as sql:
            submit_info = sql.fetch_one("resume_submit", {'submit_id': submit_id})
            user_id = submit_info['uid'] if submit_info else None
            if not submit_info:
                return jsonify(success=False, error="未找到该简历")
            if user_id != uid and not is_admin:
                return jsonify(success=False, error="无权限下载该附加文件"), 403
            submission = sql.fetch_one("resume_info", {'submit_id': submit_id})
            if not submission or not submission['additional_file_path']:
                return jsonify(success=False, error="未找到附加文件")
            file_path = submission['additional_file_path']
            if not os.path.isfile(file_path):
                return jsonify(success=False, error="附加文件不存在")
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        logger.error(f"Error downloading additional file: {e}")
        return jsonify(success=False, error="下载附加文件时发生错误")
    
@flask_app.route('/resume/additional_file/name/<submit_id>', methods=['GET'])
async def get_additional_file_name(submit_id):
    """
    获取用户附加文件的原始文件名
    """
    uid = session['uid'] if 'uid' in session else None
    if not uid:
        return jsonify(success=False, error="用户未登录")
    
    is_admin = False
    if 'uid' in session:
        with SQL() as sql:
            permission_info = sql.fetch_one('userpermission', {'uid': session['uid']})
            if permission_info and (permission_info.get('is_main_leader_admin') or permission_info.get('is_group_leader_admin')):
                is_admin = True
    
    try:
        with SQL() as sql:
            submit_info = sql.fetch_one("resume_submit", {'submit_id': submit_id})
            user_id = submit_info['uid'] if submit_info else None
            if not submit_info:
                return jsonify(success=False, error="未找到该简历")
            if user_id != uid and not is_admin:
                return jsonify(success=False, error="无权限查看该附加文件名"), 403
            submission = sql.fetch_one("resume_info", {'submit_id': submit_id})
            if not submission or not submission['additional_file_path']:
                return jsonify(success=False, error="未找到附加文件")
            file_path = submission['additional_file_path']
            original_name = os.path.basename(file_path).split('_', 3)[-1]  # Assuming the original name is after the third underscore
        return jsonify(success=True, original_name=original_name)
    except Exception as e:
        logger.error(f"Error fetching additional file name: {e}")
        return jsonify(success=False, error="获取附加文件名时发生错误")
    
@flask_app.route('/resume/headimg/<submit_id>', methods=['GET'])
async def get_real_head_img(submit_id):
    """
    获取用户的正面照
    """
    uid = session['uid'] if 'uid' in session else None
    if not uid:
        return jsonify(success=False, error="用户未登录")
    is_admin = False
    if 'uid' in session:
        with SQL() as sql:
            permission_info = sql.fetch_one('userpermission', {'uid': session['uid']})
            if permission_info and (permission_info.get('is_main_leader_admin') or permission_info.get('is_group_leader_admin')):
                is_admin = True
    
    try:
        with SQL() as sql:
            submission = sql.fetch_one("resume_submit", {'submit_id': submit_id})
            if not submission:
                return jsonify(success=False, error="未找到该简历")
            user_id = submission['uid']
            if user_id != uid and not is_admin:
                return jsonify(success=False, error="无权限查看该正面照"), 403
            img_record = sql.fetch_one("resume_user_real_head_img", {'submit_id': submit_id})
            if not img_record or not img_record['real_head_img_path']:
                return jsonify(success=False, error="未找到正面照")
            img_path = img_record['real_head_img_path']
            if not os.path.isfile(img_path):
                return jsonify(success=False, error="正面照不存在")
        return send_file(img_path, mimetype='image/jpeg')
    except Exception as e:
        logger.error(f"Error fetching real head image: {e}")
        return jsonify(success=False, error="获取正面照时发生错误")
    
@flask_app.route('/recruit/positions', methods=['GET'])
async def get_available_positions():
    """
    获取可申请的职位列表
    """
    return jsonify(success=True, positions=available_positions, second_stage_positions=available_2st_positions)

@flask_app.route('/resume/info/<submit_id>', methods=['GET'])
async def get_resume_info(submit_id):
    """
    获取简历详细信息
    """
    uid = session['uid'] if 'uid' in session else None
    if not uid:
        return jsonify(success=False, error="用户未登录")
    is_admin = False
    if 'uid' in session:
        with SQL() as sql:
            permission_info = sql.fetch_one('userpermission', {'uid': session['uid']})
            if permission_info and (permission_info.get('is_main_leader_admin') or permission_info.get('is_group_leader_admin')):
                is_admin = True
    
    try:
        with SQL() as sql:
            submission = sql.fetch_one("resume_submit", {'submit_id': submit_id})
            user_id = submission['uid'] if submission else None
            if user_id != uid and not is_admin:
                return jsonify(success=False, error="无权限查看该简历"), 403
            info = sql.fetch_one("resume_info", {'submit_id': submit_id})
            if not info:
                return jsonify(success=False, error="未找到简历信息")
            status = submission.get('status', 0)
            status_name = sql.fetch_one("status_name", {'status_id': status})
            submission['status_name'] = status_name['status_name'] if status_name else "未知状态"
        return jsonify(success=True, submission=submission, info=info)
    except Exception as e:
        logger.error(f"Error fetching resume info: {e}")
        return jsonify(success=False, error="获取简历信息时发生错误")

@flask_app.route('/resume/list', methods=['GET'])
async def list_user_resumes():
    """
    列出当前用户的所有简历提交记录
    """
    uid = session['uid'] if 'uid' in session else None
    if not uid:
        return jsonify(success=False, error="用户未登录")

    if 'recruit_id' in request.json:
        recruit_id = request.json['recruit_id']
    else:
        recruit_id = None

    try:
        with SQL() as sql:
            submissions = sql.fetch_all("resume_submit", {'uid': uid})
            results = []
            for submission in submissions:
                status = submission.get('status', 0)
                status_name = sql.fetch_one("status_name", {'status_id': status})
                if recruit_id and submission['recruit_id'] != recruit_id:
                    continue
                result = {
                    'submit_id': submission['submit_id'],
                    'recruit_id': submission['recruit_id'],
                    'submit_time': submission['submit_time'].strftime('%Y-%m-%d %H:%M:%S'),
                    'status': status,
                    'status_name': status_name['status_name'] if status_name else "未知状态"
                }
                results.append(result)
        return jsonify(success=True, submissions=results)
    except Exception as e:
        logger.error(f"Error listing user resumes: {e}")
        return jsonify(success=False, error="获取简历列表时发生错误")
    
@flask_app.route('/resume/update/<submit_id>', methods=['POST'])
async def update_resume(submit_id):
    """
    更新已提交的简历
    """
    uid = session['uid'] if 'uid' in session else None
    if not uid:
        return jsonify(success=False, error="用户未登录")
    is_admin = False
    if 'uid' in session:
        with SQL() as sql:
            permission_info = sql.fetch_one('userpermission', {'uid': session['uid']})
            if permission_info and (permission_info.get('is_main_leader_admin') or permission_info.get('is_group_leader_admin')):
                is_admin = True
    try:
        with SQL() as sql:
            submission = sql.fetch_one("resume_submit", {'submit_id': submit_id})
            if not submission:
                return jsonify(success=False, error="未找到该简历")
            user_id = submission['uid']
            if user_id != uid and not is_admin:
                return jsonify(success=False, error="无权限修改该简历"), 403
    except Exception as e:
        logger.error(f"Error fetching resume for update: {e}")
        return jsonify(success=False, error="获取简历信息时发生错误")
    
    data = request.json
    first_choice = data.get('1st_choice', '')
    if not first_choice:
        return jsonify(success=False, error="必须提供第一志愿")
    if first_choice not in available_positions:
        return jsonify(success=False, error="第一志愿选择无效")
    second_choice = data.get('2nd_choice', '')
    if second_choice and second_choice not in available_2st_positions:
        return jsonify(success=False, error="第二志愿选择无效")
    if first_choice == second_choice and second_choice != '':
        return jsonify(success=False, error="第一志愿和第二志愿不能相同")
    self_intro = data.get('self_intro', '')
    if not self_intro:
        return jsonify(success=False, error="自我介绍不能为空")
    skills = data.get('skills', '')
    if not skills:
        return jsonify(success=False, error="技能不能为空")
    projects = data.get('projects', '')
    if not projects:
        return jsonify(success=False, error="项目经历不能为空")
    awards = data.get('awards', '')
    if not awards:
        return jsonify(success=False, error="获奖经历不能为空")
    grade_point = data.get('grade_point', '')
    grade_rank = data.get('grade_rank', '')
    additional_file_change = data.get('additional_file_change', False)
    additional_file = request.files['additional_file'] if 'additional_file' in request.files else None
    additional_file_path = ''
    if additional_file_change:
        if additional_file:
            filename = additional_file.filename
            if '.' in filename and filename.rsplit('.', 1)[1].lower() in global_config.get('allowed_content_extensions', []):
                save_path = os.path.join('uploads', f"{uid}_{submission['recruit_id']}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}")
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                additional_file.save(save_path)
                additional_file_path = save_path
            else:
                return jsonify(success=False, error="附加文件格式不支持")
        else:
            return jsonify(success=False, error="未提供新的附加文件")
    real_head_img_change = data.get('real_head_img_change', False)
    real_head_img = request.files['real_head_img'] if 'real_head_img' in request.files else None
    if real_head_img_change:
        if not real_head_img:
            return jsonify(success=False, error="必须上传正面照")
        if not real_head_img.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            return jsonify(success=False, error="正面照格式不支持,仅支持png/jpg/jpeg")
        if not os.path.exists('photos'):
            os.makedirs('photos')
        real_head_img_path = f'photos/{uid}_{submission["recruit_id"]}_{int(datetime.datetime.now().timestamp())}_real.jpg'
        real_head_img.save(real_head_img_path)
    try:
        with SQL() as sql:
            update_data = {
                '1st_choice': first_choice,
                '2nd_choice': second_choice,
                'self_intro': self_intro,
                'skills': skills,
                'projects': projects,
                'awards': awards,
                'grade_point': grade_point,
                'grade_rank': grade_rank
            }
            if additional_file_change and additional_file_path:
                update_data['additional_file_path'] = additional_file_path
            sql.update('resume_info', update_data, {'submit_id': submit_id})
            if real_head_img_change and real_head_img_path:
                sql.update('resume_user_real_head_img', {'real_head_img_path': real_head_img_path}, {'submit_id': submit_id})
        logger.info(f"User {uid} updated resume {submit_id}")
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"Error updating resume: {e}")
        return jsonify(success=False, error="更新简历时发生错误")
    
@flask_app.route('/resume/delete/<submit_id>', methods=['POST'])
async def delete_resume(submit_id):
    """
    删除已提交的简历
    """
    uid = session['uid'] if 'uid' in session else None
    if not uid:
        return jsonify(success=False, error="用户未登录")
    is_admin = False
    if 'uid' in session:
        with SQL() as sql:
            permission_info = sql.fetch_one('userpermission', {'uid': session['uid']})
            if permission_info and (permission_info.get('is_main_leader_admin') or permission_info.get('is_group_leader_admin')):
                is_admin = True
    try:
        with SQL() as sql:
            submission = sql.fetch_one("resume_submit", {'submit_id': submit_id})
            if not submission:
                return jsonify(success=False, error="未找到该简历")
            user_id = submission['uid']
            if user_id != uid and not is_admin:
                return jsonify(success=False, error="无权限删除该简历"), 403
            sql.delete('resume_submit', {'submit_id': submit_id})
            sql.delete('resume_info', {'submit_id': submit_id})
            sql.delete('resume_user_real_head_img', {'submit_id': submit_id})
        logger.info(f"User {uid} deleted resume {submit_id}")
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"Error deleting resume: {e}")
        return jsonify(success=False, error="删除简历时发生错误")
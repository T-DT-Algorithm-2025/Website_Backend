import os
import uuid
from flask import request, jsonify, session, send_file
from core.global_params import flask_app
import logging
import datetime

from utils import SQL

logger = logging.getLogger(__name__)

@flask_app.route('/resume/admin/list', methods=['GET'])
async def get_all_resumes():
    """
    获取所有简历的列表，管理员专用接口
    """
    if 'uid' not in session:
        return jsonify(success=False, error="未登录"), 401
    
    uid = session['uid']
    with SQL() as sql:
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        if not permission_info or not (permission_info.get('is_main_leader_admin') or permission_info.get('is_group_leader_admin')):
            return jsonify(success=False, error="权限不足"), 403
        
        resume_list = sql.fetch_all('resume_submit', columns=['submit_id', 'uid', 'recruit_id', 'submit_time', 'status'])
    
    if resume_list is not None:
        resume_info = []
        for item in resume_list:
            resume_info.append({
                'submit_id': item['submit_id'],
                'uid': item['uid'],
                'recruit_id': item['recruit_id'],
                'submit_time': item['submit_time'].strftime('%Y-%m-%d %H:%M:%S'),
                'status': item['status']
            })
        return jsonify(success=True, data=resume_info)
    else:
        return jsonify(success=False, error="未找到简历信息")
    
@flask_app.route('/resume/admin/batch/delete', methods=['POST'])
async def batch_delete_resumes():
    """
    批量删除简历，管理员专用接口
    请求体应包含 JSON 数组 "submit_ids"，表示要删除的简历提交ID列表
    """
    if 'uid' not in session:
        return jsonify(success=False, error="未登录"), 401
    
    uid = session['uid']
    with SQL() as sql:
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        if not permission_info or not (permission_info.get('is_main_leader_admin') or permission_info.get('is_group_leader_admin')):
            return jsonify(success=False, error="权限不足"), 403
    
    data = request.json
    if not data or 'submit_ids' not in data or not isinstance(data['submit_ids'], list):
        return jsonify(success=False, error="请求格式错误，应包含 'submit_ids' 列表"), 400
    
    submit_ids = data['submit_ids']
    if not all(isinstance(sid, str) for sid in submit_ids):
        return jsonify(success=False, error="'submit_ids' 列表中应全部为字符串"), 400
    
    try:
        with SQL() as sql:
            for submit_id in submit_ids:
                sql.delete('resume_submit', {'submit_id': submit_id})
                sql.delete('resume_info', {'submit_id': submit_id})
                sql.delete('resume_review', {'submit_id': submit_id})
                sql.delete('resume_user_real_head_img', {'submit_id': submit_id})
        return jsonify(success=True, message="简历批量删除成功")
    except Exception as e:
        logger.error(f"批量删除简历时出错: {e}")
        return jsonify(success=False, error="批量删除简历时出错"), 500
    
@flask_app.route('/resume/status_names', methods=['GET'])
async def get_resume_status_names():
    """
    获取简历状态名称列表
    """
    try:
        with SQL() as sql:
            status_list = sql.fetch_all('resume_status_names', columns=['status_id', 'status_name'])
        
        if status_list is not None:
            formatted_status = [{'status_id': item['status_id'], 'status_name': item['status_name']} for item in status_list]
            return jsonify(success=True, data=formatted_status)
        else:
            return jsonify(success=False, error="未找到状态名称")
    except Exception as e:
        logger.error(f"获取简历状态名称时出错: {e}")
        return jsonify(success=False, error="获取简历状态名称时出错"), 500
    
@flask_app.route('/resume/admin/batch/update_status', methods=['POST'])
async def batch_update_resume_status():
    """
    批量更新简历状态，管理员专用接口
    请求体应包含 JSON 数组 "submit_ids" 和整数 "new_status"
    """
    if 'uid' not in session:
        return jsonify(success=False, error="未登录"), 401
    
    uid = session['uid']
    with SQL() as sql:
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        if not permission_info or not (permission_info.get('is_main_leader_admin') or permission_info.get('is_group_leader_admin')):
            return jsonify(success=False, error="权限不足"), 403
    
    data = request.json
    if not data or 'submit_ids' not in data or 'new_status' not in data:
        return jsonify(success=False, error="请求格式错误，应包含 'submit_ids' 列表和 'new_status' 整数"), 400
    
    submit_ids = data['submit_ids']
    new_status = data['new_status']
    
    if not isinstance(submit_ids, list) or not all(isinstance(sid, str) for sid in submit_ids):
        return jsonify(success=False, error="'submit_ids' 应为字符串列表"), 400
    if not isinstance(new_status, int):
        return jsonify(success=False, error="'new_status' 应为整数"), 400
    
    try:
        with SQL() as sql:
            for submit_id in submit_ids:
                sql.update('resume_submit', {'status': new_status}, {'submit_id': submit_id})
        return jsonify(success=True, message="简历状态批量更新成功")
    except Exception as e:
        logger.error(f"批量更新简历状态时出错: {e}")
        return jsonify(success=False, error="批量更新简历状态时出错"), 500
    
@flask_app.route('/resume/admin/review/add/<submit_id>', methods=['POST'])
async def admin_review_resume(submit_id):
    """
    管理员对指定简历进行审核
    请求体应包含 JSON 字段 "comments"（字符串）, "score"（整数）, "passed"（布尔值）
    此处passed仅表示该管理员观点,不立刻改变简历状态
    仅供管理员参考
    """
    if 'uid' not in session:
        return jsonify(success=False, error="未登录"), 401
    
    uid = session['uid']
    with SQL() as sql:
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        if not permission_info or not (permission_info.get('is_main_leader_admin') or permission_info.get('is_group_leader_admin')):
            return jsonify(success=False, error="权限不足"), 403
    
    data = request.json
    if not data or 'comments' not in data:
        return jsonify(success=False, error="请求格式错误，应包含 'comments'字段"), 400
    
    comments = data['comments']
    score = data['score'] if 'score' in data else None
    passed = data['passed'] if 'passed' in data else None

    if not isinstance(comments, str) or not isinstance(score, (int, type(None))) or not isinstance(passed, (bool, type(None))):
        return jsonify(success=False, error="'comments' 应为字符串, 'score' 应为整数或null, 'passed' 应为布尔值或null"), 400

    try:
        review_id = str(uuid.uuid4())
        while sql.fetch_one('resume_review', {'review_id': review_id}):
            review_id = str(uuid.uuid4())
        review_time = datetime.datetime.now()
        with SQL() as sql:
            insert_data = {
                'review_id': review_id,
                'submit_id': submit_id,
                'reviewer_uid': uid,
                'review_time': review_time,
                'comments': comments
            }
            if score is not None:
                insert_data['score'] = score
            if passed is not None:
                insert_data['passed'] = passed
            sql.insert('resume_review', insert_data)
        return jsonify(success=True, message="简历审核提交成功")
    except Exception as e:
        logger.error(f"提交简历审核时出错: {e}")
        return jsonify(success=False, error="提交简历审核时出错"), 500

@flask_app.route('/resume/admin/review/get_all/<submit_id>', methods=['GET'])
async def get_admin_review(submit_id):
    """
    获取指定简历的审核信息
    """
    if 'uid' not in session:
        return jsonify(success=False, error="未登录"), 401

    uid = session['uid']
    with SQL() as sql:
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        if not permission_info or not (permission_info.get('is_main_leader_admin') or permission_info.get('is_group_leader_admin')):
            return jsonify(success=False, error="权限不足"), 403

    try:
        with SQL() as sql:
            review_info = sql.fetch_one('resume_review', {'submit_id': submit_id})
            if review_info:
                return jsonify(success=True, data=review_info)
            else:
                return jsonify(success=False, error="未找到审核信息"), 404
    except Exception as e:
        logger.error(f"获取简历审核信息时出错: {e}")
        return jsonify(success=False, error="获取简历审核信息时出错"), 500
    
@flask_app.route('/resume/admin/review/delete/<review_id>', methods=['POST'])
async def delete_admin_review(review_id):
    """
    删除指定的简历审核记录
    """
    if 'uid' not in session:
        return jsonify(success=False, error="未登录"), 401

    uid = session['uid']
    with SQL() as sql:
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        if not permission_info or not (permission_info.get('is_main_leader_admin') or permission_info.get('is_group_leader_admin')):
            return jsonify(success=False, error="权限不足"), 403

    try:
        with SQL() as sql:
            sql.delete('resume_review', {'review_id': review_id})
        return jsonify(success=True, message="审核记录删除成功")
    except Exception as e:
        logger.error(f"删除简历审核记录时出错: {e}")
        return jsonify(success=False, error="删除简历审核记录时出错"), 500
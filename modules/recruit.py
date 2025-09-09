import os
import uuid
from flask import request, jsonify, session, send_file
from core.global_params import flask_app
import logging
import datetime

from utils import SQL, is_admin_check

logger = logging.getLogger(__name__)

@flask_app.route('/recruit/list', methods=['GET'])
async def get_recruit_list():
    """
    获取所有招聘信息列表
    """
    with SQL() as sql:
        recruit_list = sql.fetch_all('recruit', columns=['recruit_id', 'name', 'start_time', 'end_time', 'is_active'])
    only_available = request.args.get('only_available', 'false').lower() == 'true'
    
    is_admin = False
    if 'uid' in session:
        uid = session['uid']
        with SQL() as sql:
            permission_info = sql.fetch_one('userpermission', {'uid': uid})
            if is_admin_check(permission_info):
                is_admin = True
    
    if recruit_list is not None:
        cnt_time = datetime.datetime.now()
        recruit_info = []
        for item in recruit_list:
            if only_available and not (item['is_active'] and (item['start_time'] <= cnt_time <= item['end_time'])):
                continue
            if not is_admin and not item['is_active']:
                continue
            is_applyed = False
            if 'uid' in session:
                with SQL() as sql:
                    application = sql.fetch_one('resume_submit', {'uid': session['uid'], 'recruit_id': item['recruit_id']})
                    if application:
                        is_applyed = True
            recruit_info.append({
                'recruit_id': item['recruit_id'],
                'name': item['name'],
                'start_time': item['start_time'].strftime('%Y-%m-%d %H:%M:%S'),
                'end_time': item['end_time'].strftime('%Y-%m-%d %H:%M:%S'),
                'is_active': item['is_active'],
                "available": item['is_active'] and (item['start_time'] <= cnt_time <= item['end_time']),
                "is_applyed": is_applyed
            })
        return jsonify(success=True, data=recruit_info)
    else:
        return jsonify(success=False, error="未找到招聘信息")
    
    
@flask_app.route('/recruit/info/<recruit_id>', methods=['GET'])
async def get_recruit_info(recruit_id):
    """
    获取指定招聘信息的详细内容
    """
    with SQL() as sql:
        recruit = sql.fetch_one('recruit', {'recruit_id': recruit_id})
    
    if not recruit:
        return jsonify(success=False, error="未找到该招聘信息")
    
    is_admin = False
    if 'uid' in session:
        uid = session['uid']
        with SQL() as sql:
            permission_info = sql.fetch_one('userpermission', {'uid': uid})
            if is_admin_check(permission_info):
                is_admin = True
    
    cnt_time = datetime.datetime.now()
    if not is_admin and (not recruit['is_active'] or not (recruit['start_time'] <= cnt_time <= recruit['end_time'])):
        return jsonify(success=False, error="该招聘信息不可见")
    
    is_applyed = False
    if 'uid' in session:
        with SQL() as sql:
            application = sql.fetch_one('resume_submit', {'uid': session['uid'], 'recruit_id': recruit_id})
            if application:
                is_applyed = True
            
    recruit_info = {
        'recruit_id': recruit['recruit_id'],
        'name': recruit['name'],
        'start_time': recruit['start_time'].strftime('%Y-%m-%d %H:%M:%S'),
        'end_time': recruit['end_time'].strftime('%Y-%m-%d %H:%M:%S'),
        'description': recruit['description'],
        'is_active': recruit['is_active'],
        'available': recruit['is_active'] and (recruit['start_time'] <= cnt_time <= recruit['end_time']),
        'is_applyed': is_applyed
    }
    
    return jsonify(success=True, data=recruit_info)
    
@flask_app.route('/recruit/create', methods=['POST'])
async def create_recruit():
    """
    创建新的招聘信息（仅管理员可用）
    """
    if 'uid' not in session:
        return jsonify(success=False, error="用户未登录"), 401
    
    uid = session['uid']
    with SQL() as sql:
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        if not is_admin_check(permission_info):
            return jsonify(success=False, error="权限不足"), 403
    
    data = request.json
    required_fields = ['name', 'start_time', 'end_time', 'description', 'is_active']
    if not all(field in data for field in required_fields):
        return jsonify(success=False, error="缺少必要的字段")
    
    try:
        with SQL() as sql:
            recruit_id = str(uuid.uuid4())
            while sql.fetch_one('recruit', {'recruit_id': recruit_id}):
                recruit_id = str(uuid.uuid4())
            sql.insert('recruit', {
                'recruit_id': recruit_id,
                'name': data['name'],
                'start_time': data['start_time'],
                'end_time': data['end_time'],
                'description': data['description'],
                'is_active': data['is_active']
            })
        return jsonify(success=True, message="招聘信息创建成功", recruit_id=recruit_id)
    except Exception as e:
        logger.error(f"创建招聘信息时出错: {e}")
        return jsonify(success=False, error="创建招聘信息失败")
    
@flask_app.route('/recruit/<recruit_id>/update', methods=['POST'])
async def update_recruit(recruit_id):
    """
    更新指定招聘信息（仅管理员可用）
    """
    if 'uid' not in session:
        return jsonify(success=False, error="用户未登录"), 401
    
    uid = session['uid']
    with SQL() as sql:
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        if not is_admin_check(permission_info):
            return jsonify(success=False, error="权限不足"), 403
    
    data = request.json
    allowed_fields = ['name', 'start_time', 'end_time', 'description', 'is_active']
    
    try:
        update_data = {key: data[key] for key in allowed_fields if key in data}
        if not update_data:
            return jsonify(success=False, error="没有提供更新数据")
        
        with SQL() as sql:
            sql.update('recruit', update_data, {'recruit_id': recruit_id})
        return jsonify(success=True, message="招聘信息更新成功")
    except Exception as e:
        logger.error(f"更新招聘信息时出错: {e}")
        return jsonify(success=False, error="更新招聘信息失败")
    
@flask_app.route('/recruit/<recruit_id>/delete', methods=['POST'])
async def delete_recruit(recruit_id):
    """
    删除指定招聘信息（仅管理员可用）
    """
    if 'uid' not in session:
        return jsonify(success=False, error="用户未登录"), 401
    
    uid = session['uid']
    with SQL() as sql:
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        if not is_admin_check(permission_info):
            return jsonify(success=False, error="权限不足"), 403
    
    try:
        with SQL() as sql:
            sql.delete('recruit', {'recruit_id': recruit_id})
        return jsonify(success=True, message="招聘信息删除成功")
    except Exception as e:
        logger.error(f"删除招聘信息时出错: {e}")
        return jsonify(success=False, error="删除招聘信息失败")
    
import os
import uuid
from flask import request, jsonify, session, send_file
from core.global_params import flask_app
import logging
import datetime

from utils import SQL, is_admin_check

logger = logging.getLogger(__name__)

@flask_app.route('/admin/user/list', methods=['GET'])
async def get_all_users():
    """
    获取所有用户的信息，管理员专用接口
    """
    if 'uid' not in session:
        return jsonify(success=False, error="未登录"), 401
    
    uid = session['uid']
    with SQL() as sql:
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        if not is_admin_check(permission_info):
            return jsonify(success=False, error="权限不足"), 403
        
        user_list = sql.fetch_all('userinfo')
    
    if user_list is not None:
        user_info = []
        for item in user_list:
            with SQL() as sql:
                user_submission = sql.fetch_one('user', {'uid': item['uid']})
            cnt_user_info = {
                'uid': item['uid'],
                'nickname': item['nickname'],
                'realname': item['realname'],
                'email': user_submission['mail'],
            }
            if item['registration_time']:
                cnt_user_info['registration_time'] = item['registration_time'].strftime('%Y-%m-%d %H:%M:%S')
            user_info.append(cnt_user_info)
        return jsonify(success=True, data=user_info)
    else:
        return jsonify(success=False, error="未找到用户信息")
        
@flask_app.route('/admin/user/info/get/<target_uid>', methods=['GET'])
async def get_target_user_info(target_uid):
    """
    获取目标用户的信息
    """
    uid = session.get('uid')
    if not uid:
        return jsonify(success=False, error="用户未登录"), 401
    with SQL() as sql:
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        if not is_admin_check(permission_info):
            return jsonify(success=False, error="权限不足"), 403
            
    uid = target_uid
        
    with SQL() as sql:
        user_info = sql.fetch_one('userinfo', {'uid': uid})
        if not user_info:
            return jsonify(success=False, error="未找到用户信息"), 404

        user_phone = sql.fetch_one('userphone', {'uid': uid})
        user_info['phone_number'] = user_phone.get('phone_number', '') if user_phone else ''
        user_info['is_verified'] = user_phone.get('is_verified', False) if user_phone else False
        
        user_id = sql.fetch_one('user', {'uid': uid})
        if user_id and user_id.get('mail', None):
            user_info['mail'] = user_id.get('mail', None)
        
        permission = False
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        if permission_info and is_admin_check(permission_info):
            permission = True
        user_info['permission'] = permission
    
    return jsonify(success=True, data=user_info)
    
@flask_app.route('/admin/user/batch/delete', methods=['POST'])
async def batch_delete_users():
    """
    批量删除用户，管理员专用接口
    请求体应包含 JSON 数组 "uids"，表示要删除的用户ID列表
    """
    if 'uid' not in session:
        return jsonify(success=False, error="未登录"), 401
    
    uid = session['uid']
    with SQL() as sql:
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        if not is_admin_check(permission_info):
            return jsonify(success=False, error="权限不足"), 403
    
    data = request.json
    if not data or 'uids' not in data or not isinstance(data['uids'], list):
        return jsonify(success=False, error="请求格式错误，应包含 'uids' 列表"), 400
    
    uids_to_delete = data['uids']
    with SQL() as sql:
        for target_uid in uids_to_delete:
            user = sql.fetch_one('user', {'uid': target_uid})
            if user:
                sql.delete('user', {'uid': target_uid})
                sql.delete('userinfo', {'uid': target_uid})
                sql.delete('useravatar', {'uid': target_uid})
                sql.delete('userpermission', {'uid': target_uid})
                sql.delete('userphone', {'uid': target_uid})
                # 这里可以继续删除与用户相关的其他数据，如简历、申请等
    
    return jsonify(success=True, message="用户已批量删除")

@flask_app.route('/admin/user/permissions/update', methods=['POST'])
async def update_user_permissions():
    """
    更新指定用户的权限，管理员专用接口
    请求体应包含 JSON 字段 "uid" 和权限字段，如 "is_main_leader_admin", "is_group_leader_admin", "is_member_admin"
    """
    if 'uid' not in session:
        return jsonify(success=False, error="未登录"), 401
    
    uid = session['uid']
    with SQL() as sql:
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        if not is_admin_check(permission_info):
            return jsonify(success=False, error="权限不足"), 403
    
    data = request.json
    if not data or 'uid' not in data:
        return jsonify(success=False, error="请求格式错误，应包含 'uid' 字段"), 400
    
    target_uid = data['uid']
    valid_permissions = ['is_main_leader_admin', 'is_group_leader_admin', 'is_member_admin']
    update_fields = {key: data[key] for key in valid_permissions if key in data and isinstance(data[key], bool)}
    
    if not update_fields:
        return jsonify(success=False, error="没有有效的权限字段提供"), 400
    
    with SQL() as sql:
        user = sql.fetch_one('user', {'uid': target_uid})
        if not user:
            return jsonify(success=False, error="用户不存在"), 404
        
        existing_permissions = sql.fetch_one('userpermission', {'uid': target_uid})
        if existing_permissions:
            sql.update('userpermission', update_fields, {'uid': target_uid})
        else:
            update_fields['uid'] = target_uid
            sql.insert('userpermission', update_fields)
    
    return jsonify(success=True, message="用户权限已更新")

@flask_app.route('/admin/user/permissions/get/<target_uid>', methods=['GET'])
async def get_user_permissions(target_uid):
    """
    获取指定用户的权限信息，管理员专用接口
    """
    if 'uid' not in session:
        return jsonify(success=False, error="未登录"), 401
    
    uid = session['uid']
    with SQL() as sql:
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        if not is_admin_check(permission_info):
            return jsonify(success=False, error="权限不足"), 403
        
        target_permissions = sql.fetch_one('userpermission', {'uid': target_uid})
    
    if target_permissions:
        return jsonify(success=True, data=target_permissions)
    else:
        return jsonify(success=False, error="未找到用户权限信息"), 404
    
@flask_app.route('/admin/user/search', methods=['GET'])
async def search_users():
    """
    搜索用户，管理员专用接口
    支持通过邮箱或用户名进行模糊搜索，使用查询参数 'query'
    """
    if 'uid' not in session:
        return jsonify(success=False, error="未登录"), 401
    
    uid = session['uid']
    with SQL() as sql:
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        if not is_admin_check(permission_info):
            return jsonify(success=False, error="权限不足"), 403
    
    query = request.args.get('query', '').strip()
    if not query:
        return jsonify(success=False, error="未提供搜索查询"), 400
    
    like_query = f"%{query}%"
    with SQL() as sql:
        query = """
            SELECT `uid`, `realname`, `nickname`, `registration_time` 
            FROM `userinfo` 
            WHERE `realname` LIKE %s OR `nickname` LIKE %s
        """
        params = (like_query, like_query)
        user_list = sql.execute_query(query, params)
    
    if user_list is not None:
        user_info = []
        for item in user_list:
            user_info.append({
                'uid': item['uid'],
                'name': item['name'],
                'email': item['email'],
                'registration_time': item['registration_time'].strftime('%Y-%m-%d %H:%M:%S'),
            })
        return jsonify(success=True, data=user_info)
    else:
        return jsonify(success=False, error="未找到匹配的用户信息")
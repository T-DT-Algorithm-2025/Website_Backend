import os
from flask import request, jsonify, session, send_file
from core.global_params import flask_app
import logging

from utils.login import *
from utils import SQL

logger = logging.getLogger(__name__)

@flask_app.route('/user/info/get', methods=['GET'])
async def get_user_info():
    """
    获取当前登录用户的信息
    """
    uid = session['uid'] if 'uid' in session else None
    if not uid:
        return jsonify(success=False, error="用户未登录")
    with SQL() as sql:
        user_info = sql.fetch_one('userinfo', {'uid': uid})
        permission = False
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        if permission_info:
            if permission_info.get('is_main_leader_admin') or permission_info.get('is_group_leader_admin') or permission_info.get('is_member_admin'):
                permission = True
    
    if user_info:
        user_info['permission'] = permission
        return jsonify(success=True, data=user_info, permission=permission)
    else:
        return jsonify(success=False, error="未找到用户信息")

@flask_app.route('/user/avatar/get', methods=['GET'])
async def get_user_avatar():
    """
    获取当前登录用户的头像
    """
    uid = session['uid'] if 'uid' in session else None
    if not uid:
        # 如果用户未登录，可以返回一个默认头像
        try:
            return send_file('avatars/default.jpg', mimetype='image/jpeg')
        except FileNotFoundError:
            return jsonify(success=False, error="默认头像未找到"), 404

    with SQL() as sql:
        avatar_info = sql.fetch_one('useravatar', {'uid': uid})
    if avatar_info and avatar_info['avatar_path']:
        avatar_path = avatar_info['avatar_path']
        try:
            return send_file(os.path.join(os.getcwd(), avatar_path), mimetype='image/jpeg')
        except FileNotFoundError:
            return jsonify(success=False, error="头像文件未找到"), 404
    else:
        # 如果没有头像记录或路径为空，也返回默认头像
        try:
            return send_file(os.path.join(os.getcwd(), 'avatars/default.jpg'), mimetype='image/jpeg')
        except FileNotFoundError:
            return jsonify(success=False, error="默认头像未找到"), 404


@flask_app.route('/user/info/update', methods=['POST'])
async def update_user_info():
    """
    更新当前登录用户的信息
    """
    uid = session['uid'] if 'uid' in session else None
    if not uid:
        return jsonify(success=False, error="用户未登录")

    update_data = request.json
    if not update_data:
        return jsonify(success=False, error="未提供更新数据")

    allowed_fields = ["nickname", "gender", "realname", "student_id", "department", "major", "grade", "rank"]
    
    try:
        for key, value in update_data.items():
            if key in allowed_fields:
                # 注意：这里的参数需要正确地被引用和格式化
                with SQL() as sql:
                    sql.update('userinfo', {key: value}, {'uid': uid})
        return jsonify(success=True, message="用户信息更新成功")
    except Exception as e:
        logger.error(f"更新用户信息时出错: {e}")
        return jsonify(success=False, error="更新失败"), 500

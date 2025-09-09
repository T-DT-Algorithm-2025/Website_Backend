import os
from flask import request, jsonify, session, send_file
from core.global_params import flask_app
import logging

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
        user_phone = sql.fetch_one('userphone', {'uid': uid})
        if user_phone:
            user_info['phone_number'] = user_phone.get('phone_number', '')
            user_info['is_verified'] = user_phone.get('is_verified', False)
        else:
            user_info['phone_number'] = ''
            user_info['is_verified'] = False
        
        permission = False
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        if permission_info:
            if permission_info.get('is_main_leader_admin') or permission_info.get('is_group_leader_admin') or permission_info.get('is_member_admin'):
                permission = True
        user_info['permission'] = permission
    
    if user_info:
        return jsonify(success=True, data=user_info)
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

    allowed_fields = ["nickname", "gender", "realname", "student_id", "department", "major", "grade", "rank", "phone_number"]
    
    try:
        for key, value in update_data.items():
            if key in allowed_fields:
                # 注意：这里的参数需要正确地被引用和格式化
                if key == "phone_number":
                    with SQL() as sql:
                        phone_record = sql.fetch_one('userphone', {'uid': uid})
                        if phone_record:
                            sql.update('userphone', {'phone_number': value, 'is_verified': False}, {'uid': uid})
                        else:
                            sql.insert_one('userphone', (uid, value, False, '', None))
                else:
                    with SQL() as sql:
                        sql.update('userinfo', {key: value}, {'uid': uid})
        return jsonify(success=True, message="用户信息更新成功")
    except Exception as e:
        logger.error(f"更新用户信息时出错: {e}")
        return jsonify(success=False, error="更新失败"), 500

@flask_app.route('/user/avatar/update', methods=['POST'])
async def update_user_avatar():
    """
    更新当前登录用户的头像
    """
    uid = session['uid'] if 'uid' in session else None
    if not uid:
        return jsonify(success=False, error="用户未登录")

    if 'avatar' not in request.files:
        return jsonify(success=False, error="未提供头像文件")

    avatar_file = request.files['avatar']
    if avatar_file.filename == '':
        return jsonify(success=False, error="未选择头像文件")

    # 简单的文件类型检查，可以根据需要扩展
    if not avatar_file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
        return jsonify(success=False, error="不支持的文件类型")

    avatar_dir = os.path.join(os.getcwd(), 'avatars')
    os.makedirs(avatar_dir, exist_ok=True)
    avatar_path = os.path.join(avatar_dir, f"{uid}_{avatar_file.filename}")
    avatar_file.save(avatar_path)

    relative_avatar_path = os.path.relpath(avatar_path, os.getcwd())

    try:
        with SQL() as sql:
            avatar_record = sql.fetch_one('useravatar', {'uid': uid})
            if avatar_record:
                sql.update('useravatar', {'avatar_path': relative_avatar_path}, {'uid': uid})
            else:
                sql.insert('useravatar', {'uid': uid, 'avatar_path': relative_avatar_path})
        return jsonify(success=True, message="头像更新成功")
    except Exception as e:
        logger.error(f"更新用户头像时出错: {e}")
        return jsonify(success=False, error="头像更新失败"), 500
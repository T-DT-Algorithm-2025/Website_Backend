import os
from flask import request, jsonify, session, send_file
from core.global_params import flask_app
import logging

from utils import SQL, is_admin_check

logger = logging.getLogger(__name__)

@flask_app.route('/user/info/get', methods=['GET'])
async def get_user_info():
    """
    获取当前登录用户的信息
    """
    uid = session.get('uid')
    if not uid:
        return jsonify(success=False, error="用户未登录"), 401
        
    with SQL() as sql:
        user_info = sql.fetch_one('userinfo', {'uid': uid})
        if not user_info:
            return jsonify(success=False, error="未找到用户信息"), 404

        user_phone = sql.fetch_one('userphone', {'uid': uid})
        user_info['phone_number'] = user_phone.get('phone_number', '') if user_phone else ''
        user_info['is_verified'] = user_phone.get('is_verified', False) if user_phone else False
        
        permission = False
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        if permission_info and is_admin_check(permission_info):
            permission = True
        user_info['permission'] = permission
    
    return jsonify(success=True, data=user_info)

@flask_app.route('/user/avatar/get', methods=['GET'])
async def get_user_avatar():
    """
    获取当前登录用户的头像
    """
    uid = session.get('uid')
    if not uid:
        return jsonify(success=False, error="用户未登录"), 401

    with SQL() as sql:
        avatar_info = sql.fetch_one('useravatar', {'uid': uid})

    if avatar_info and avatar_info.get('avatar_path') and os.path.exists(avatar_info['avatar_path']):
        return send_file(os.path.join(os.getcwd(), avatar_info['avatar_path']), mimetype='image/jpeg')
    else:
        # 如果没有头像记录或路径为空/文件不存在，也返回默认头像
        try:
            return send_file(os.path.join(os.getcwd(), 'avatars/default.jpg'), mimetype='image/jpeg')
        except FileNotFoundError:
            return jsonify(success=False, error="默认头像未找到"), 404


@flask_app.route('/user/info/update', methods=['POST'])
async def update_user_info():
    """
    更新当前登录用户的信息
    """
    uid = session.get('uid')
    if not uid:
        return jsonify(success=False, error="用户未登录"), 401

    update_data = request.json
    if not update_data:
        return jsonify(success=False, error="未提供更新数据"), 400

    allowed_fields = ["nickname", "gender", "realname", "student_id", "department", "major", "grade", "rank"]
    
    try:
        user_info_update = {key: value for key, value in update_data.items() if key in allowed_fields}
        
        with SQL() as sql:
            if user_info_update:
                sql.update('userinfo', user_info_update, {'uid': uid})

            if "phone_number" in update_data:
                phone_number = update_data["phone_number"]
                phone_record = sql.fetch_one('userphone', {'uid': uid})
                if phone_record:
                    sql.update('userphone', {'phone_number': phone_number, 'is_verified': False}, {'uid': uid})
                else:
                    # Bug修复: sql.insert 方法需要一个字典作为参数，而不是元组
                    sql.insert('userphone', {
                        'uid': uid, 
                        'phone_number': phone_number, 
                        'is_verified': False,
                        'verification_code': '',
                        'code_sent_time': None
                    })

        return jsonify(success=True, message="用户信息更新成功")
    except Exception as e:
        logger.error(f"更新用户信息时出错: {e}")
        return jsonify(success=False, error="更新失败"), 500

@flask_app.route('/user/avatar/update', methods=['POST'])
async def update_user_avatar():
    """
    更新当前登录用户的头像
    """
    uid = session.get('uid')
    if not uid:
        return jsonify(success=False, error="用户未登录"), 401

    if 'avatar' not in request.files:
        return jsonify(success=False, error="未提供头像文件"), 400

    avatar_file = request.files['avatar']
    if avatar_file.filename == '':
        return jsonify(success=False, error="未选择头像文件"), 400

    # 简单的文件类型检查，可以根据需要扩展
    if not avatar_file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
        return jsonify(success=False, error="不支持的文件类型"), 400

    avatar_dir = 'avatars'
    os.makedirs(avatar_dir, exist_ok=True)
    
    # 使用一个更安全的文件名
    file_extension = os.path.splitext(avatar_file.filename)[1]
    avatar_path = os.path.join(avatar_dir, f'{uid}{file_extension}')
    
    avatar_file.save(avatar_path)

    try:
        with SQL() as sql:
            avatar_record = sql.fetch_one('useravatar', {'uid': uid})
            if avatar_record:
                sql.update('useravatar', {'avatar_path': avatar_path}, {'uid': uid})
            else:
                sql.insert('useravatar', {'uid': uid, 'avatar_path': avatar_path})
        return jsonify(success=True, message="头像更新成功", path=avatar_path)
    except Exception as e:
        logger.error(f"更新用户头像时出错: {e}")
        return jsonify(success=False, error="头像更新失败"), 500

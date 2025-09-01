from flask import request, jsonify, session, send_file
from core.global_params import flask_app, sql

@flask_app.route('/user/info/get', methods=['GET'])
async def get_user_info():
    """
    获取当前登录用户的信息
    """
    uid = session.get('uid')
    if not uid:
        return jsonify(success=False, error="用户未登录")

    user_info = await sql.select_one('userinfo', 'uid', f"'{uid}'")
    if user_info:
        return jsonify(success=True, data=user_info[0])
    else:
        return jsonify(success=False, error="未找到用户信息")

@flask_app.route('/user/avatar/get', methods=['GET'])
async def get_user_avatar():
    """
    获取当前登录用户的头像
    """
    uid = session.get('uid')
    if not uid:
        # 如果用户未登录，可以返回一个默认头像
        try:
            return send_file('avatars/default.jpg', mimetype='image/jpeg')
        except FileNotFoundError:
            return jsonify(success=False, error="默认头像未找到"), 404


    avatar_info = await sql.select_one('useravatar', 'uid', f"'{uid}'")
    if avatar_info and avatar_info[0]['avatar_path']:
        avatar_path = avatar_info[0]['avatar_path']
        try:
            return send_file(avatar_path, mimetype='image/jpeg')
        except FileNotFoundError:
            return jsonify(success=False, error="头像文件未找到"), 404
    else:
        # 如果没有头像记录或路径为空，也返回默认头像
        try:
            return send_file('avatars/default.jpg', mimetype='image/jpeg')
        except FileNotFoundError:
            return jsonify(success=False, error="默认头像未找到"), 404


@flask_app.route('/user/info/update', methods=['POST'])
async def update_user_info():
    """
    更新当前登录用户的信息
    """
    uid = session.get('uid')
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
                await sql.update_one('userinfo', 'uid', f"'{uid}'", key, f"'{value}'")
        return jsonify(success=True, message="用户信息更新成功")
    except Exception as e:
        print(f"更新用户信息时出错: {e}")
        return jsonify(success=False, error="更新失败"), 500

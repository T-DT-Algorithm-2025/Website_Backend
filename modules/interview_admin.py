import os
import uuid
from flask import request, jsonify, session, send_file
from core.global_params import flask_app
import logging
import datetime

from utils import SQL, is_admin_check

logger = logging.getLogger(__name__)

# 改进: 将权限检查提取为装饰器会更好，但这里暂时保留为辅助函数以减少代码改动
def is_admin():
    """检查当前用户是否为管理员"""
    uid = session.get('uid')
    if not uid:
        return False
    with SQL() as sql:
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        return is_admin_check(permission_info)

@flask_app.route('/admin/interview/room/add', methods=['POST'])
async def add_interview_room():
    if not is_admin():
        return jsonify(success=False, error="权限不足"), 403
    
    data = request.json
    recruit_id = data.get('recruit_id')
    room_name = data.get('room_name')
    location = data.get('location')
    applicable_to_choice = data.get('applicable_to_choice')

    if not all([recruit_id, room_name, location, applicable_to_choice]):
        return jsonify(success=False, error="缺少必要字段(recruit_id, room_name, location, applicable_to_choice)"), 400

    try:
        with SQL() as sql:
            if not sql.fetch_one('recruit', {'recruit_id': recruit_id}):
                return jsonify(success=False, error="无效的招聘ID"), 404
            
            room_id = str(uuid.uuid4())
            sql.insert('interview_room', {
                'room_id': room_id,
                'recruit_id': recruit_id,
                'room_name': room_name,
                'location': location,
                'applicable_to_choice': applicable_to_choice
            })
        return jsonify(success=True, message="面试地点添加成功", room_id=room_id)
    except Exception as e:
        logger.error(f"添加面试地点时出错: {e}")
        return jsonify(success=False, error="服务器内部错误"), 500

@flask_app.route('/admin/interview/list/<recruit_id>', methods=['GET'])
async def list_interviews(recruit_id):
    """
    (管理员) 获取指定招聘的所有已安排面试列表
    """
    if not is_admin():
        return jsonify(success=False, error="权限不足"), 403

    try:
        with SQL() as sql:
            # Bug修复: interview_info 表没有 recruit_id。需要通过 resume_submit 表进行关联查询。
            query = """
                SELECT
                    ii.interview_id,
                    ii.submit_id,
                    ii.interviewee_uid,
                    ui.realname,
                    ui.nickname,
                    ii.interview_time,
                    ii.location,
                    ii.notes
                FROM
                    interview_info AS ii
                JOIN
                    resume_submit AS rs ON ii.submit_id = rs.submit_id
                JOIN
                    userinfo AS ui ON ii.interviewee_uid = ui.uid
                WHERE
                    rs.recruit_id = %s
            """
            interviews = sql.execute_query(query, (recruit_id,))

            interview_list = [
                {
                    'interview_id': interview['interview_id'],
                    'submit_id': interview['submit_id'],
                    'interviewee_uid': interview['interviewee_uid'],
                    'interviewee_name': interview.get('realname') or interview.get('nickname', '未知'),
                    'interview_time': interview['interview_time'].strftime('%Y-%m-%d %H:%M:%S'),
                    'location': interview.get('location', 'N/A'),
                    'notes': interview.get('notes', '')
                } for interview in interviews
            ]
            return jsonify(success=True, data=interview_list)
    except Exception as e:
        logger.error(f"获取面试列表时出错: {e}")
        return jsonify(success=False, error="服务器内部错误"), 500

# ... (其他 admin 接口)
# 以下为其他未修改但保持完整的函数
@flask_app.route('/admin/interview/room/list/<recruit_id>', methods=['GET'])
async def list_interview_rooms(recruit_id):
    if not is_admin():
        return jsonify(success=False, error="权限不足"), 403
    try:
        with SQL() as sql:
            rooms = sql.fetch_all('interview_room', {'recruit_id': recruit_id})
            return jsonify(success=True, data=rooms)
    except Exception as e:
        logger.error(f"获取面试地点列表时出错: {e}")
        return jsonify(success=False, error="服务器内部错误"), 500

import asyncio
import os
import uuid
from flask import request, jsonify, session, send_file
from core.global_params import flask_app
import logging
import datetime

from utils import SQL
from utils.notification import send_interview_booking_email

logger = logging.getLogger(__name__)

# 定义简历状态ID常量
RESUME_PASSED_STATUS = 1    # "简历通过"
AWAITING_INTERVIEW_STATUS = 3 # "等待预约面试"

@flask_app.route('/interview/available/<recruit_id>', methods=['GET'])
async def get_available_interview_rooms(recruit_id):
    """
    获取指定招聘（recruit_id）是否可预约面试地点
    """
    uid = session.get('uid')
    if not uid:
        return jsonify(success=False, error="用户未登录"), 401

    try:
        with SQL() as sql:
            recruit_info = sql.fetch_one('recruit', {'recruit_id': recruit_id})
            if not recruit_info or not recruit_info.get('is_active', False):
                return jsonify(success=True, data={"available": False})

            # 检查用户是否有通过的简历
            submission = sql.fetch_one(
                'resume_submit',
                {'uid': uid, 'recruit_id': recruit_id, 'status': RESUME_PASSED_STATUS}
            )
            if not submission:
                return jsonify(success=True, data={"available": False})

            recruit_interview_settings = sql.fetch_one('recruit_interview_settings', {'recruit_id': recruit_id})
            if not recruit_interview_settings:
                return jsonify(success=True, data={"available": False})
            cnt_time = datetime.datetime.now()
            if not (recruit_interview_settings['interview_start_time'] <= cnt_time <= recruit_interview_settings['interview_end_time']):
                return jsonify(success=True, data={"available": False, "start_time": recruit_interview_settings['interview_start_time'].strftime('%Y-%m-%d %H:%M:%S'), "end_time": recruit_interview_settings['interview_end_time'].strftime('%Y-%m-%d %H:%M:%S')})

            return jsonify(success=True, data={"available": True, "start_time": recruit_interview_settings['interview_start_time'].strftime('%Y-%m-%d %H:%M:%S'), "end_time": recruit_interview_settings['interview_end_time'].strftime('%Y-%m-%d %H:%M:%S')})
    except Exception as e:
        logger.error(f"获取面试地点可预约状态时出错: {e}")
        return jsonify(success=False, error="服务器内部错误"), 500

@flask_app.route('/interview/schedule/available/<submit_id>', methods=['GET'])
async def get_available_schedules(submit_id):
    """
    获取指定投递（submit_id）所有可用的面试时间段
    """
    uid = session.get('uid')
    if not uid:
        return jsonify(success=False, error="用户未登录"), 401

    try:
        with SQL() as sql:
            # 验证用户是否有权为该投递预约面试
            submission = sql.fetch_one(
                'resume_submit',
                {'submit_id': submit_id, 'uid': uid, 'status': RESUME_PASSED_STATUS}
            )
            if not submission:
                return jsonify(success=False, error="该投递不符合面试预约条件(可能原因:非本人操作,或简历状态不为'简历通过')"), 403

            # 获取该投递的志愿
            resume_info = sql.fetch_one('resume_info', {'submit_id': submit_id})
            if not resume_info or not resume_info.get('first_choice'):
                return jsonify(success=False, error="找不到该投递的志愿信息"), 404
            
            target_choice = resume_info['first_choice']
            recruit_id = submission['recruit_id']

            rooms = sql.fetch_all(
                'interview_room', 
                {'recruit_id': recruit_id, 'applicable_to_choice': target_choice}
            )
            if not rooms:
                return jsonify(success=True, data=[])

            room_ids = [room['room_id'] for room in rooms]
            if not room_ids:
                 return jsonify(success=True, data=[])
            
            placeholders = ','.join(['%s'] * len(room_ids))
            schedule_query = f"SELECT * FROM `interview_schedule` WHERE `room_id` IN ({placeholders}) AND `already_booked` = FALSE"
            schedules = sql.execute_query(schedule_query, room_ids)

            # 获取所有相关房间信息以减少循环内查询
            room_info_query = f"SELECT `room_id`, `room_name`, `location` FROM `interview_room` WHERE `room_id` IN ({placeholders})"
            room_infos_raw = sql.execute_query(room_info_query, room_ids)
            room_infos = {room['room_id']: room for room in room_infos_raw}

            available_slots = []
            for s in schedules:
                room_details = room_infos.get(s['room_id'])
                if room_details:
                    available_slots.append({
                        "schedule_id": s['schedule_id'],
                        "start_time": s['start_time'].strftime('%Y-%m-%d %H:%M:%S'),
                        "end_time": s['end_time'].strftime('%Y-%m-%d %H:%M:%S'),
                        "room_name": room_details.get('room_name', 'N/A'),
                        "location": room_details.get('location', 'N/A')
                    })
            return jsonify(success=True, data=available_slots)
    except Exception as e:
        logger.error(f"获取可用面试安排时出错: {e}")
        return jsonify(success=False, error="服务器内部错误"), 500

@flask_app.route('/interview/schedule/book', methods=['POST'])
async def book_interview_schedule():
    """
    用户为指定的投递（submit_id）预约一个面试时间段
    """
    uid = session.get('uid')
    if not uid:
        return jsonify(success=False, error="用户未登录"), 401
    
    data = request.json
    schedule_id = data.get('schedule_id')
    submit_id = data.get('submit_id')

    if not schedule_id or not submit_id:
        return jsonify(success=False, error="缺少 schedule_id 或 submit_id"), 400

    try:
        with SQL() as sql:
            # 事务性检查：确保该用户拥有该投递，且状态正确
            submission = sql.fetch_one('resume_submit', {'submit_id': submit_id, 'uid': uid})
            if not submission or submission['status'] != RESUME_PASSED_STATUS:
                return jsonify(success=False, error="该投递不符合面试预约条件"), 403

            # 事务性更新：确保时间段未被预约，这是一个原子操作
            affected_rows = sql.update(
                'interview_schedule',
                {'already_booked': True},
                {'schedule_id': schedule_id, 'already_booked': False}
            )
            if affected_rows == 0:
                return jsonify(success=False, error="该时间段已被预约，请选择其他时间"), 409

            # 如果更新成功，继续创建面试信息
            schedule = sql.fetch_one('interview_schedule', {'schedule_id': schedule_id})
            room_info = sql.fetch_one('interview_room', {'room_id': schedule['room_id']})

            interview_id = str(uuid.uuid4())
            sql.insert('interview_info', {
                'interview_id': interview_id,
                'submit_id': submit_id,
                'interviewee_uid': uid,
                'interview_time': schedule['start_time'],
                'location': room_info.get('location', 'N/A'),
                'notes': f"由 {uid} 于 {datetime.datetime.now()} 预约"
            })
            
            # 将新创建的 interview_id 关联回 schedule
            sql.update('interview_schedule', {'booked_interview_id': interview_id}, {'schedule_id': schedule_id})
            
            # 更新简历状态为“等待面试”
            sql.update('resume_submit', {'status': AWAITING_INTERVIEW_STATUS}, {'submit_id': submit_id})

        # 发送面试预约成功邮件
        recruit_info = sql.fetch_one('recruit', {'recruit_id': submission['recruit_id']})
        recruit_name = recruit_info.get('name', 'N/A') if recruit_info else 'N/A'
        resume_info = sql.fetch_one('resume_info', {'submit_id': submit_id})
        choice = resume_info.get('first_choice', 'N/A') if resume_info else 'N/A'
        interview_time_str = schedule['start_time'].strftime('%Y-%m-%d %H:%M:%S')
        location = room_info.get('location', 'N/A')
        asyncio.create_task(send_interview_booking_email(uid, recruit_name, choice, interview_time_str, location))
        
        return jsonify(success=True, message="面试预约成功", interview_id=interview_id)

    except Exception as e:
        logger.error(f"预约面试时出错: {e}")
        # 发生任何错误时，尝试回滚预约状态
        try:
            with SQL() as sql:
                sql.update('interview_schedule', {'already_booked': False, 'booked_interview_id': None}, {'schedule_id': schedule_id})
        except Exception as rollback_e:
            logger.error(f"回滚面试预约状态失败: {rollback_e}")
        
        return jsonify(success=False, error="服务器内部错误，预约失败"), 500

@flask_app.route('/interview/my_bookings/<recruit_id>', methods=['GET'])
async def get_my_bookings(recruit_id):
    """
    获取用户在某个招聘下的所有已预约面试信息
    """
    uid = session.get('uid')
    if not uid:
        return jsonify(success=False, error="用户未登录"), 401
    
    try:
        with SQL() as sql:
            query = """
                SELECT
                    ii.interview_id,
                    ii.submit_id,
                    ii.interview_time,
                    ii.location,
                    ri.first_choice as choice
                FROM
                    interview_info AS ii
                JOIN
                    resume_submit AS rs ON ii.submit_id = rs.submit_id
                JOIN
                    resume_info AS ri ON ii.submit_id = ri.submit_id
                WHERE
                    ii.interviewee_uid = %s AND rs.recruit_id = %s
            """
            if '%' in recruit_id or ';' in recruit_id or '\"' in recruit_id or '\'' in recruit_id:
                # 防止SQL注入攻击
                return jsonify(success=False, error="无效的招聘ID"), 400
            interviews = sql.execute_query(query, (uid, recruit_id))

            response_data = [
                {
                    'interview_id': info['interview_id'],
                    'submit_id': info['submit_id'],
                    'interview_time': info['interview_time'].strftime('%Y-%m-%d %H:%M:%S'),
                    'location': info['location'],
                    'choice': info['choice']
                } for info in interviews
            ]
            return jsonify(success=True, data=response_data)
    except Exception as e:
        logger.error(f"获取我的面试安排时出错: {e}")
        return jsonify(success=False, error="服务器内部错误"), 500


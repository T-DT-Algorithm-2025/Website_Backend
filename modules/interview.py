import asyncio
import os
import uuid
from flask import request, jsonify, session, send_file
from core.global_params import flask_app
import logging
import datetime

from utils import SQL, is_admin_check
from utils.notification import send_interview_booking_email

logger = logging.getLogger(__name__)

# 定义简历状态ID常量
RESUME_PASSED_STATUS = 1    # "简历通过"
AWAITING_INTERVIEW_STATUS = 3 # "等待面试"

@flask_app.route('/interview/available/<recruit_id>', methods=['GET'])
async def get_available_interview_rooms(recruit_id):
    """
    获取指定招聘（recruit_id）对当前用户是否开放面试预约。
    这不仅仅是检查房间，而是检查整个预约流程的前置条件。
    """
    uid = session.get('uid')
    if not uid:
        return jsonify(success=False, error="用户未登录"), 401
    
    is_admin = False
    with SQL() as sql:
        permission_info = sql.fetch_one('userpermission', {'uid': uid})
        if is_admin_check(permission_info):
            is_admin = True

    try:
        with SQL() as sql:
            # 1. 检查招聘本身是否存在且处于活动状态
            recruit_info = sql.fetch_one('recruit', {'recruit_id': recruit_id})
            if not recruit_info or not recruit_info.get('is_active', False):
                return jsonify(success=True, data={"available": False, "reason": "招聘未激活"})

            # 2. 检查用户在该招聘下是否有状态为“简历通过”的投递
            submission = sql.fetch_one(
                'resume_submit',
                {'uid': uid, 'recruit_id': recruit_id, 'status': RESUME_PASSED_STATUS}
            )
            if not submission and not is_admin:
                return jsonify(success=True, data={"available": False, "reason": "未找到符合条件的投递"})

            # 3. 检查管理员是否设置了该招聘的面试预约时间
            recruit_interview_settings = sql.fetch_one('recruit_interview_settings', {'recruit_id': recruit_id})
            if not recruit_interview_settings:
                return jsonify(success=True, data={"available": False, "reason": "预约未开放"})
            
            # 4. 检查当前时间是否在管理员设置的预约时间窗口内
            cnt_time = datetime.datetime.now()
            start_time = recruit_interview_settings['book_start_time']
            end_time = recruit_interview_settings['book_end_time']
            if not (start_time <= cnt_time <= end_time):
                return jsonify(success=True, data={"available": False, "reason": "不在预约时间段内", "start_time": start_time.strftime('%Y-%m-%d %H:%M:%S'), "end_time": end_time.strftime('%Y-%m-%d %H:%M:%S')})

            # 所有条件满足，开放预约
            return jsonify(success=True, data={"available": True, "start_time": start_time.strftime('%Y-%m-%d %H:%M:%S'), "end_time": end_time.strftime('%Y-%m-%d %H:%M:%S')})
    except Exception as e:
        logger.error(f"获取面试可预约状态时出错: {e}")
        return jsonify(success=False, error="服务器内部错误"), 500

@flask_app.route('/interview/schedule/available/<submit_id>', methods=['GET'])
async def get_available_schedules(submit_id):
    """
    获取指定投递（submit_id）所有可用的面试时间段。
    """
    uid = session.get('uid')
    if not uid:
        return jsonify(success=False, error="用户未登录"), 401

    try:
        with SQL() as sql:
            # 验证用户是否有权为该投递预约面试（本人操作 + 简历通过）
            submission = sql.fetch_one(
                'resume_submit',
                {'submit_id': submit_id, 'uid': uid, 'status': RESUME_PASSED_STATUS}
            )
            if not submission:
                return jsonify(success=False, error="该投递不符合面试预约条件(可能原因:非本人操作,或简历状态不为'简历通过')"), 403

            # 获取该投递的第一志愿，以匹配对应的面试地点
            resume_info = sql.fetch_one('resume_info', {'submit_id': submit_id})
            if not resume_info or not resume_info.get('first_choice'):
                return jsonify(success=False, error="找不到该投递的志愿信息"), 404
            
            target_choice = resume_info['first_choice']
            recruit_id = submission['recruit_id']

            # 找到所有适用于该招聘和该志愿的面试房间
            rooms = sql.fetch_all(
                'interview_room', 
                {'recruit_id': recruit_id, 'applicable_to_choice': target_choice}
            )
            if not rooms:
                return jsonify(success=True, data=[])

            room_ids = [room['room_id'] for room in rooms]
            if not room_ids:
                 return jsonify(success=True, data=[])
            
            # 一次性查询所有相关房间中尚未被预定的时间段
            placeholders = ','.join(['%s'] * len(room_ids))
            schedule_query = f"SELECT * FROM `interview_schedule` WHERE `room_id` IN ({placeholders}) AND `already_booked` = FALSE"
            schedules = sql.execute_query(schedule_query, room_ids)

            # 一次性获取所有相关房间信息以减少循环内查询
            room_info_query = f"SELECT `room_id`, `room_name`, `location` FROM `interview_room` WHERE `room_id` IN ({placeholders})"
            room_infos_raw = sql.execute_query(room_info_query, room_ids)
            room_infos = {room['room_id']: room for room in room_infos_raw}

            # 组合信息并返回给前端
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
    用户为指定的投递（submit_id）预约一个面试时间段。
    这是一个关键的事务性操作。
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
        with SQL() as sql: # 整个 `with` 块是一个事务
            # 1. 再次验证用户资格
            submission = sql.fetch_one('resume_submit', {'submit_id': submit_id, 'uid': uid})
            if not submission or submission['status'] != RESUME_PASSED_STATUS:
                return jsonify(success=False, error="该投递不符合面试预约条件"), 403

            # 2. 原子性地更新时间表，防止多人同时预约同一时段
            affected_rows = sql.update(
                'interview_schedule',
                {'already_booked': True},
                {'schedule_id': schedule_id, 'already_booked': False}
            )
            # 如果影响的行数为0，说明在你查询到更新的瞬间，别人抢先预约了
            if affected_rows == 0:
                return jsonify(success=False, error="该时间段已被预约，请选择其他时间"), 409

            # 3. 如果成功抢占时间段，则创建面试信息
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
            
            # 4. 将新创建的 interview_id 关联回 schedule
            sql.update('interview_schedule', {'booked_interview_id': interview_id}, {'schedule_id': schedule_id})
            
            # 5. 更新简历状态为“等待面试”
            sql.update('resume_submit', {'status': AWAITING_INTERVIEW_STATUS}, {'submit_id': submit_id})

            # 事务成功提交后，发送邮件通知
            recruit_info = sql.fetch_one('recruit', {'recruit_id': submission['recruit_id']})
            recruit_name = recruit_info.get('name', 'N/A') if recruit_info else 'N/A'
            resume_info = sql.fetch_one('resume_info', {'submit_id': submit_id})
            choice = resume_info.get('first_choice', 'N/A') if resume_info else 'N/A'
            interview_time_str = schedule['start_time'].strftime('%Y-%m-%d %H:%M:%S')
            location = room_info.get('location', 'N/A')
        await send_interview_booking_email(uid, recruit_name, choice, interview_time_str, location)
        
        return jsonify(success=True, message="面试预约成功", interview_id=interview_id)

    except Exception as e:
        logger.error(f"预约面试时出错: {e}")
        # 如果在 `with` 块中发生异常，`__exit__` 方法会自动回滚所有操作。
        # 这里可以尝试手动执行一次额外的、独立的数据库操作来回滚已占用的时间段（作为最后的保险措施）
        try:
            with SQL() as sql:
                sql.update('interview_schedule', {'already_booked': False, 'booked_interview_id': None}, {'schedule_id': schedule_id, 'booked_interview_id': None})
        except Exception as rollback_e:
            logger.error(f"尝试回滚面试预约状态失败: {rollback_e}")
        
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
            if SQL().validate_indentifier_part(recruit_id) is False:
                return jsonify(success=False, error="无效的 recruit_id"), 400

            query = """
                SELECT
                    ii.interview_id,
                    ii.submit_id,
                    ii.interview_time,
                    ii.location,
                    ri.first_choice as choice,
                    rm.room_id,
                    rm.room_name
                FROM
                    interview_info AS ii
                JOIN
                    resume_submit AS rs ON ii.submit_id = rs.submit_id
                JOIN
                    resume_info AS ri ON ii.submit_id = ri.submit_id
                JOIN
                    interview_schedule AS isch ON ii.interview_id = isch.booked_interview_id
                JOIN
                    interview_room AS rm ON isch.room_id = rm.room_id
                WHERE
                    ii.interviewee_uid = %s AND rs.recruit_id = %s
            """
            interviews = sql.execute_query(query, (uid, recruit_id))

            response_data = [
                {
                    'interview_id': info['interview_id'],
                    'submit_id': info['submit_id'],
                    'interview_time': info['interview_time'].strftime('%Y-%m-%d %H:%M:%S'),
                    'location': info['location'],
                    'choice': info['choice'],
                    'room_id': info['room_id'],
                    'room_name': info['room_name']
                } for info in interviews
            ]
            return jsonify(success=True, data=response_data)
    except Exception as e:
        logger.error(f"获取我的面试安排时出错: {e}")
        return jsonify(success=False, error="服务器内部错误"), 500

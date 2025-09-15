import os
import uuid
from flask import request, jsonify, session
from core.global_params import flask_app
import logging
from datetime import datetime, timedelta
from functools import wraps

# 假设这些是您项目中的工具类
from utils import SQL, is_admin_check, send_interview_cancellation_email

logger = logging.getLogger(__name__)

RESUME_PASSED_STATUS = 1    # "简历通过"
AWAITING_INTERVIEW_STATUS = 3 # "等待面试"

# --- 权限检查装饰器 ---
def admin_required(f):
    """
    一个装饰器，用于检查当前会话用户是否具有管理员权限。
    如果权限不足，则中断请求并返回 403 Forbidden 错误。
    """
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        uid = session.get('uid')
        if not uid:
            return jsonify(success=False, error="用户未登录"), 401
        
        with SQL() as sql:
            permission_info = sql.fetch_one('userpermission', {'uid': uid})
            if not is_admin_check(permission_info):
                return jsonify(success=False, error="管理员权限不足"), 403
        
        return await f(*args, **kwargs)
    return decorated_function

# ==============================================================================
# I. 招聘全局设置管理 (Recruitment Settings Management)
# ==============================================================================

@flask_app.route('/admin/interview/settings/<recruit_id>', methods=['POST'])
@admin_required
async def set_interview_availability(recruit_id):
    """
    (Admin) 设置指定招聘（recruit_id）的面试预约开放时间段。
    请求体 JSON: { "book_start_time": "YYYY-MM-DD HH:MM:SS", "book_end_time": "YYYY-MM-DD HH:MM:SS" }
    """
    data = request.json
    if not data or 'book_start_time' not in data or 'book_end_time' not in data:
        return jsonify(success=False, error="请求体缺少必要字段(book_start_time, book_end_time)"), 400

    try:
        start_time_str = data['book_start_time']
        end_time_str = data['book_end_time']
        book_start_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
        book_end_time = datetime.strptime(end_time_str, '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return jsonify(success=False, error="时间格式错误，应为 'YYYY-MM-DD HH:MM:SS'"), 400

    if book_start_time >= book_end_time:
        return jsonify(success=False, error="预约开始时间必须早于结束时间"), 400

    try:
        with SQL() as sql:
            if not sql.fetch_one('recruit', {'recruit_id': recruit_id}):
                return jsonify(success=False, error="无效的招聘ID"), 404

            # 【已修复】操作正确的表 `recruit_interview_settings`
            # 检查记录是否存在，不存在则插入，存在则更新 (Upsert逻辑)
            settings_exist = sql.fetch_one('recruit_interview_settings', {'recruit_id': recruit_id})
            
            update_data = {
                'book_start_time': start_time_str,
                'book_end_time': end_time_str
            }

            if settings_exist:
                sql.update('recruit_interview_settings', update_data, {'recruit_id': recruit_id})
            else:
                update_data['recruit_id'] = recruit_id
                sql.insert('recruit_interview_settings', update_data)
                
        return jsonify(success=True, message="面试预约时间设置成功")
    except Exception as e:
        logger.error(f"设置面试预约时间时出错: {e}")
        return jsonify(success=False, error="服务器内部错误"), 500

# ==============================================================================
# II. 面试地点管理 (Interview Room Management)
# ==============================================================================

@flask_app.route('/admin/interview/room/add', methods=['POST'])
@admin_required
async def add_interview_room():
    """(Admin) 添加一个新的面试地点。"""
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
        return jsonify(success=True, message="面试地点添加成功", room_id=room_id), 201
    except Exception as e:
        logger.error(f"添加面试地点时出错: {e}")
        return jsonify(success=False, error="服务器内部错误"), 500

@flask_app.route('/admin/interview/room/<room_id>', methods=['PUT'])
@admin_required
async def update_interview_room(room_id):
    """(Admin) 更新一个面试地点的信息。"""
    data = request.json
    if not data:
        return jsonify(success=False, error="请求体不能为空"), 400

    update_fields = {}
    if 'room_name' in data:
        update_fields['room_name'] = data['room_name']
    if 'location' in data:
        update_fields['location'] = data['location']
    if 'applicable_to_choice' in data:
        update_fields['applicable_to_choice'] = data['applicable_to_choice']

    if not update_fields:
        return jsonify(success=False, error="没有提供任何可更新的字段"), 400

    try:
        with SQL() as sql:
            if not sql.fetch_one('interview_room', {'room_id': room_id}):
                return jsonify(success=False, error="面试地点不存在"), 404
            sql.update('interview_room', update_fields, {'room_id': room_id})
        return jsonify(success=True, message="面试地点信息更新成功")
    except Exception as e:
        logger.error(f"更新面试地点时出错: {e}")
        return jsonify(success=False, error="服务器内部错误"), 500


@flask_app.route('/admin/interview/room/<room_id>', methods=['DELETE'])
@admin_required
async def delete_interview_room(room_id):
    """
    (Admin) 删除一个面试地点。
    安全检查：如果该地点下有任何已被预定的时间段，则禁止删除。
    """
    try:
        with SQL() as sql:
            if not sql.fetch_one('interview_room', {'room_id': room_id}):
                return jsonify(success=False, error="面试地点不存在"), 404

            # 【已修复】检查正确的表 `interview_schedule` 和字段 `already_booked`
            booked_slots = sql.fetch_one('interview_schedule', {'room_id': room_id, 'already_booked': True})
            if booked_slots:
                return jsonify(success=False, error="无法删除：该地点下存在已预约的面试，请先处理这些面试。"), 409

            # 安全地删除所有关联的（未被预约的）时间段，然后删除地点本身
            sql.delete('interview_schedule', {'room_id': room_id})
            sql.delete('interview_room', {'room_id': room_id})

        return jsonify(success=True, message="面试地点及关联的可用时段已成功删除")
    except Exception as e:
        logger.error(f"删除面试地点时出错: {e}")
        return jsonify(success=False, error="服务器内部错误"), 500


@flask_app.route('/admin/interview/room/list/<recruit_id>', methods=['GET'])
@admin_required
async def list_interview_rooms(recruit_id):
    """(Admin) 获取指定招聘下的所有面试地点。"""
    try:
        with SQL() as sql:
            rooms = sql.fetch_all('interview_room', {'recruit_id': recruit_id})
            return jsonify(success=True, data=rooms)
    except Exception as e:
        logger.error(f"获取面试地点列表时出错: {e}")
        return jsonify(success=False, error="服务器内部错误"), 500

# ==============================================================================
# III. 面试时段管理 (Interview Schedule Management)
# ==============================================================================

@flask_app.route('/admin/interview/schedules/add/<room_id>', methods=['POST'])
@admin_required
async def add_interview_schedules(room_id):
    """
    (Admin) 为指定面试地点批量添加面试时间段。
    请求体 JSON: { "start_time": "YYYY-MM-DD HH:MM:SS", "end_time": "YYYY-MM-DD HH:MM:SS", "duration_minutes": 30 }
    """
    data = request.json
    if not all(k in data for k in ['start_time', 'end_time', 'duration_minutes']):
        return jsonify(success=False, error="缺少必要字段(start_time, end_time, duration_minutes)"), 400

    try:
        start_time = datetime.strptime(data['start_time'], '%Y-%m-%d %H:%M:%S')
        end_time = datetime.strptime(data['end_time'], '%Y-%m-%d %H:%M:%S')
        duration = timedelta(minutes=int(data['duration_minutes']))
    except (ValueError, TypeError):
        return jsonify(success=False, error="时间格式或时长错误"), 400

    if start_time >= end_time or duration.total_seconds() <= 0:
        return jsonify(success=False, error="开始时间必须早于结束时间，且时长必须为正数"), 400

    try:
        with SQL() as sql:
            if not sql.fetch_one('interview_room', {'room_id': room_id}):
                return jsonify(success=False, error="面试地点不存在"), 404

            generated_schedules = []
            current_time = start_time
            while current_time < end_time:
                schedule_end_time = current_time + duration
                if schedule_end_time > end_time:
                    break
                
                # 【已修复】适配数据库表和字段名
                schedule_id = str(uuid.uuid4())
                sql.insert('interview_schedule', {
                    'schedule_id': schedule_id,
                    'room_id': room_id,
                    'start_time': current_time,
                    'end_time': schedule_end_time,
                    'already_booked': False,
                    'booked_interview_id': None # 明确设为NULL
                })
                generated_schedules.append(schedule_id)
                current_time = schedule_end_time

        return jsonify(success=True, message=f"成功生成 {len(generated_schedules)} 个面试时段", generated_schedule_ids=generated_schedules), 201
    except Exception as e:
        logger.error(f"添加面试时段时出错: {e}")
        return jsonify(success=False, error="服务器内部错误"), 500

@flask_app.route('/admin/interview/schedules/list/<room_id>', methods=['GET'])
@admin_required
async def list_interview_schedules(room_id):
    """(Admin) 获取指定面试地点下的所有时间段及其状态。"""
    try:
        with SQL() as sql:
            if not sql.fetch_one('interview_room', {'room_id': room_id}):
                return jsonify(success=False, error="面试地点不存在"), 404
            
            # 【已修复】查询正确的表
            schedules = sql.fetch_all('interview_schedule', {'room_id': room_id})
            # 格式化时间以便前端显示
            for schedule in schedules:
                if schedule.get('start_time'):
                    schedule['start_time'] = schedule['start_time'].strftime('%Y-%m-%d %H:%M:%S')
                if schedule.get('end_time'):
                    schedule['end_time'] = schedule['end_time'].strftime('%Y-%m-%d %H:%M:%S')
            schedules.sort(key=lambda x: x['start_time'])
            return jsonify(success=True, data=schedules)
    except Exception as e:
        logger.error(f"获取面试时段列表时出错: {e}")
        return jsonify(success=False, error="服务器内部错误"), 500


@flask_app.route('/admin/interview/schedule/<schedule_id>', methods=['DELETE'])
@admin_required
async def delete_interview_schedule(schedule_id):
    """
    (Admin) 删除一个未被预约的面试时段。
    """
    try:
        with SQL() as sql:
            # 【已修复】操作正确的表和字段
            schedule_info = sql.fetch_one('interview_schedule', {'schedule_id': schedule_id})
            if not schedule_info:
                return jsonify(success=False, error="面试时段不存在"), 404
            if schedule_info['already_booked']:
                return jsonify(success=False, error="无法删除，该时段已被预约"), 409
            
            sql.delete('interview_schedule', {'schedule_id': schedule_id})
            return jsonify(success=True, message="面试时段已成功删除")
    except Exception as e:
        logger.error(f"删除面试时段时出错: {e}")
        return jsonify(success=False, error="服务器内部错误"), 500

# ==============================================================================
# IV. 面试安排与结果管理 (Interview Scheduling & Result Management)
# ==============================================================================

@flask_app.route('/admin/interview/list/<recruit_id>', methods=['GET'])
@admin_required
async def list_interviews(recruit_id):
    """
    (Admin) 获取指定招聘的所有已安排面试列表，包含面试者信息和结果。
    """
    try:
        with SQL() as sql:
            # 【已修复】使用 LEFT JOIN 关联 interview_review 表来获取结果
            query = """
                SELECT
                    ii.interview_id, ii.submit_id, ii.interviewee_uid,
                    ui.realname, ui.nickname,
                    ii.interview_time, ii.location, ii.notes,
                    ir.passed, ir.score, ir.comments AS interviewer_feedback, ir.reviewer_uid, ir.review_time,
                    rm.room_id,
                    rm.room_name,
                    ri.first_choice
                FROM
                    interview_info AS ii
                JOIN
                    resume_submit AS rs ON ii.submit_id = rs.submit_id
                JOIN
                    userinfo AS ui ON ii.interviewee_uid = ui.uid
                LEFT JOIN
                    interview_review AS ir ON ii.interview_id = ir.interview_id
                LEFT JOIN
                    interview_schedule AS isch ON ii.interview_id = isch.booked_interview_id
                LEFT JOIN
                    interview_room AS rm ON isch.room_id = rm.room_id
                LEFT JOIN
                    resume_info AS ri ON ii.submit_id = ri.submit_id
                WHERE
                    rs.recruit_id = %s
                ORDER BY
                    ii.interview_time DESC
            """
            interviews = sql.execute_query(query, (recruit_id,))

            interview_list = [
                {
                    'interview_id': item['interview_id'],
                    'submit_id': item['submit_id'],
                    'interviewee_uid': item['interviewee_uid'],
                    'interviewee_name': item.get('realname') or item.get('nickname', '未知'),
                    'interview_time': item['interview_time'].strftime('%Y-%m-%d %H:%M:%S') if item['interview_time'] else None,
                    'location': item.get('location', 'N/A'),
                    'notes': item.get('notes', ''),
                    # 【已修复】从关联表中获取结果
                    'result_passed': item.get('passed'), # bool or None
                    'score': item.get('score'),
                    'interviewer_feedback': item.get('interviewer_feedback'),
                    'reviewer_uid': item.get('reviewer_uid'),
                    'review_time': item['review_time'].strftime('%Y-%m-%d %H:%M:%S') if item.get('review_time') else None,
                    'room_id': item.get('room_id'),
                    'room_name': item.get('room_name'),
                    'first_choice': item.get('first_choice')
                } for item in interviews
            ]
            interview_list.sort(key=lambda x: x['interview_time'], reverse=True)
            return jsonify(success=True, data=interview_list)
    except Exception as e:
        logger.error(f"获取面试列表时出错: {e}")
        return jsonify(success=False, error="服务器内部错误"), 500

@flask_app.route('/admin/interview/<interview_id>/reschedule', methods=['PUT'])
@admin_required
async def reschedule_interview(interview_id):
    """(Admin) 修改一个已安排面试的时间、地点或备注。"""
    data = request.json
    if not data:
        return jsonify(success=False, error="请求体不能为空"), 400

    update_fields = {}
    if 'interview_time' in data:
        try:
            datetime.strptime(data['interview_time'], '%Y-%m-%d %H:%M:%S')
            update_fields['interview_time'] = data['interview_time']
        except (ValueError, TypeError):
            return jsonify(success=False, error="时间格式错误"), 400
    if 'location' in data:
        update_fields['location'] = data['location']
    if 'notes' in data:
        update_fields['notes'] = data['notes']

    if not update_fields:
        return jsonify(success=False, error="没有提供任何可更新的字段"), 400
        
    try:
        with SQL() as sql:
            if not sql.fetch_one('interview_info', {'interview_id': interview_id}):
                return jsonify(success=False, error="面试记录不存在"), 404
            
            sql.update('interview_info', update_fields, {'interview_id': interview_id})
            return jsonify(success=True, message="面试信息更新成功")
    except Exception as e:
        logger.error(f"更新面试信息时出错: {e}")
        return jsonify(success=False, error="服务器内部错误"), 500

@flask_app.route('/admin/interview/<interview_id>/cancel', methods=['POST'])
@admin_required
async def cancel_interview(interview_id):
    """
    (Admin) 取消一个已安排的面试。
    该操作会删除面试记录，并释放其占用的 interview_schedule (如果有关联)。
    """
    try:
        with SQL() as sql: # 整个代码块是一个事务
            interview_info = sql.fetch_one('interview_info', {'interview_id': interview_id})
            if not interview_info:
                return jsonify(success=False, error="面试记录不存在"), 404

            # 【已修复】重写逻辑以正确解绑 interview_schedule
            # 1. 查找并释放关联的 schedule
            schedule_to_release = sql.fetch_one('interview_schedule', {'booked_interview_id': interview_id})
            if schedule_to_release:
                sql.update('interview_schedule', 
                           {'already_booked': False, 'booked_interview_id': None},
                           {'schedule_id': schedule_to_release['schedule_id']})
            
            # 2. 删除面试记录
            sql.delete('interview_info', {'interview_id': interview_id})
            
            # 3. （可选）将用户的简历状态重置回“简历通过”，以便他们可以重新预约
            if interview_info.get('submit_id'):
                resume_submit = sql.fetch_one('resume_submit', {'submit_id': interview_info['submit_id']})
                if resume_submit and resume_submit.get('status') == AWAITING_INTERVIEW_STATUS:
                    sql.update('resume_submit', {'status': RESUME_PASSED_STATUS}, {'submit_id': interview_info['submit_id']})

            # 4. 发送取消通知邮件
            try:
                submit_id = interview_info.get('submit_id')
                if submit_id:
                    with SQL() as sql:
                        resume_info = sql.fetch_one('resume_info', {'submit_id': submit_id})
                        resume_submit = sql.fetch_one('resume_submit', {'submit_id': submit_id})
                    first_choice = resume_info.get('first_choice') if resume_info else 'N/A'
                    recruit_id = resume_submit.get('recruit_id') if resume_submit else None
                    recruit_name = 'N/A'
                    if recruit_id:
                        with SQL() as sql:
                            recruit_info = sql.fetch_one('recruit', {'recruit_id': recruit_id})
                            if recruit_info:
                                recruit_name = recruit_info.get('name', 'N/A')
                    
                await send_interview_cancellation_email(
                    interview_info['interviewee_uid'],
                    recruit_name,
                    first_choice,
                    interview_info['interview_time'].strftime('%Y-%m-%d %H:%M:%S') if interview_info.get('interview_time') else 'N/A'
                )
            except Exception as e:
                logger.error(f"发送面试取消邮件时出错: {e}")


        return jsonify(success=True, message="面试已取消，关联的时间段（如有）已释放，用户可重新预约")
    except Exception as e:
        logger.error(f"取消面试时出错: {e}")
        return jsonify(success=False, error="服务器内部错误"), 500

@flask_app.route('/admin/interview/<interview_id>/result', methods=['POST'])
@admin_required
async def record_interview_result(interview_id):
    """
    (Admin) 记录或更新面试结果。
    此操作将向 interview_review 表插入或更新一条记录。
    请求体 JSON: { "passed": true/false, "score": 85 (optional), "comments": "..." (optional) }
    """
    data = request.json

    reviewer_uid = session.get('uid')
    if not reviewer_uid:
         return jsonify(success=False, error="无法获取管理员ID，请重新登录"), 401

    try:
        with SQL() as sql:
            if not sql.fetch_one('interview_info', {'interview_id': interview_id}):
                return jsonify(success=False, error="面试记录不存在"), 404

            # 【已修复】向 `interview_review` 表插入数据
            review_data = {
                'review_id': str(uuid.uuid4()),
                'interview_id': interview_id,
                'reviewer_uid': reviewer_uid,
                'review_time': datetime.now(),
                'passed': data.get('passed', False),
                'score': data.get('score', 0),
                'comments': data.get('comments', '')
            }
            
            sql.insert('interview_review', review_data)

            return jsonify(success=True, message="面试结果记录成功")
    except Exception as e:
        logger.error(f"记录面试结果时出错: {e}")
        return jsonify(success=False, error="服务器内部错误"), 500

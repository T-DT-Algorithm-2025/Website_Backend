import asyncio
from core.global_params import cMailer, sms_client
from utils.sql import SQL
import logging

logger = logging.getLogger(__name__)

async def send_application_submission_email(uid, recruit_name, choice):
    """
    发送简历投递成功邮件通知
    """
    try:
        with SQL() as sql:
            user_info = sql.fetch_one('user', {'uid': uid})
            if user_info and user_info.get('mail'):
                mail_to = user_info['mail']
                subject = "【T-DT创新实验室】简历投递成功通知"
                content = f"""同学您好,
                <br><br>感谢您投递<b>{recruit_name}</b>的<b>{choice}</b>岗位。我们已经收到了您的简历，请耐心等待后续通知。
                <br><br>-- T-DT创新实验室"""
                async with cMailer() as mailer:
                    await mailer.send(mail_to, subject, content, subtype='html')
                logger.info(f"成功向 {mail_to} 发送简历投递成功邮件。")
    except Exception as e:
        logger.error(f"发送简历投递邮件给 {uid} 时出错: {e}")

async def send_interview_booking_email(uid, recruit_name, choice, interview_time, location):
    """
    发送面试预约成功邮件通知
    """
    try:
        with SQL() as sql:
            user_info = sql.fetch_one('user', {'uid': uid})
            if user_info and user_info.get('mail'):
                mail_to = user_info['mail']
                subject = "【T-DT创新实验室】面试预约成功通知"
                content = f"""同学您好,
                <br><br>您已成功预约<b>{recruit_name}</b>的<b>{choice}</b>岗位的面试。
                <br>面试时间: <b>{interview_time}</b>
                <br>面试地点: <b>{location}</b>
                <br><br>请准时参加。
                <br><br>-- T-DT创新实验室"""
                async with cMailer() as mailer:
                    await mailer.send(mail_to, subject, content, subtype='html')
                logger.info(f"成功向 {mail_to} 发送面试预约成功邮件。")
    except Exception as e:
        logger.error(f"发送面试预约邮件给 {uid} 时出错: {e}")


async def send_status_change_notification(submit_id, new_status_name):
    """
    发送简历状态变更的邮件和短信通知
    """
    try:
        with SQL() as sql:
            submission = sql.fetch_one('resume_submit', {'submit_id': submit_id})
            if not submission:
                return

            uid = submission['uid']
            recruit_id = submission['recruit_id']
            
            user_info = sql.fetch_one('user', {'uid': uid})
            user_phone_info = sql.fetch_one('userphone', {'uid': uid})
            recruit_info = sql.fetch_one('recruit', {'recruit_id': recruit_id})
            resume_info = sql.fetch_one('resume_info', {'submit_id': submit_id})
            
            recruit_name = recruit_info.get('name', 'N/A') if recruit_info else 'N/A'
            choice = resume_info.get('first_choice', 'N/A') if resume_info else 'N/A'

            # 邮件通知
            if user_info and user_info.get('mail'):
                mail_to = user_info['mail']
                subject = f"【T-DT创新实验室】您的投递状态已更新为: {new_status_name}"
                content = f"""同学您好,
                <br><br>您投递的<b>{recruit_name}</b>的<b>{choice}</b>岗位的状态已更新为: <b>{new_status_name}</b>。
                <br><br>请登录我们的网站查看详情。
                <br><br>-- T-DT创新实验室"""
                async with cMailer() as mailer:
                    await mailer.send(mail_to, subject, content, subtype='html')
                logger.info(f"成功向 {mail_to} 发送状态变更邮件。")

            # 短信通知 (仅在特定状态下)
            sms_statuses = ["简历通过", "简历未通过", "面试未通过", "已录取"]
            if new_status_name in sms_statuses and user_phone_info and user_phone_info.get('phone_number') and sms_client:
                phone_number = user_phone_info['phone_number']
                sms_content = f"【TDT创新实验室】同学您好，感谢您投递{recruit_name}，您在{choice}投递的简历已更新为{new_status_name}，感谢您对T-DT创新实验室的支持。"
                
                # 异步发送短信
                loop = asyncio.get_event_loop()
                loop.run_in_executor(None, sms_client.send, phone_number, sms_content)
                logger.info(f"已向 {phone_number} 发送状态变更短信。")

    except Exception as e:
        logger.error(f"为 submit_id {submit_id} 发送状态变更通知时出错: {e}")
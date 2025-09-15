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
            感谢您投递<b>{recruit_name}</b>的<b>{choice}</b>岗位。我们已经收到了您的简历，请耐心等待后续通知。
            -- T-DT创新实验室"""
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

async def send_interview_cancellation_email(uid, recruit_name, choice, interview_time):
    """
    发送面试取消邮件通知
    """
    try:
        with SQL() as sql:
            user_info = sql.fetch_one('user', {'uid': uid})
            phone_info = sql.fetch_one('userphone', {'uid': uid})
            user_info_info = sql.fetch_one('userinfo', {'uid': uid})
        realname = user_info_info.get('realname', '') if user_info_info else ''
        # 邮件通知
        if user_info and user_info.get('mail'):
            mail_to = user_info['mail']
            subject = "【T-DT创新实验室】面试取消通知"
            content = f"""亲爱的{realname}同学您好,
            <br><br>您预约的<b>{recruit_name}</b>的<b>{choice}</b>岗位的面试已被取消。
            <br><b>请您及时登录系统重新预约。</b>
            <br>原定面试时间: <b>{interview_time}</b>
            <br><br>如有疑问，请联系相关负责人。
            <br><br>-- T-DT创新实验室"""
            async with cMailer() as mailer:
                await mailer.send(mail_to, subject, content, subtype='html')
            logger.info(f"成功向 {mail_to} 发送面试取消邮件。")

        # 短信通知
        if phone_info and phone_info.get('phone_number') and sms_client:
            phone_number = phone_info['phone_number']
            sms_content = f"【TDT创新实验室】亲爱的{realname}同学您好，您预约的{recruit_name}的{choice}岗位的面试已被取消，请您及时登录系统重新预约。"
            sms_client.send(phone_number, sms_content)
            logger.info(f"已向 {phone_number} 发送面试取消短信。")
    except Exception as e:
        logger.error(f"发送面试取消邮件给 {uid} 时出错: {e}")


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
            user_info_info = sql.fetch_one('userinfo', {'uid': uid})
            recruit_info = sql.fetch_one('recruit', {'recruit_id': recruit_id})
            resume_info = sql.fetch_one('resume_info', {'submit_id': submit_id})
            
        recruit_name = recruit_info.get('name', 'N/A') if recruit_info else 'N/A'
        choice = resume_info.get('first_choice', 'N/A') if resume_info else 'N/A'
        realname = user_info_info.get('realname', '') if user_info_info else ''
        plan_name = recruit_info.get('name', 'N/A') if recruit_info else 'N/A'
        # 邮件通知
        if user_info and user_info.get('mail'):
            mail_to = user_info['mail']
            subject = f"【T-DT创新实验室】您的投递状态已更新为: {new_status_name}"
            content = f"""同学您好,
            您投递的 {recruit_name} 的 {choice} 岗位的状态已更新为:  {new_status_name}。
            请登录我们的网站查看详情。
            -- T-DT创新实验室"""
            if new_status_name == '简历通过':
                content = f"""亲爱的{realname}同学您好,
                <br><br>感谢您投递<b>{recruit_name}</b>的<b>{choice}</b>岗位。我们很高兴地通知您，您的简历已通过初筛！
                <br>请尽快登录系统预约面试，以进行下一步的操作。
                <br><br>感谢您对我们的关注和信任。祝您面试顺利！
                <br><br>-- T-DT创新实验室"""
            elif new_status_name == '已录取':
                content = f"""亲爱的{realname}同学您好,
                <br><br>感谢您投递<b>{recruit_name}</b>的<b>{choice}</b>岗位。我们很高兴地通知您，您已通过面试，正式成为{plan_name}的一员！
                <br>我们衷心期待您的到来。
                <br><br>再次非常感谢您对我们工作的支持与信任，祝您学业有成，生活美满。
                <br><br>-- T-DT创新实验室"""
            elif new_status_name == '简历未通过' or new_status_name == '面试未通过':
                content = f"""亲爱的{realname}同学您好,
                <br><br>感谢您投递<b>{recruit_name}</b>的<b>{choice}</b>岗位。对于您的申请，我们经过了慎重的考虑，您不是该岗位的最佳人选，因此我们无法为您推进后续安排。
                <br>这并非说明您不够优秀，只是不一定适合我们实验室。
                <br><br>再次感谢您的信任与参与，祝愿您学业有成！
                <br><br>-- T-DT创新实验室"""
            
            async with cMailer() as mailer:
                await mailer.send(mail_to, subject, content, subtype='plain')

            logger.info(f"成功向 {mail_to} 发送状态变更邮件。")
        # 短信通知 (仅在特定状态下)
        sms_statuses = ["简历通过", "简历未通过", "面试未通过", "已录取"]
        if new_status_name in sms_statuses and user_phone_info and user_phone_info.get('phone_number') and sms_client:
            phone_number = user_phone_info['phone_number']
            sms_content = f"【TDT创新实验室】同学您好，感谢您投递{recruit_name}，您在{choice}投递的简历已更新为{new_status_name}，感谢您对T-DT创新实验室的支持。"
            if new_status_name == '简历通过':
                sms_content = f"【TDT创新实验室】亲爱的{realname}同学您好， 感谢您投递{recruit_name}，我们很高兴地通知您，对于您在{choice}的投递，已经通过了简历初筛！请尽快登陆系统预约面试，以进行下一步的操作。 感谢您对我们的关注和信任。祝您面试顺利！"
            elif new_status_name == '已录取':
                sms_content = f"【TDT创新实验室】亲爱的{realname}同学您好， 感谢您投递{recruit_name}，我们很高兴地通知您，对于您在{choice}的投递，已经通过了面试！非常感谢您加入{plan_name}，我们衷心期待您的到来。再次非常感谢您对我们工作的支持与信任，祝您学业有成，生活美满。"
            elif new_status_name == '简历未通过' or new_status_name == '面试未通过':
                sms_content = f"【TDT创新实验室】亲爱的{realname}同学您好， 感谢您投递{recruit_name}，对于您在{choice}的投递，我们经过了慎重的考虑，您不是该岗位的最佳人选，因此我们无法为您推进后续安排。这并非说明您不够优秀，只是不一定适合我们实验室。再次感谢您的信任与参与，祝愿您学业有成！"
            sms_client.send(phone_number, sms_content)
            logger.info(f"已向 {phone_number} 发送状态变更短信。")

    except Exception as e:
        logger.error(f"为 submit_id {submit_id} 发送状态变更通知时出错: {e}")
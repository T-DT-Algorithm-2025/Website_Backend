import utils
import json
import asyncio
from flask import Flask, jsonify
import flask_cors
import redis
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

# Global parameters
database_config = json.load(open('config/database.json'))

global_config = json.load(open('config/config.json'))

mail_config = json.load(open('config/mail.json'))

oauth_config = json.load(open('config/oauth.json'))

db_config = {
    'host': database_config['sql']['sql_host'],
    'port': database_config['sql']['sql_port'],
    'user': database_config['sql']['sql_database_user'],
    'password': database_config['sql']['sql_database_passwd'],
    'db': database_config['sql']['sql_database_name'],
    'charset': 'utf8mb4'
}
utils.DatabaseManager.initialize_pool(**db_config)

redis_client = utils.RedisClient(
    host=database_config['redis']['redis_host'], 
    port=database_config['redis']['redis_port'], 
    db=database_config['redis']['redis_db'], 
    password=database_config['redis']['redis_password']
)

mailer = utils.Mailer(mail_config['host'], mail_config['port'],
                    mail_config['user'], mail_config['passwd'])

try:
    sms_config = json.load(open('config/sms.json'))
    sms_client = utils.SmsBao(sms_config['username'], sms_config['password'])
except (FileNotFoundError, KeyError):
    sms_client = None
    logger.warning("警告: 短信配置文件 'config/sms.json' 未找到或格式不正确，短信功能将不可用。")

flask_app = Flask(__name__)
flask_app.debug = False
flask_app.config['SECRET_KEY'] = global_config['secret_key']
flask_app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=global_config.get('login_expire_days', 7))
flask_app.config['MAX_CONTENT_LENGTH'] = global_config.get('max_content_length', 16 * 1024 * 1024)  # Default to 16MB

@flask_app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify(success=False, error=f'文件太大，请上传小于{flask_app.config["MAX_CONTENT_LENGTH"] // 1024 // 1024}MB的文件'), 413

flask_cors.CORS(flask_app)

async def check_data_base():
    sql_tables = [
        'user', 'userinfo', 'useravatar', 'userpermission', 'recruit', 'userphone', 'usermailverify',
        'resume_submit', 'resume_info', 'resume_review', 'resume_status_names', 'resume_user_real_head_img',
        'interview_info', 'interview_room', 'interview_schedule', 'interview_review'
    ]
    sql_params = {
        "user": ("uid char(36) primary key", "openid_qq char(64)", "openid_wx char(64)", "mail char(64)", "pwd char(64)"),
        "userinfo": ("uid char(36) primary key", "nickname char(64)", "gender char(10)", "realname char(64)", "registration_time datetime",
                     "student_id char(20)", "department char(64)", "major char(64)", "grade char(10)", "rank char(10)"),
        "useravatar": ("uid char(36) primary key", "avatar_path char(255)"),
        "userpermission": ("uid char(36) primary key", "is_main_leader_admin bool", "is_group_leader_admin bool", "is_member_admin bool", "is_banned bool", "ban_reason char(255)"),
        "userphone": ("uid char(36) primary key", "phone_number char(20)", "is_verified bool", "verification_code char(10)", "code_sent_time datetime"),
        "usermailverify": ("mail char(64) primary key", "verification_code char(10)", "code_sent_time datetime"),
        "recruit": ("recruit_id char(36) primary key", "name char(64)", "start_time datetime", "end_time datetime", "description text", "is_active bool"),
        "resume_submit": ("submit_id char(64) primary key", "uid char(36)", "recruit_id char(36)", "submit_time datetime", "status int"),
        "resume_info": ("submit_id char(64) primary key", "first_choice char(64)", "second_choice char(64)", "self_intro text", "skills text", "projects text", "awards text", "grade_point char(10)", "grade_rank char(10)", "additional_file_path text"),
        "resume_review": ("review_id char(36) primary key", "submit_id char(64)", "reviewer_uid char(36)", "review_time datetime", "comments text", "score int", "passed bool"),
        "resume_status_names": ("status_id int primary key", "status_name char(64)"),
        "resume_user_real_head_img": ("submit_id char(64) primary key", "real_head_img_path char(255)"),
        "interview_info": ("interview_id char(36) primary key", "submit_id char(64)", "interviewee_uid char(36)", "interview_time datetime", "location char(255)", "notes text"),
        "interview_room": ("room_id char(36) primary key", "room_name char(64)","location char(255)", "recruit_id char(36)", "applicable_to_choice char(64)"),
        "interview_schedule": ("schedule_id char(36) primary key", "room_id char(36)", "start_time datetime", "end_time datetime", "already_booked bool", "booked_interview_id char(36)"),
        "interview_review": ("review_id char(36) primary key", "interview_id char(36)", "reviewer_uid char(36)", "review_time datetime", "comments text", "score int", "passed bool"),
        "recruit_interview_settings": ("recruit_id char(36) primary key", "book_start_time datetime", "book_end_time datetime")
    }

    with utils.SQL() as sql:
        db_name = db_config['db']
        for table in sql_tables:
            # 检查表是否存在
            form = sql.execute_query(
                "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
                (db_name, table)
            )
            if not form:
                # 如果表不存在，则创建
                create_sql = f"CREATE TABLE `{table}` ({', '.join(sql_params[table])})"
                sql.execute_update(create_sql)
                print(f"Table '{table}' created.")
            else:
                # 如果表存在，则检查字段
                # 获取现有字段
                existing_columns_info = sql.execute_query(f"SHOW COLUMNS FROM `{table}`")
                existing_columns = {col['Field'] for col in existing_columns_info}

                # 获取期望的字段
                expected_columns_defs = sql_params[table]
                expected_columns = {col.strip().split()[0].replace('`', '') for col in expected_columns_defs}

                # 添加缺失的字段
                missing_columns = expected_columns - existing_columns
                for col_name in missing_columns:
                    col_def = next(s for s in expected_columns_defs if s.strip().startswith(col_name))
                    alter_sql = f"ALTER TABLE `{table}` ADD COLUMN {col_def}"
                    sql.execute_update(alter_sql)
                    print(f"Added missing column '{col_name}' to table '{table}'.")

                # 删除多余的字段
                extra_columns = existing_columns - expected_columns
                for col_name in extra_columns:
                    # 安全检查：避免误删主键
                    is_primary = any(col['Key'] == 'PRI' for col in existing_columns_info if col['Field'] == col_name)
                    if not is_primary:
                        alter_sql = f"ALTER TABLE `{table}` DROP COLUMN `{col_name}`"
                        sql.execute_update(alter_sql)
                        print(f"Removed extra column '{col_name}' from table '{table}'.")

    # 状态检查
    status_list = ["未处理", "简历通过", "简历未通过", "等待面试", "面试未通过", "已录取", "未参加面试"]
    with utils.SQL() as sql:
        existing_status = sql.fetch_all('resume_status_names')
        existing_status_ids = [item['status_id'] for item in existing_status] if existing_status else []
        for idx, status in enumerate(status_list):
            if idx not in existing_status_ids:
                sql.insert('resume_status_names', {'status_id': idx, 'status_name': status})
        for item in existing_status:
            if item['status_id'] < 0 or item['status_id'] >= len(status_list):
                sql.delete('resume_status_names', {'status_id': item['status_id']})
            elif item['status_name'] != status_list[item['status_id']]:
                sql.update('resume_status_names', {'status_name': status_list[item['status_id']]}, {'status_id': item['status_id']})


async def initialize_mailer():
    try:
        await mailer.connect()
    except Exception as e:
        print(f"邮件服务初始化失败: {e}")

async def initialize():
    await check_data_base()
    await initialize_mailer()

# 使用 asyncio.run() 来替代旧的 event loop 管理方式，更简洁健壮
try:
    asyncio.run(initialize())
except RuntimeError:
    # 如果事件循环已在运行（例如在某些环境中），则创建任务
    loop = asyncio.get_event_loop()
    loop.create_task(initialize())


resume_submit_ip_time_history = {}

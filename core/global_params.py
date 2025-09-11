import utils
import json
import asyncio
from flask import Flask, jsonify
import flask_cors
import redis
from datetime import timedelta
import logging
import re

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

mail_info = {
    'host': mail_config['host'],
    'port': mail_config['port'],
    'user': mail_config['user'],
    'password': mail_config['passwd'],
    'use_tls': True
}

def cMailer():
    return utils.Mailer(**mail_info)

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
        'interview_info', 'interview_room', 'interview_schedule', 'interview_review', 'recruit_interview_settings'
    ]
    sql_params = {
        # ... 您的 sql_params 字典保持不变 ...
        "user": ("uid char(36) primary key", "openid_qq char(64)", "openid_wx char(64)", "mail char(64)", "pwd char(255)"),
        "userinfo": ("uid char(36) primary key", "nickname char(64)", "gender char(10)", "realname char(64)", "registration_time datetime",
                       "student_id char(20)", "department char(64)", "major char(64)", "grade char(10)", "rank char(10)"),
        "useravatar": ("uid char(36) primary key", "avatar_path char(255)"),
        "userpermission": ("uid char(36) primary key", "is_main_leader_admin bool", "is_group_leader_admin bool", "is_member_admin bool", "is_banned bool", "ban_reason char(255)"),
        "userphone": ("uid char(36) primary key", "phone_number char(20)", "is_verified bool", "verification_code char(10)", "code_sent_time datetime"),
        "usermailverify": ("mail char(64) primary key", "verification_code char(10)", "code_sent_time datetime"),
        "recruit": ("recruit_id char(36) primary key", "name char(64)", "start_time datetime", "end_time datetime", "description text", "is_active bool"),
        "resume_submit": ("submit_id char(64) primary key", "uid char(36)", "recruit_id char(36)", "submit_time datetime", "status int"),
        "resume_info": ("submit_id char(64) primary key", "first_choice char(64)", "second_choice char(64)", "self_intro text", "skills text", "projects text", "awards text", "grade_point char(10)", "grade_rank char(10)", "additional_file_path text", "additional_file_name char(64)"),
        "resume_review": ("review_id char(36) primary key", "submit_id char(64)", "reviewer_uid char(36)", "review_time datetime", "comments text", "score int", "passed bool"),
        "resume_status_names": ("status_id int primary key", "status_name char(64)"),
        "resume_user_real_head_img": ("submit_id char(64) primary key", "real_head_img_path char(255)"),
        "interview_info": ("interview_id char(36) primary key", "submit_id char(64)", "interviewee_uid char(36)", "interview_time datetime", "location char(255)", "notes text"),
        "interview_room": ("room_id char(36) primary key", "room_name char(64)","location char(255)", "recruit_id char(36)", "applicable_to_choice char(64)"),
        "interview_schedule": ("schedule_id char(36) primary key", "room_id char(36)", "start_time datetime", "end_time datetime", "already_booked bool", "booked_interview_id char(36)"),
        "interview_review": ("review_id char(36) primary key", "interview_id char(36)", "reviewer_uid char(36)", "review_time datetime", "comments text", "score int", "passed bool"),
        "recruit_interview_settings": ("recruit_id char(36) primary key", "book_start_time datetime", "book_end_time datetime")
    }

    parsed_schema = {
        table: {
            definition.strip().split()[0].replace('`', ''): definition
            for definition in definitions
        }
        for table, definitions in sql_params.items()
    }

    with utils.SQL() as sql:
        db_name = db_config['db']
        for table in sql_tables:
            expected_columns = parsed_schema.get(table, {})
            if not expected_columns:
                logger.warning(f"Table '{table}' is defined in 'sql_tables' but not in 'sql_params'. Skipping.")
                continue

            table_exists_query = "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s"
            if not sql.execute_query(table_exists_query, (db_name, table)):
                create_sql = f"CREATE TABLE `{table}` ({', '.join(expected_columns.values())})"
                sql.execute_update(create_sql)
                logger.info(f"Table '{table}' created.")
                continue

            # --- 表已存在，开始同步其结构 ---
            existing_columns_info = {col['Field']: col for col in sql.execute_query(f"SHOW COLUMNS FROM `{table}`")}
            existing_column_names = set(existing_columns_info.keys())
            expected_column_names = set(expected_columns.keys())

            # 添加缺失字段
            for col_name in expected_column_names - existing_column_names:
                add_sql = f"ALTER TABLE `{table}` ADD COLUMN {expected_columns[col_name]}"
                sql.execute_update(add_sql)
                logger.info(f"Table '{table}': Added column '{col_name}'.")

            # 删除多余字段
            for col_name in existing_column_names - expected_column_names:
                drop_sql = f"ALTER TABLE `{table}` DROP COLUMN `{col_name}`"
                sql.execute_update(drop_sql)
                logger.warning(f"Table '{table}': Removed extra column '{col_name}'.")

            # **【核心修复1】修改字段类型，但不处理主键**
            for col_name in expected_column_names.intersection(existing_column_names):
                full_def = expected_columns[col_name]
                # 使用正则表达式移除 'primary key'，忽略大小写
                def_without_pk = re.sub(r'\s+primary\s+key', '', full_def, flags=re.IGNORECASE)
                modify_sql = f"ALTER TABLE `{table}` MODIFY COLUMN {def_without_pk}"
                sql.execute_update(modify_sql)
            logger.info(f"Table '{table}': Verified and aligned column types and lengths.")

            # **【核心修复2】单独同步主键**
            # 获取代码中预期的主键
            expected_pk = sorted([
                name for name, definition in expected_columns.items()
                if 'primary key' in definition.lower()
            ])
            # 获取数据库中现有的主键
            existing_pk_info = sql.execute_query(f"SHOW KEYS FROM `{table}` WHERE Key_name = 'PRIMARY'")
            existing_pk = sorted([row['Column_name'] for row in existing_pk_info])

            # 如果主键不一致，则更新
            if expected_pk != existing_pk:
                logger.info(f"Table '{table}': Primary key mismatch. Expected: {expected_pk}, Found: {existing_pk}. Updating...")
                # 先删除旧的主键（如果存在）
                if existing_pk:
                    sql.execute_update(f"ALTER TABLE `{table}` DROP PRIMARY KEY")
                # 再添加新的主键（如果需要）
                if expected_pk:
                    pk_columns_str = ', '.join([f"`{col}`" for col in expected_pk])
                    sql.execute_update(f"ALTER TABLE `{table}` ADD PRIMARY KEY ({pk_columns_str})")
                logger.info(f"Table '{table}': Primary key updated successfully.")


    # 状态检查部分保持不变
    status_list = ["未处理", "简历通过", "简历未通过", "等待面试", "面试未通过", "已录取", "未参加面试"]
    with utils.SQL() as sql:
        existing_status = sql.fetch_all('resume_status_names')
        existing_status_ids = [item['status_id'] for item in existing_status] if existing_status else []
        for idx, status in enumerate(status_list):
            if idx not in existing_status_ids:
                sql.insert('resume_status_names', {'status_id': idx, 'status_name': status})
        if existing_status:
            for item in existing_status:
                if item['status_id'] < 0 or item['status_id'] >= len(status_list):
                    sql.delete('resume_status_names', {'status_id': item['status_id']})
                elif item['status_name'] != status_list[item['status_id']]:
                    sql.update('resume_status_names', {'status_name': status_list[item['status_id']]}, {'status_id': item['status_id']})

async def initialize():
    await check_data_base()

# 使用 asyncio.run() 来替代旧的 event loop 管理方式，更简洁健壮
try:
    asyncio.run(initialize())
except RuntimeError:
    # 如果事件循环已在运行（例如在某些环境中），则创建任务
    loop = asyncio.get_event_loop()
    loop.create_task(initialize())


resume_submit_ip_time_history = {}

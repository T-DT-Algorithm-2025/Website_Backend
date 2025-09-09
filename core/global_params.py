import utils
import json
import asyncio
from flask import Flask
import flask_cors
import redis
from datetime import timedelta


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

redis_client = utils.RedisClient(host=database_config['redis']['redis_host'], port=database_config['redis']['redis_port'], db=database_config['redis']['redis_db'], password=database_config['redis']['redis_password'])

mailer = utils.Mailer(mail_config['host'], mail_config['port'],
                    mail_config['user'], mail_config['passwd'])

flask_app = Flask(__name__)
flask_app.debug = False
flask_app.config['SECRET_KEY'] = global_config['secret_key']
flask_app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=global_config.get('login_expire_days', 7))
flask_app.config['MAX_CONTENT_LENGTH'] = global_config.get('max_content_length', 16 * 1024 * 1024)  # Default to 16MB

@flask_app.errorhandler(413)
def request_entity_too_large(error):
    return f'文件太大，请上传小于{flask_app.config["MAX_CONTENT_LENGTH"] // 1024 // 1024}MB的文件', 413

flask_cors.CORS(flask_app)

async def check_data_base():
    sql_tables = ['user', 'userinfo', 'useravatar', 'userpermission', 'recruit', 'userphone', 'resume_submit', 'resume_info', 'resume_review', 'resume_status_names']
    sql_params = {
        "user": ("uid char(20) primary key", "openid_qq char(64)", "openid_wx char(64)", "mail char(255)", "pwd char(64)"),
        "userinfo": ("uid char(20) primary key", "nickname char(64)", "gender char(10)", "realname char(64)", 
                     "student_id char(20)", "department char(64)", "major char(64)", "grade char(10)", "rank char(10)"),
        "useravatar": ("uid char(20) primary key", "avatar_path char(255)"),
        "userpermission": ("uid char(20) primary key", "is_main_leader_admin bool", "is_group_leader_admin bool", "is_member_admin bool", "is_banned bool", "ban_reason char(255)"),
        "userphone": ("uid char(20) primary key", "phone_number char(20)", "is_verified bool", "verification_code char(10)", "code_sent_time datetime"),
        "usermailverify": ("mail char(20) primary key", "verification_code char(10)", "code_sent_time datetime"),
        "recruit": ("recruit_id char(20) primary key", "name char(64)", "start_time datetime", "end_time datetime", "description text", "is_active bool"),
        "resume_submit": ("submit_id char(20) primary key", "uid char(20)", "recruit_id char(20)", "submit_time datetime", "status int"),
        "resume_info": ("submit_id char(20) primary key", "1st_choice char(64)", "2nd_choice char(64)", "self_intro text", "skills text", "projects text", "awards text", "grade_point char(10)", "grade_rank char(10)", "additional_file_path text"),
        "resume_review": ("review_id char(20) primary key", "submit_id char(20)", "reviewer_uid char(20)", "review_time datetime", "comments text", "score int", "passed bool"),
        "resume_status_names": ("status_id int primary key", "status_name char(64)"),
        "resume_user_real_head_img": ("submit_id char(20) primary key", "real_head_img_path char(255)"),
        "interview_info": ("interview_id char(20) primary key", "submit_id char(20)", "interviewee_uid char(20)", "interview_time datetime", "location char(255)", "notes text"),
        "interview_room": ("room_id char(20) primary key", "room_name char(64)","location char(255)", "recruit_id char(20)"),
        "interview_schedule": ("schedule_id char(20) primary key", "room_id char(20)", "start_time datetime", "end_time datetime", "already_booked bool", "booked_interview_id char(20)"),
        "interview_review": ("review_id char(20) primary key", "interview_id char(20)", "reviewer_uid char(20)", "review_time datetime", "comments text", "score int", "passed bool")
    }
    for table in sql_tables:
        with utils.SQL() as sql:
            form = sql.fetch_one('information_schema.TABLES', {'TABLE_NAME': table})
            if not form:
                sql.execute_query(f"CREATE TABLE `{table}` ({', '.join(sql_params[table])})")
                
    #status check
    status_list = ["未处理", "初选通过", "初选未通过", "复试通过", "复试未通过", "录取"]
    with utils.SQL() as sql:
        existing_status = sql.fetch_all('resume_status_names')
        existing_status_names = [item['status_name'] for item in existing_status] if existing_status else []
        for idx, status in enumerate(status_list):
            if status not in existing_status_names:
                sql.execute_query("INSERT INTO `resume_status_names` (status_id, status_name) VALUES (%s, %s)", (idx, status))

async def initialize_mailer():
    try:
        await mailer.connect()
    except Exception as e:
        print(f"邮件服务初始化失败: {e}")
        raise
    
async def initialize():
    await initialize_mailer()
    await check_data_base()

loop = asyncio.get_event_loop()
if loop.is_running():
    loop.create_task(initialize())
else:
    loop.run_until_complete(initialize())

resume_submit_ip_time_history = {}
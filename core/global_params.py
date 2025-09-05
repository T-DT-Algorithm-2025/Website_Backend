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

mailer = utils.Mail(mail_config['host'], mail_config['port'],
                    mail_config['user'], mail_config['passwd'])

flask_app = Flask(__name__)
flask_app.debug = False
flask_app.config['SECRET_KEY'] = global_config['secret_key']
flask_app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=global_config.get('login_expire_days', 7))
flask_cors.CORS(flask_app)

async def check_data_base():
    sql_tables = ['user', 'userinfo', 'useravatar', 'userpermission']
    sql_params = {
        "user": ("uid char(20) primary key", "openid_qq char(64)", "openid_wx char(64)", "mail char(255)", "pwd char(64)"),
        "userinfo": ("uid char(20) primary key", "nickname char(64)", "gender char(10)", "realname char(64)", 
                     "student_id char(20)", "department char(64)", "major char(64)", "grade char(10)", "rank char(10)"),
        "useravatar": ("uid char(20) primary key", "avatar_path char(255)"),
        "userpermission": ("uid char(20) primary key", "is_main_leader_admin bool", "is_group_leader_admin bool", "is_member_admin bool", "is_banned bool", "ban_reason char(255)")
        # "resume": ("submit_id char(20) primary key", "student_id char(20)",
        #            "name char(9)", "department char(20)", "path char(64)", "mail char(255)")
    }
    for table in sql_tables:
        with utils.SQL() as sql:
            form = sql.fetch_one('information_schema.TABLES', {'TABLE_NAME': table})
            if not form:
                sql.execute_query(f"CREATE TABLE `{table}` ({', '.join(sql_params[table])})")

loop = asyncio.get_event_loop()
if loop.is_running():
    loop.create_task(check_data_base())
else:
    loop.run_until_complete(check_data_base())

resume_submit_ip_time_history = {}
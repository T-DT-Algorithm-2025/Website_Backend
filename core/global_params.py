import utils
import json
import asyncio
from flask import Flask
import flask_cors

# Global parameters
database_config = json.load(open('config/database.json'))

global_config = json.load(open('config/config.json'))

mail_config = json.load(open('config/mail.json'))

sql = utils.SQL(database_config['sql_host'], database_config['sql_port'],
                database_config['sql_database_name'], database_config['sql_database_user'], database_config['sql_database_passwd'])

mailer = utils.Mail(mail_config['host'], mail_config['port'],
                    mail_config['user'], mail_config['passwd'])

flask_app = Flask(__name__)
flask_app.debug = False
flask_cors.CORS(flask_app)

async def check_data_base():
    sql_tables = ['user', 'userinfo', 'useravatar']
    sql_params = {
        "user": ("uid char(20) primary key", "openid_qq char(64)", "openid_wx char(64)", "mail char(255)", "pwd char(64)"),
        "userinfo": ("uid char(20) primary key", "nickname char(64)", "gender char(10)", "realname char(64)", 
                     "student_id char(20)", "department char(64)", "major char(64)", "grade char(10)", "rank char(10)"),
        "useravatar": ("uid char(20) primary key", "avatar_path char(255)")
        # "resume": ("submit_id char(20) primary key", "student_id char(20)",
        #            "name char(9)", "department char(20)", "path char(64)", "mail char(255)")
    }
    for table in sql_tables:
        form = await sql.select_one('information_schema.TABLES', 'TABLE_NAME', table)
        if (len(form) == 0):
            await sql.create_table(table, sql_params[table])

loop = asyncio.get_event_loop()
if loop.is_running():
    loop.create_task(check_data_base())
else:
    loop.run_until_complete(check_data_base())

resume_submit_ip_time_history = {}
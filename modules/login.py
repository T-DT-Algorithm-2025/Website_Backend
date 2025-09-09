import os
import time
import math
from datetime import datetime
import aiohttp
import uuid
import logging

from flask import request, jsonify, session, redirect

from core.global_params import flask_app, oauth_config, redis_client, mailer

from utils import SQL

logger = logging.getLogger(__name__)

def safe_redirect(url):
    """Safely redirects to a given URL."""
    if not url:
        return '/'
    if url.startswith('/') and not url.startswith('//'):
        return url
    # 检查是否为同一一级域名
    host_url_father = request.host_url.split('//')[1].split('/')[0].split('.')[-2:]
    url_father = url.split('//')[1].split('/')[0].split('.')[-2:]
    # if host_url_father != url_father:
    #     return '/'
    # 检查协议是否安全
    if request.scheme != 'http' and request.scheme != 'https':
        return '/'
    return url

@flask_app.route('/login/redirect/set', methods=['POST'])
async def on_login_redirect_set():
    session.permanent = True
    session['login_redirect'] = request.json.get('redirect_url', None)
    if not session['login_redirect']:
        return jsonify(success=False, error="未提供重定向URL")
    return jsonify(success=True)

@flask_app.route('/login/bundle/set', methods=['POST'])
async def on_login_bundle_set():
    session.permanent = True
    session['login_bundle'] = request.json.get('bundle_name', None)
    if not session['login_bundle']:
        return jsonify(success=False, error="未提供绑定信息")
    return jsonify(success=True)

async def handle_avatar(uid, avatar_url):
    """Downloads avatar, saves it locally, and updates the database."""
    if not os.path.exists('avatars'):
        os.makedirs('avatars')
    
    avatar_path = f'avatars/{uid}.jpg'
    
    async with aiohttp.ClientSession() as http_session:
        async with http_session.get(avatar_url) as response:
            if response.status == 200:
                with open(avatar_path, 'wb') as f:
                    f.write(await response.read())
                with SQL() as sql:
                    sql.update('useravatar', {'avatar_path': avatar_path}, {'uid': uid})

@flask_app.route('/oauth/qq/callback', methods=['GET'])
async def on_qq_callback():
    code = request.args.get('code')
    state = request.args.get('state')

    async with aiohttp.ClientSession() as http_session:
        # Get access token
        token_url = 'https://graph.qq.com/oauth2.0/token'
        params = {
            'grant_type': 'authorization_code',
            'client_id': oauth_config['qq_app_id'],
            'client_secret': oauth_config['qq_app_key'],
            'code': code,
            'redirect_uri': oauth_config['qq_redirect_uri']
        }
        async with http_session.get(token_url, params=params) as response:
            access_token = (await response.text()).split('&')[0].split('=')[1]

        # Get openid
        openid_url = 'https://graph.qq.com/oauth2.0/me'
        params = {'access_token': access_token}
        async with http_session.get(openid_url, params=params) as response:
            openid = (await response.text()).split('"openid":"')[1].split('"')[0]

        # Get user info
        user_info_url = 'https://graph.qq.com/user/get_user_info'
        params = {
            'access_token': access_token,
            'oauth_consumer_key': oauth_config['qq_app_id'],
            'openid': openid
        }
        async with http_session.get(user_info_url, params=params) as response:
            user_info = await response.json()

    # Check if user exists
    with SQL() as sql:
        user = sql.fetch_one('user', {'openid_qq': openid})
        if 'uid' in session and session['uid'] and 'bundle' in session and session['bundle'] == 'qq':
            session.pop('bundle', None)
            # User is logged in, bind account
            if user and user['uid'] != session['uid']:
                return jsonify(success=False, error="该QQ号已绑定其他账号")
            sql.update('user', {'openid_qq': openid}, {'uid': session['uid']})
            uid = session['uid']
            
        elif not user:
            # Create new user
            uid = str(uuid.uuid4())
            while sql.fetch_one('user', {'uid': uid}):
                uid = str(uuid.uuid4())
            sql.insert('user', {'uid': uid, 'openid_qq': openid})
            sql.insert('userinfo', {'uid': uid, 'nickname': user_info['nickname'], 'gender': user_info['gender']})
            sql.insert('useravatar', {'uid': uid, 'avatar_path': ''})
        else:
            uid = user['uid']

    # Store access_token in Redis
    redis_client.set(f'access_token_qq:{uid}', access_token)

    # Handle avatar
    await handle_avatar(uid, user_info['figureurl_qq'])

    # Store user info in session
    session.permanent = True
    session['uid'] = uid

    # Redirect to the original page
    redirect_url = session.get('login_redirect', '/')
    session.pop('login_redirect', None)

    response = redirect(safe_redirect(redirect_url))
    return response


@flask_app.route('/logout', methods=['POST', 'GET'])
async def on_logout():
    success = False
    if 'uid' in session:
        session.pop('uid', None)
        success = True
        if 'login_redirect' in session:
            session.pop('login_redirect', None)
    response = jsonify(success=True, message="用户已登出")
    if not success:
        response = jsonify(success=False, message="用户未登录")
    return response

@flask_app.route('/mail/verify/send', methods=['POST'])
async def on_mail_verify_send():
    data = request.json
    if not data or 'mail' not in data:
        return jsonify(success=False, error="未提供邮箱地址")

    mail = data['mail']
    verification_code = os.urandom(3).hex()
    
    with SQL() as sql:
        existing = sql.fetch_one('user', {'mail': mail})
        if existing:
            return jsonify(success=False, error="该邮箱已被注册")
        
        last_sent = sql.fetch_one('usermailverify', {'mail': mail})
        if last_sent and last_sent['code_sent_time']:
            elapsed = (datetime.now() - last_sent['code_sent_time']).total_seconds()
            if elapsed < 60:
                return jsonify(success=False, error="请勿频繁发送验证码，60秒后再试")
            
    if 'mail_verify_last_sent' in session:
        elapsed = time.time() - session['mail_verify_last_sent']
        if elapsed < 60:
            return jsonify(success=False, error="请勿频繁发送验证码，60秒后再试")

    try:
        await mailer.send(mail, "验证码 T-DT创新实验室邮件助手", f"同学您好,\n\t您的邮箱验证代码是: {verification_code}\n请在10分钟内使用该验证码完成验证。如非本人操作，请忽略此邮件。\n请勿回复此邮件。\n\n-- T-DT创新实验室", subtype='plain')
    except Exception as e:
        logger.error(f"发送邮件失败: {e}")
        return jsonify(success=False, error="发送邮件失败")
    
    session['mail_verify_last_sent'] = time.time()
    with SQL() as sql:
        existing = sql.fetch_one('usermailverify', {'mail': mail})
        if existing:
            sql.update('usermailverify', {'verification_code': verification_code, 'code_sent_time': datetime.now()}, {'mail': mail})
        else:
            sql.insert('usermailverify', {'mail': mail, 'verification_code': verification_code, 'code_sent_time': datetime.now()})

    return jsonify(success=True, message="验证邮件已发送")


@flask_app.route('/login/mail/register', methods=['POST'])
async def on_mail_register():
    data = request.json
    if not data or 'mail' not in data or 'pwd' not in data or 'verification_code' not in data:
        return jsonify(success=False, error="未提供完整的注册信息")

    mail = data['mail']
    pwd = data['pwd']
    verification_code = data['verification_code']

    with SQL() as sql:
        existing = sql.fetch_one('user', {'mail': mail})
        if existing:
            return jsonify(success=False, error="该邮箱已被注册")
        
        code_entry = sql.fetch_one('usermailverify', {'mail': mail})
        if not code_entry or code_entry['verification_code'] != verification_code:
            return jsonify(success=False, error="验证码错误")
        if (datetime.now() - code_entry['code_sent_time']).total_seconds() > 600:
            return jsonify(success=False, error="验证码已过期，请重新获取")

        uid = str(uuid.uuid4())
        while sql.fetch_one('user', {'uid': uid}):
            uid = str(uuid.uuid4())
        sql.insert('user', {'uid': uid, 'mail': mail, 'pwd': pwd})
        sql.insert('userinfo', {'uid': uid})
        sql.insert('useravatar', {'uid': uid, 'avatar_path': ''})
        sql.delete('usermailverify', {'mail': mail})

    session.permanent = True
    session['uid'] = uid

    redirect_url = session.get('login_redirect', '/')
    session.pop('login_redirect', None)

    response = redirect(safe_redirect(redirect_url))
    return response

@flask_app.route('/login/mail', methods=['POST'])
async def on_mail_login():
    data = request.json
    if not data or 'mail' not in data or 'pwd' not in data:
        return jsonify(success=False, error="未提供完整的登录信息")

    mail = data['mail']
    pwd = data['pwd']

    with SQL() as sql:
        user = sql.fetch_one('user', {'mail': mail})
        if not user or user['pwd'] != pwd:
            return jsonify(success=False, error="邮箱或密码错误")
        uid = user['uid']

    session.permanent = True
    session['uid'] = uid

    redirect_url = session.get('login_redirect', '/')
    session.pop('login_redirect', None)

    response = redirect(safe_redirect(redirect_url))
    return response
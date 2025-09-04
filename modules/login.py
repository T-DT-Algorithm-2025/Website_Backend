import os
import time
import math
from datetime import datetime
import aiohttp
import uuid
import logging

from flask import request, jsonify, session, redirect

from core.global_params import flask_app, oauth_config, redis_client

from utils.login import *
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
    session['login_redirect'] = request.json.get('redirect_url')
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
        if not user:
            # Create new user
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


@flask_app.route('/oauth/weixin/callback', methods=['GET'])
async def on_weixin_callback():
    code = request.args.get('code')
    state = request.args.get('state')

    async with aiohttp.ClientSession() as http_session:
        # Get access token
        token_url = 'https://api.weixin.qq.com/sns/oauth2/access_token'
        params = {
            'appid': oauth_config['wx_app_id'],
            'secret': oauth_config['wx_app_key'],
            'code': code,
            'grant_type': 'authorization_code'
        }
        async with http_session.get(token_url, params=params) as response:
            data = await response.json()
            access_token = data['access_token']
            openid = data['openid']

        # Get user info
        user_info_url = 'https://api.weixin.qq.com/sns/userinfo'
        params = {
            'access_token': access_token,
            'openid': openid,
            'lang': 'zh_CN'
        }
        async with http_session.get(user_info_url, params=params) as response:
            user_info = await response.json(content_type='text/plain; charset=utf-8')

    # Check if user exists
    with SQL() as sql:
        user = sql.fetch_one('user', {'openid_wx': openid})
        if not user:
            # Create new user
            uid = str(uuid.uuid4())
            sql.insert('user', {'uid': uid, 'openid_wx': openid})
            sql.insert('userinfo', {'uid': uid, 'nickname': user_info['nickname'], 'gender': user_info.get('sex')})
            sql.insert('useravatar', {'uid': uid, 'avatar_path': ''})
        else:
            uid = user['uid']

    # Store access_token in Redis
    redis_client.set(f'access_token_wx:{uid}', access_token)

    # Handle avatar
    await handle_avatar(uid, user_info['headimgurl'])

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

@flask_app.route('/login/mail', methods=['POST'])
async def on_mail_login():
    pass
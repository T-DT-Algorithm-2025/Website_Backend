import os
import time
import math
from datetime import datetime
import aiohttp
import uuid

from flask import request, jsonify, session, redirect

from core.global_params import flask_app, oauth_config, sql, redis_pool

@flask_app.route('/login/redirect/set', methods=['POST'])
async def on_login_redirect_set():
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
                await sql.update_one('useravatar', 'uid', uid, 'avatar_path', f"'{avatar_path}'")

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
    user = await sql.select_one('user', 'openid_qq', openid)
    if not user:
        # Create new user
        uid = str(uuid.uuid4())
        await sql.insert_one('user', (uid, openid, None, None, None))
        await sql.insert_one('userinfo', (uid, user_info['nickname'], user_info['gender'], None, None, None, None, None, None))
        await sql.insert_one('useravatar', (uid, ''))
    else:
        uid = user[0]['uid']

    # Store access_token in Redis
    redis_pool.set(f'access_token_qq:{uid}', access_token)

    # Handle avatar
    await handle_avatar(uid, user_info['figureurl_qq_1'])

    # Store user info in session
    session['uid'] = uid

    # Redirect to the original page
    redirect_url = session.get('login_redirect', '/')
    session.pop('login_redirect', None)
    return redirect(redirect_url)


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
    user = await sql.select_one('user', 'openid_wx', openid)
    if not user:
        # Create new user
        uid = str(uuid.uuid4())
        await sql.insert_one('user', (uid, None, openid, None, None))
        await sql.insert_one('userinfo', (uid, user_info['nickname'], user_info.get('sex'), None, None, None, None, None, None))
        await sql.insert_one('useravatar', (uid, ''))
    else:
        uid = user[0]['uid']

    # Store access_token in Redis
    redis_pool.set(f'access_token_wx:{uid}', access_token)

    # Handle avatar
    await handle_avatar(uid, user_info['headimgurl'])

    # Store user info in session
    session['uid'] = uid

    # Redirect to the original page
    redirect_url = session.get('login_redirect', '/')
    session.pop('login_redirect', None)
    return redirect(redirect_url)

@flask_app.route('/logout', methods=['POST'])
async def on_logout():
    session.pop('uid', None)
    session.pop('login_redirect', None)
    return jsonify(success=True, message="用户已登出")

@flask_app.route('/login/mail', methods=['POST'])
async def on_mail_login():
    pass
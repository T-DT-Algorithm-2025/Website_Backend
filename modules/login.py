import os
import time
import math
from datetime import datetime

from flask import request, jsonify

from core.global_params import flask_app

@flask_app.route('/login/redirect/set', methods=['POST'])
async def on_login_redirect_set():
    pass

@flask_app.route('/oauth/qq/callback', methods=['POST'])
async def on_qq_callback():
    pass

@flask_app.route('/oauth/weixin/callback', methods=['POST'])
async def on_weixin_callback():
    pass

@flask_app.route('/login/mail', methods=['POST'])
async def on_mail_login():
    pass
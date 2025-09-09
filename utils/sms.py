# -*- coding: UTF-8 -*-

import hashlib
import logging
import requests
from typing import Tuple, Optional

# API返回状态码说明
STATUS_CODES = {
    0: "短信发送成功",
    30: "密码错误",
    40: "账号不存在",
    41: "余额不足",
    42: "账户已过期",
    43: "IP地址限制",
    50: "内容含有敏感词",
    51: "手机号码不正确",
}

class SmsBao:
    """
    短信宝 (smsbao.com) API 封装
    文档: https://www.smsbao.com/openapi/213.html
    """
    API_BASE_URL = "http://api.smsbao.com"

    def __init__(self, username: str, password: str):
        """
        初始化客户端

        Args:
            username (str): 短信宝平台的用户名
            password (str): 短信宝平台的密码 (注意: 请传入原始密码，该类会自动进行MD5加密)
        """
        if not username or not password:
            raise ValueError("用户名和密码不能为空")
        self.username = username
        # 根据API文档，密码需要进行MD5加密
        self.password_md5 = self._md5_encode(password)
        self.session = requests.Session()

    @staticmethod
    def _md5_encode(text: str) -> str:
        """对字符串进行MD5加密"""
        md5 = hashlib.md5()
        md5.update(text.encode('utf-8'))
        return md5.hexdigest()

    def _make_request(self, endpoint: str, params: Optional[dict] = None) -> requests.Response:
        """
        发起网络请求的核心方法

        Args:
            endpoint (str): API的端点 (例如: /sms)
            params (dict, optional): 请求参数. Defaults to None.

        Returns:
            requests.Response: 返回的响应对象

        Raises:
            requests.exceptions.RequestException: 当网络请求失败时抛出
        """
        url = f"{self.API_BASE_URL}{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()  # 如果HTTP状态码不是200, 则抛出异常
            return response
        except requests.exceptions.RequestException as e:
            print(f"网络请求失败: {e}")
            raise

    def send(self, mobile: str, content: str) -> Tuple[bool, str]:
        """
        发送短信

        Args:
            mobile (str): 接收短信的手机号码
            content (str): 短信内容，需要经过短信宝平台审核

        Returns:
            Tuple[bool, str]: 一个元组，第一个元素表示是否成功 (True/False)，
                              第二个元素是API返回的消息。
        """
        params = {
            'u': self.username,
            'p': self.password_md5,
            'm': mobile,
            'c': content,
        }
        try:
            response = self._make_request("/sms", params=params)
            status_code = int(response.text)
            message = STATUS_CODES.get(status_code, f"未知错误，状态码: {status_code}")
            return status_code == 0, message
        except (requests.exceptions.RequestException, ValueError) as e:
            # ValueError 可能在 int(response.text) 时发生
            return False, f"请求处理失败: {e}"

    def query_balance(self) -> Tuple[bool, str]:
        """
        查询账户余额

        Returns:
            Tuple[bool, str]: 一个元组，第一个元素表示是否成功 (True/False)，
                              第二个元素是API返回的消息。
                              如果成功，消息格式为 "查询成功, 用户名: xxx, 剩余短信: xxx条"。
        """
        params = {
            'u': self.username,
            'p': self.password_md5,
        }
        try:
            response = self._make_request("/query", params=params)
            response_text = response.text.strip()
            
            parts = response_text.split('\n')
            
            # 检查响应是否为空或无效
            if not parts:
                return False, f"API返回了无效的空响应"

            # 尝试解析第一部分作为状态码
            try:
                status_code = int(parts[0])
            except ValueError:
                return False, f"无法解析API响应中的状态码: {response_text}"

            # 如果状态码为 0 (成功)
            if status_code == 0:
                if len(parts) >= 3:  # 标准格式: 0\n用户名\n剩余条数
                    user, balance = parts[1], parts[2]
                    message = f"查询成功, 用户名: {user}, 剩余短信: {balance}条"
                    return True, message
                elif len(parts) == 2:  # 兼容格式: 0\n剩余信息
                    balance_info = parts[1]
                    left = balance_info.split(',')[-1]  # 处理中文冒号
                    message = f"查询成功, 剩余短信: {left.strip()}"
                    return True, message
                else:
                    return False, f"成功的响应格式不符合预期: {response_text}"
            
            # 如果状态码不为 0 (失败)
            else:
                message = STATUS_CODES.get(status_code, f"未知错误，状态码: {status_code}")
                return False, message

        except requests.exceptions.RequestException as e:
            return False, f"网络请求失败: {e}"
     
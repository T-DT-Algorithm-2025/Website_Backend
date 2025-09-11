import asyncio
import aiosmtplib
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from typing import List, Union
import logging

logger = logging.getLogger(__name__)

class Mailer:
    """
    一个作为异步上下文管理器的邮件发送类。
    它为每一次 `async with` 代码块建立一个临时的连接，确保所有操作都在同一个事件循环中完成。
    这种模式非常适合在Web框架的视图函数中使用。
    """
    def __init__(self, host: str, port: int, user: str, password: str, use_tls: bool = True):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.use_tls = use_tls
        self.server: aiosmtplib.SMTP = None

    async def __aenter__(self):
        """进入 `async with` 块时调用，负责连接和登录。"""
        try:
            self.server = aiosmtplib.SMTP(hostname=self.host, port=self.port, use_tls=self.use_tls)
            await self.server.connect()
            await self.server.login(self.user, self.password)
            logger.info("SMTP 客户端成功连接并登录。")
            return self  # 返回实例自身，以便在 `with` 块中使用
        except aiosmtplib.SMTPException as e:
            self.server = None
            logger.error(f"SMTP连接失败: {e}")
            raise ConnectionError(f"SMTP连接失败: {e}")

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出 `async with` 块时调用，负责断开连接。"""
        if self.server and self.server.is_connected:
            await self.server.quit()
            logger.info("SMTP 客户端连接已关闭。")
        self.server = None

    async def send(self, targets: Union[str, List[str]], subject: str, content: str, subtype: str = 'plain'):
        """发送简单的文本或HTML邮件。"""
        if not self.server or not self.server.is_connected:
            raise ConnectionError("SMTP 未连接。请在 'async with' 语句块中使用 send 方法。")
        
        msg = MIMEText(content, subtype, 'utf-8')
        msg['Subject'] = subject
        await self.send_mime(targets, msg)

    async def send_mime(self, targets: Union[str, List[str]], msg: MIMEBase):
        """发送一个预先构建好的 MIME 对象。"""
        if not self.server or not self.server.is_connected:
            raise ConnectionError("SMTP 未连接。请在 'async with' 语句块中使用 send 方法。")
            
        if isinstance(targets, str):
            recipients = [targets]
        else:
            recipients = targets

        msg['From'] = self.user
        msg['To'] = ", ".join(recipients)
        
        await self.server.send_message(msg)
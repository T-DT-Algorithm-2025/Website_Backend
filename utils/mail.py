import asyncio
import aiosmtplib
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from typing import List, Union

class Mailer:
    """
    一个可持久化的异步邮件发送实例。
    它管理一个长期连接，并能在连接断开时自动重连。
    适合在应用程序的整个生命周期中作为单例或共享实例使用。
    """
    def __init__(self, host: str, port: int, user: str, password: str, use_tls: bool = True):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.use_tls = use_tls
        
        self.server: aiosmtplib.SMTP = None
        self._lock = asyncio.Lock()  # 锁，用于防止在重连时发生竞态条件

    async def connect(self):
        """
        显式连接到SMTP服务器。
        应用启动时应调用此方法。
        """
        async with self._lock:
            if not self.is_connected:
                try:
                    self.server = aiosmtplib.SMTP(hostname=self.host, port=self.port, use_tls=self.use_tls)
                    await self.server.connect()
                    await self.server.login(self.user, self.password)
                    print("SMTP 客户端成功连接并登录。")
                except aiosmtplib.SMTPException as e:
                    self.server = None # 连接失败，重置server
                    raise ConnectionError(f"SMTP连接失败: {e}")

    async def close(self):
        """
        关闭与SMTP服务器的连接。
        应用关闭前应调用此方法。
        """
        async with self._lock:
            if self.server and self.is_connected:
                await self.server.quit()
                self.server = None
                print("SMTP 客户端连接已关闭。")

    @property
    def is_connected(self) -> bool:
        """检查当前是否已连接"""
        return self.server is not None and self.server.is_connected

    async def _ensure_connected(self):
        """内部方法，确保在操作前已连接。如果未连接，则尝试连接。"""
        if not self.is_connected:
            print("连接已断开，正在尝试重新连接...")
            await self.connect()

    async def send(self, targets: Union[str, List[str]], subject: str, content: str, subtype: str = 'plain'):
        """
        发送简单的文本或HTML邮件。
        """
        msg = MIMEText(content, subtype, 'utf-8')
        msg['Subject'] = subject
        await self.send_mime(targets, msg)

    async def send_mime(self, targets: Union[str, List[str]], msg: MIMEBase):
        """
        发送一个预先构建好的 MIME 对象，包含自动重连逻辑。
        """
        if isinstance(targets, str):
            recipients = [targets]
        else:
            recipients = targets

        msg['From'] = self.user
        msg['To'] = ", ".join(recipients)
        
        async with self._lock: # 确保发送操作的原子性
            try:
                await self._ensure_connected() # 确保已连接
                await self.server.send_message(msg)
            except aiosmtplib.SMTPException as e:
                # 如果发送失败，很可能是连接问题，尝试重连并重试一次
                print(f"发送失败 ({e})，将尝试重连并重试一次...")
                await self.connect() # 强制重连
                await self.server.send_message(msg) # 重试
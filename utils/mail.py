import smtplib
from email.mime.text import MIMEText


class Mail(object):
    def __init__(self, host, port, user, password):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.server = smtplib.SMTP_SSL(host, port)
        self.server.connect(host, port)
        self.server.login(self.user, self.password)
     
    def check_target(self, target):
        if (target.find('@') == -1):
            return False
        if (target.find('.') == -1):
            return False
        return True

    async def send(self, target, title, content):
        self.server.connect(self.host, self.port)
        self.server.helo()
        self.server.login(self.user, self.password)
        msg = MIMEText(content, 'plain', 'utf-8')
        # 发件人昵称和地址
        msg['From'] = self.user
        # 收件人昵称和地址
        msg['To'] = str(target)
        # 邮件主题
        msg['Subject'] = str(title)
        self.server.sendmail(self.user, [str(target)], msg.as_string())

    async def send_mime(self, target, content):
        self.server.connect(self.host, self.port)
        self.server.helo()
        self.server.login(self.user, self.password)
        msg = content
        self.server.sendmail(self.user, [str(target)], msg.as_string())

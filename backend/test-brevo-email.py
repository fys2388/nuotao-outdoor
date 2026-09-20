#!/usr/bin/env python3
import os
import sys

# 显式加载 .env
env_path = '/opt/nuotao/backend/.env'
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

smtp_host = os.getenv('SMTP_HOST')
smtp_port = int(os.getenv('SMTP_PORT', 587))
smtp_user = os.getenv('SMTP_USERNAME')
smtp_pass = os.getenv('SMTP_PASSWORD')
from_email = os.getenv('FROM_EMAIL', 'noreply@nuotaooutdoor.com')
to_email = 'fys2388@gmail.com'

print(f'SMTP Host: {smtp_host}')
print(f'SMTP Port: {smtp_port}')
print(f'SMTP User: {smtp_user}')
print(f'From: {from_email}')
print(f'To: {to_email}')
print()

msg = MIMEMultipart('alternative')
msg['Subject'] = 'Nuotao AI OS - SMTP 配置成功测试'
msg['From'] = f'Nuotao Outdoor <{from_email}>'
msg['To'] = to_email

html_content = """
<html>
<body style="font-family: Arial, sans-serif; padding: 20px;">
  <div style="background: #27ae60; color: white; padding: 20px; text-align: center; border-radius: 5px;">
    <h1>SMTP 配置成功！</h1>
  </div>
  <div style="padding: 20px; background: #f9f9f9;">
    <p>你好 Joran，</p>
    <p>这是一封来自 Nuotao Outdoor AI OS 的测试邮件，通过 Brevo SMTP 发送。</p>
    <p><strong>配置信息：</strong></p>
    <ul>
      <li>SMTP 服务商: Brevo (原 Sendinblue)</li>
      <li>免费额度: 300 封/天</li>
      <li>发件人: noreply@nuotaooutdoor.com</li>
    </ul>
    <p>如果你收到这封邮件，说明 SMTP 配置已成功，订单确认和发货通知将可以真实发送。</p>
  </div>
  <div style="text-align: center; padding: 20px; color: #999; font-size: 12px;">
    <p>(c) 2026 Nuotao Outdoor. All rights reserved.</p>
  </div>
</body>
</html>
"""

msg.attach(MIMEText(html_content, 'html'))

try:
    server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
    server.starttls()
    server.login(smtp_user, smtp_pass)
    server.sendmail(from_email, to_email, msg.as_string())
    server.quit()
    print('✅ 邮件发送成功！请检查 fys2388@gmail.com 收件箱')
except Exception as e:
    print(f'❌ 邮件发送失败: {e}')
    sys.exit(1)

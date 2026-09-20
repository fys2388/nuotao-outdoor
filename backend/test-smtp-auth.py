#!/usr/bin/env python3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

smtp_host = 'smtp-relay.brevo.com'
smtp_port = 587
smtp_key = 'xsmtpsib-37c4ce6ebce648e87df9516995a5738fc96718422fb31d504af5983966eaf115-03TB3w'
from_email = 'noreply@nuotaooutdoor.com'
to_email = 'fys2388@gmail.com'

# 测试方式1: 使用生成的 login
print("=== 测试方式1: 使用生成的 login b7a6aa001@smtp-brevo.com ===")
try:
    server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login('b7a6aa001@smtp-brevo.com', smtp_key)
    
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Nuotao AI OS - SMTP 测试 (方式1)'
    msg['From'] = f'Nuotao Outdoor <{from_email}>'
    msg['To'] = to_email
    msg.attach(MIMEText('<h1>测试邮件</h1><p>方式1: 使用生成的 login</p>', 'html'))
    server.sendmail(from_email, to_email, msg.as_string())
    server.quit()
    print("✅ 方式1 成功！")
except Exception as e:
    print(f"❌ 方式1 失败: {e}")

print()

# 测试方式2: 使用登录邮箱
print("=== 测试方式2: 使用登录邮箱 fys2388@gmail.com ===")
try:
    server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login('fys2388@gmail.com', smtp_key)
    
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Nuotao AI OS - SMTP 测试 (方式2)'
    msg['From'] = f'Nuotao Outdoor <{from_email}>'
    msg['To'] = to_email
    msg.attach(MIMEText('<h1>测试邮件</h1><p>方式2: 使用登录邮箱</p>', 'html'))
    server.sendmail(from_email, to_email, msg.as_string())
    server.quit()
    print("✅ 方式2 成功！")
except Exception as e:
    print(f"❌ 方式2 失败: {e}")

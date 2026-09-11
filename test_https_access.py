import ssl
import urllib.request

# 创建不验证证书的SSL上下文
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# 测试HTTPS访问
try:
    req = urllib.request.Request('https://admin.nuotaoutdoor.com/api/v1/healthz')
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        print(f'HTTP状态码: {resp.status}')
        print(f'响应内容: {resp.read().decode()}')
        print('HTTPS访问正常！自签名证书工作正常')
except Exception as e:
    print(f'HTTPS访问失败: {e}')

# 测试首页
try:
    req = urllib.request.Request('https://admin.nuotaoutdoor.com/')
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        content = resp.read().decode()
        print(f'\n首页HTTP状态码: {resp.status}')
        title_start = content.find('<title>')
        title_end = content.find('</title>')
        if title_start >= 0 and title_end >= 0:
            print(f'首页标题: {content[title_start+7:title_end]}')
        else:
            print('首页无标题')
except Exception as e:
    print(f'首页访问失败: {e}')

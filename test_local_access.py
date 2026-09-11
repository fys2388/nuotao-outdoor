import requests
import urllib3
urllib3.disable_warnings()

# 测试本地通过域名访问（本地hosts已配置）
try:
    r = requests.get('https://admin.nuotaoutdoor.com/', 
                     verify=False, 
                     proxies={'http': None, 'https': None}, 
                     timeout=10)
    print(f'Status: {r.status_code}')
    if '<title>' in r.text:
        title = r.text[r.text.find('<title>')+7:r.text.find('</title>')]
        print(f'Title: {title}')
    print('访问成功！')
except Exception as e:
    print(f'访问失败: {e}')

# 测试API健康检查
try:
    r = requests.get('https://admin.nuotaoutdoor.com/api/v1/healthz', 
                     verify=False, 
                     proxies={'http': None, 'https': None}, 
                     timeout=10)
    print(f'\nAPI Status: {r.status_code}')
    print(f'API Response: {r.text}')
except Exception as e:
    print(f'\nAPI访问失败: {e}')

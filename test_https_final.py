import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 测试直连服务器（hosts配置）
try:
    r = requests.get('https://admin.nuotaooutdoor.com/', verify=False, timeout=10, proxies={'http': None, 'https': None})
    print(f'直连服务器状态码: {r.status_code}')
    title_start = r.text.find('<title>')
    if title_start >= 0:
        title_end = r.text.find('</title>', title_start)
        print(f'标题: {r.text[title_start+7:title_end]}')
    else:
        print('无标题')
except Exception as e:
    print(f'直连服务器失败: {e}')

# 测试API健康检查
try:
    r = requests.get('https://admin.nuotaooutdoor.com/api/v1/healthz', verify=False, timeout=10, proxies={'http': None, 'https': None})
    print(f'API健康检查: {r.status_code} - {r.text}')
except Exception as e:
    print(f'API健康检查失败: {e}')

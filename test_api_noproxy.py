import requests
import os

# 禁用代理
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''

proxies = {'http': None, 'https': None}

# 测试API健康检查
try:
    r = requests.get('https://admin.nuotaooutdoor.com/api/v1/healthz', timeout=10, proxies=proxies)
    print(f'健康检查: {r.status_code} - {r.text}')
except Exception as e:
    print(f'健康检查失败: {e}')

# 测试agent-suggestions API
try:
    r = requests.get('https://admin.nuotaooutdoor.com/api/v1/agent-suggestions?status=pending_approval&limit=1', timeout=10, proxies=proxies)
    print(f'agent-suggestions: {r.status_code} - {r.text[:200]}')
except Exception as e:
    print(f'agent-suggestions失败: {e}')

# 测试dashboard/summary API
try:
    r = requests.get('https://admin.nuotaooutdoor.com/api/v1/dashboard/summary', timeout=10, proxies=proxies)
    print(f'dashboard/summary: {r.status_code} - {r.text[:200]}')
except Exception as e:
    print(f'dashboard/summary失败: {e}')

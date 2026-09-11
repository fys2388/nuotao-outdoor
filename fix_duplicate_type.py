import os

file_path = r"E:\AI\nuotao-ai-os\frontend\src\pages\B2BAgents.tsx"

# 读取文件（保持原始换行符）
with open(file_path, 'rb') as f:
    content = f.read()

# 检测换行符
if b'\r\n' in content:
    newline = '\r\n'
    print("检测到CRLF换行符")
else:
    newline = '\n'
    print("检测到LF换行符")

# 解码为字符串
content_str = content.decode('utf-8')

# 修复重复的type属性
old_text = '<Button type="link" size="small" type="primary" icon={<CheckCircleOutlined />}>通过</Button>'
new_text = '<Button type="primary" size="small" icon={<CheckCircleOutlined />}>通过</Button>'

if old_text in content_str:
    content_str = content_str.replace(old_text, new_text)
    print("已修复重复的type属性")
else:
    print("未找到需要修复的文本")

# 写回文件（保持原始换行符）
with open(file_path, 'wb') as f:
    f.write(content_str.encode('utf-8'))

print("文件已保存")

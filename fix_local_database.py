"""修改本地database.py，添加ssl=False到connect_args中"""

file_path = r"E:\AI\nuotao-ai-os\backend\app\core\database.py"

# 读取文件（保持原始换行）
with open(file_path, 'rb') as f:
    content = f.read()

# 检测换行符
if b'\r\n' in content:
    newline = b'\r\n'
    print("检测到CRLF换行")
else:
    newline = b'\n'
    print("检测到LF换行")

# 解码为字符串
text = content.decode('utf-8')

# 替换connect_args
old = '"connect_args": {"timeout": 5}'
new = '"connect_args": {"timeout": 5, "ssl": False}'

if old in text:
    text = text.replace(old, new)
    print("已修改connect_args，添加ssl=False")
else:
    print("未找到旧的connect_args")
    # 尝试其他格式
    import re
    text = re.sub(
        r'"connect_args":\s*\{([^}]+)\}',
        r'"connect_args": {\1, "ssl": False}',
        text
    )
    print("已用正则表达式修改")

# 写回文件（保持原始换行）
with open(file_path, 'wb') as f:
    f.write(text.encode('utf-8'))

print("修改完成")

# 验证修改结果
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()
    if '"ssl": False' in content:
        print("验证成功：ssl=False已添加")
    else:
        print("验证失败：ssl=False未找到")

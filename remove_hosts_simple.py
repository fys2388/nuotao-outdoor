import os
import sys

def remove_hosts_entry():
    hosts_path = r"C:\Windows\System32\drivers\etc\hosts"
    
    # 读取文件
    with open(hosts_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 移除admin记录
    new_lines = []
    removed = False
    for line in lines:
        if 'admin.nuotaooutdoor.com' in line:
            removed = True
            print(f"已移除: {line.strip()}")
            continue
        new_lines.append(line)
    
    # 写回文件
    with open(hosts_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    if removed:
        print("hosts文件已更新")
    else:
        print("未找到admin记录")
    
    # 刷新DNS缓存
    os.system('ipconfig /flushdns')
    print("DNS缓存已刷新")

if __name__ == '__main__':
    remove_hosts_entry()

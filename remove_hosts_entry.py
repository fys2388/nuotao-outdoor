import os
import sys
import ctypes

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def remove_hosts_entry():
    hosts_path = r"C:\Windows\System32\drivers\etc\hosts"
    
    # 读取当前内容
    with open(hosts_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 过滤掉admin.nuotaoutdoor.com相关行
    new_lines = []
    removed = False
    for line in lines:
        if 'admin.nuotaoutdoor.com' in line.lower():
            removed = True
            print(f"移除: {line.strip()}")
        else:
            new_lines.append(line)
    
    if not removed:
        print("未找到admin.nuotaoutdoor.com记录")
        return
    
    # 写回
    with open(hosts_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print("hosts文件已更新")
    
    # 刷新DNS缓存
    os.system('ipconfig /flushdns')
    print("DNS缓存已刷新")

if __name__ == '__main__':
    if is_admin():
        remove_hosts_entry()
    else:
        # 重新以管理员权限运行
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)

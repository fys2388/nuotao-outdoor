import socket
import time

host = "95.217.218.178"

print(f"测试服务器 {host} 的连通性...")

# 测试ping（ICMP）
print("\n测试ping...")
import subprocess
try:
    result = subprocess.run(['ping', '-n', '3', host], capture_output=True, text=True, timeout=10)
    print(result.stdout)
except Exception as e:
    print(f"ping失败: {e}")

# 测试常见端口
print("\n测试端口连通性...")
ports = [22, 80, 443, 8000]
for port in ports:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        if result == 0:
            print(f"端口 {port}: 开放")
            # 获取banner
            try:
                banner = sock.recv(1024).decode().strip()
                print(f"  Banner: {banner}")
            except:
                pass
        else:
            print(f"端口 {port}: 关闭或不可达 (error: {result})")
        sock.close()
    except Exception as e:
        print(f"端口 {port}: 测试失败 - {e}")

# 多次测试22端口
print("\n多次测试22端口（每5秒一次，共5次）...")
for i in range(5):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, 22))
        if result == 0:
            print(f"第{i+1}次: 端口22开放")
            try:
                banner = sock.recv(1024).decode().strip()
                print(f"  Banner: {banner}")
            except:
                pass
            sock.close()
            break
        else:
            print(f"第{i+1}次: 端口22不可达 (error: {result})")
        sock.close()
    except Exception as e:
        print(f"第{i+1}次: 测试失败 - {e}")
    time.sleep(5)

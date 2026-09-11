"""单次监控测试脚本（不进入循环）"""
import sys
sys.path.insert(0, "E:/AI/nuotao-ai-os/scripts")

from monitor_service import (
    check_system_resources,
    check_service_health,
    save_metrics,
    print_status,
    load_alert_history,
)

print("=" * 60)
print("Nuotao AI OS - 单次监控测试")
print("=" * 60)

load_alert_history()

print("\n[1/3] 检查系统资源...")
metrics = check_system_resources()
print(f"  CPU: {metrics['cpu']['percent']}%")
print(f"  内存: {metrics['memory']['percent']}% ({metrics['memory']['used_gb']}/{metrics['memory']['total_gb']} GB)")
print(f"  磁盘: {metrics['disk']['percent']}% ({metrics['disk']['used_gb']}/{metrics['disk']['total_gb']} GB)")

print("\n[2/3] 检查服务健康状态...")
services = check_service_health()
for name, status in services.items():
    state = status.get("status", "unknown")
    print(f"  {name}: {state}")

print("\n[3/3] 保存监控指标...")
save_metrics(metrics, services)
print("  ✅ 指标已保存")

print("\n" + "=" * 60)
print("监控测试完成！")
print("=" * 60)
print_status(metrics, services)

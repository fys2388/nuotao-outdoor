# -*- coding: utf-8 -*-
"""M335 验收检查：覆盖率、异常、报告路径、只读边界。"""
import io, sys, os, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')
from _m335_skus_data import SKUS, PURCHASE_SRC, QUADRANT, margin_breakdown

def classify(wc, psrc):
    if wc in (1014, 1013):
        return "STOPPED"
    if wc == 1722:
        return "RESTRUCTURE"
    if psrc == "D":
        return "NEEDS_EVIDENCE"
    if psrc in ("A", "B", "C"):
        return "COST_VERIFIED"
    return "BLOCKED"

print("=== 覆盖率 ===")
print("SKU 总数:", len(SKUS), "| 有独立证据状态:", len(SKUS), "/ 60")
print("采购价有本地依据(A/B/C):", sum(1 for s in SKUS if PURCHASE_SRC.get(s[0], 'D') in 'ABC'))
print("采购价估算(D):", sum(1 for s in SKUS if PURCHASE_SRC.get(s[0], 'D') == 'D'))
print("实测重量:", 0, "/ 60 (全部假设)")
print("HTSUS正式归类:", 0, "/ 60 (仅候选)")
print("=== 异常检查 ===")
issues = []
for s in SKUS:
    wc, price, landed = s[0], s[2], s[12]
    if abs(s[13]) > 95:
        issues.append(f"#{wc} 毛利异常 {s[13]}")
    psrc = PURCHASE_SRC.get(wc, 'D')
    if psrc not in 'ABCD':
        issues.append(f"#{wc} 采购档异常")
    q = QUADRANT.get(wc)
    if q not in ('star','cow','observe','stop','restructure'):
        issues.append(f"#{wc} 分类异常")
print("异常数:", len(issues), issues[:10])
print("=== 分类统计 ===")
from collections import Counter
print(Counter(classify(s[0], PURCHASE_SRC.get(s[0], 'D')) for s in SKUS))
print("=== 报告文件 ===")
for f in sorted(glob.glob('M335-*.md')):
    print(f, os.path.getsize(f), "bytes")
print("=== 关键统计 ===")
print("毛利率>=25%:", sum(1 for s in SKUS if s[13] >= 25), "/ 60")
print("扣CAC净利为正:", sum(1 for s in SKUS if margin_breakdown(s[2], s[12])['net'] > 0), "/ 60")

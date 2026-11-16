# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')
from _m335_skus_data import *
pos = []
for s in SKUS:
    wc, price, landed = s[0], s[2], s[12]
    mb = margin_breakdown(price, landed)
    if mb['net'] > 0:
        pos.append((wc, s[1], mb['gross_margin'], mb['net_pct']))
print('net positive count:', len(pos))
for p in pos:
    print(p)
n25 = sum(1 for s in SKUS if s[13] >= 25)
print('margin>=25 count:', n25)

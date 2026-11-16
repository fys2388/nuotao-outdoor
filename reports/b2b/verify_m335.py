# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')
from _m335_skus_data import *

print('SKU count:', len(SKUS))
print('purchase_src counts:', {k: sum(1 for s in SKUS if PURCHASE_SRC.get(s[0], 'D') == k) for k in 'ABCD'})
print('quadrant counts:', {k: sum(1 for s in SKUS if QUADRANT.get(s[0]) == k) for k in ['star','cow','observe','stop','restructure']})
bad = 0
for s in SKUS:
    wc, price, landed, m1 = s[0], s[2], s[12], s[13]
    mb = margin_breakdown(price, landed)
    if abs(mb['gross_margin_pct'] - m1) > 0.6:
        bad += 1
        print('MISMATCH', wc, 'calc', mb['gross_margin_pct'], 'vs M3331', m1)
print('margin mismatch count:', bad)
print('sample 968:', margin_breakdown(29.99, 12.80))
print('sample 1724:', margin_breakdown(119.99, 100.67))

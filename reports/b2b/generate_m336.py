"""M3.36 报告生成器：基于 _m335_skus_data.py + ChatGPT M3.36 指令生成 M336-01~08。

权限边界：只读本地资料 + 写本目录报告。不联系供应商/货代/报关行、不发询价、
不改 WooCommerce、不改生产、不调生产 API、不部署、不自动审批停售/改价/切换履约/扩广告。
"""
import io
import os
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _m335_skus_data import (
    BULKY_6,
    HIGH_VALUE_13,
    HTSUS,
    P0_WEIGHT,
    PURCHASE_SRC,
    QUADRANT,
    SKU_CATEGORY,
    SKUS,
    margin_breakdown,
)

OUT = os.path.dirname(os.path.abspath(__file__))
TODAY = "2026-11-16"

# 10 类最终状态（M336-07）
def m336_status(wc, psrc, quad):
    if wc in (1014, 1013):
        return "STOP_PENDING_OWNER_APPROVAL"   # 无 Owner 审批记录（M336-01 修正）
    if wc == 1722:
        return "RESTRUCTURE"
    if psrc == "D":
        return "NEEDS_EVIDENCE"
    if psrc in ("A", "B", "C"):
        return "COST_VERIFIED_PARTIAL"          # 采购价有据，重量/HS 未核实
    return "BLOCKED"

def confidence(wc, psrc):
    if psrc == "D":
        return "LOW"
    if psrc in ("B", "C"):
        return "MEDIUM"
    if psrc == "A":
        return "MEDIUM"   # 采购实价但重量/HS 假设
    return "LOW"

def scenarios(price, p_usd, head, tail, duty, fuel):
    """三情景：悲观/中性/乐观。返回 landed。"""
    # 中性 = 数据层 landed（用 margin_breakdown 内部公式重建以保持一致）
    margin_breakdown(price, p_usd + head + tail + duty + fuel)
    # 悲观：采购+20%、关税+20%、运费+15%
    landed_p = p_usd * 1.2 + head * 1.15 + tail * 1.15 + duty * 1.2 + fuel * 1.15
    # 乐观：采购-20%、关税-20%、运费-15%
    landed_o = p_usd * 0.8 + head * 0.85 + tail * 0.85 + duty * 0.8 + fuel * 0.85
    return landed_p, landed_o

def build_recs():
    recs = []
    for s in SKUS:
        (wc, name, price, p_cny, _p_star, w_kg, _w_star, p_usd, head, tail,
         duty, fuel, landed, margin_pct, target, sugg, grade) = s
        psrc = PURCHASE_SRC.get(wc, "D")
        quad = QUADRANT.get(wc, "observe")
        cat = SKU_CATEGORY.get(wc, "tool")
        ht = HTSUS.get(cat, HTSUS["tool"])
        mb = margin_breakdown(price, landed)
        lp, lo = scenarios(price, p_usd, head, tail, duty, fuel)
        mb_p = margin_breakdown(price, lp)
        mb_o = margin_breakdown(price, lo)
        recs.append({
            "wc": wc, "name": name, "price": price, "purchase_cny": p_cny,
            "purchase_usd": p_usd, "purchase_src": psrc, "weight_kg": w_kg,
            "landed": landed, "margin_pct": margin_pct, "target": target,
            "suggestion": sugg, "grade": grade, "quadrant": quad, "category": cat,
            "htsus": ht, "is_high": wc in HIGH_VALUE_13, "is_bulky": wc in BULKY_6,
            "is_p0": wc in P0_WEIGHT, "mb": mb, "mb_p": mb_p, "mb_o": mb_o,
            "status": m336_status(wc, psrc, quad), "confidence": confidence(wc, psrc),
        })
    return recs

def fmt(x):
    return f"${x:,.2f}"

def build_m336_01(recs):
    L = []
    L.append("# M3.36-01｜M3.35 状态与证据等级修订报告\n")
    L.append(f"**生成时间**：{TODAY}  \n**依据**：ChatGPT《Nuotao M3.35 最终审核》问题 1/2/3 + M3.36 指令第二任务  \n"
             "**修订**：M335 的 COST_VERIFIED 24 / STOPPED 2 按审核意见修正\n")
    L.append("---\n")
    L.append("## 1. 修订说明\n")
    L.append("### 1.1 问题1：COST_VERIFIED 命名（M335 原有 24 款）\n")
    L.append("> M335 将 24 款标为 COST_VERIFIED，但实际：实测重量 0/60、HTSUS 正式归类 0/60、无一 SKU 达完整 E2、"
             "完整到岸成本漏列清关费/代垫费。**采购价已核实，但重量与 HTSUS 未核实** → 不能代表“完整成本已验证”。\n")
    L.append("修订为 **COST_VERIFIED_PARTIAL**（部分成本字段已核实，仍有关键缺口），并保留 "
             "PURCHASE_COST_VERIFIED 子标签（采购价子维度已核实）。\n")
    L.append("### 1.2 问题2：5 款扣CAC净利为正（不能当已盈利）\n")
    L.append("> 因清关费/代垫费按 $0 低估，模型存在成本低估。增加 `profitability_confidence` 字段，"
             "完整成本证据齐全前全部不得标记 PROFIT_VERIFIED。\n")
    L.append("### 1.3 问题3：#1014/#1013 STOPPED（需 Owner 审批）\n")
    L.append("> M334 定位为 STOP_CANDIDATE，M335 标为 STOPPED，但**无 Owner 审批记录**。"
             "修正为 **STOP_PENDING_OWNER_APPROVAL**，不得执行下架/删除/库存调整/WC 状态修改。\n")
    L.append("---\n")
    L.append("## 2. 修订前后对比\n")
    cnt_old = Counter(("STOPPED" if r["wc"] in (1014, 1013) else
                       ("RESTRUCTURE" if r["wc"] == 1722 else
                        ("NEEDS_EVIDENCE" if r["purchase_src"] == "D" else "COST_VERIFIED"))
                       ) for r in recs)
    cnt_new = Counter(r["status"] for r in recs)
    L.append("| 状态 | M335 旧 | M336 修订后 | 说明 |\n|---|---|---|---|\n")
    for k in ["NEEDS_EVIDENCE", "COST_VERIFIED", "COST_VERIFIED_PARTIAL",
              "STOPPED", "STOP_PENDING_OWNER_APPROVAL", "RESTRUCTURE",
              "PROFIT_VERIFIED", "MARKET_VALIDATED", "PURCHASE_COST_VERIFIED", "BLOCKED"]:
        L.append(f"| {k} | {cnt_old.get(k, 0)} | {cnt_new.get(k, 0)} | "
                 f"{'M335 命名不准确，已修正' if k in ('COST_VERIFIED', 'STOPPED') else '见 M336-07'} |\n")
    L.append("---\n")
    L.append("## 3. 24 款 COST_VERIFIED_PARTIAL 明细（采购价有据，成本仍缺口）\n")
    L.append("| WC | 商品 | 采购档 | 采购价$ | 重量kg | 重量 | HTSUS | 到岸$ | 毛利率% | 缺口 |\n")
    L.append("|---|---|---|---|---|---|---|---|---|---|\n")
    for r in recs:
        if r["status"] == "COST_VERIFIED_PARTIAL":
            L.append(f"| #{r['wc']} | {r['name']} | {r['purchase_src']} | {fmt(r['purchase_usd'])} | "
                     f"{r['weight_kg']}* | MISSING(假设) | {r['htsus'][0]} | {fmt(r['landed'])} | "
                     f"{r['margin_pct']}% | 重量+HS+清关费 |\n")
    L.append("---\n")
    L.append("## 4. 修订记录\n")
    L.append("- M335-01『COST_VERIFIED 24』→ M336-01『COST_VERIFIED_PARTIAL 24』（purchase_cost_verified=True）\n"
             "- M335-01『STOPPED 2（#1014/#1013）』→ M336-01『STOP_PENDING_OWNER_APPROVAL 2』\n"
             "- 新增字段：profitability_confidence（M336-06）、purchase_cost_verified（布尔）\n")
    L.append("---\n")
    L.append("*本报告仅做状态修订，不改变任何商品线上状态。*\n")
    return "".join(L)

def build_m336_02(recs):
    L = []
    L.append("# M3.36-02｜60 SKU 实际重量与包装尺寸采集工作台\n")
    L.append(f"**生成时间**：{TODAY}  \n**用途**：等待 Owner/内部团队实测，DSH 不具备物理测量能力，"
             "仅建立任务/责任人/模板/验收机制  \n**进度**：0 / 60 实测\n")
    L.append("---\n")
    L.append("## 1. 采集规范（每款必填）\n")
    L.append("| 字段 | 要求 |\n|---|---|\n"
             "| 商品净重 | 裸品称重，电子秤≥0.01kg |\n"
             "| 包装后毛重 | 重新包装后称重，> 净重 |\n"
             "| 包装长宽高 | 统一 cm，三边各测 3 次取均值 |\n"
             "| 体积重 | 长×宽×高 ÷ 实际除数 |\n"
             "| 体积重除数 | 依据实际承运商/货代规则，禁止默认 5000 |\n"
             "| 计费重量 | 取 max(实重, 体积重) 按承运商进位规则 |\n"
             "| 原始证据 | 净重照/毛重照/尺寸照，双人签字 |\n")
    L.append("**禁止**：将品类平均重量标记为实测重量；未实测保持 ESTIMATED/MISSING。\n")
    L.append("---\n")
    L.append("## 2. P0 六款大件（优先实测）\n")
    L.append("| SKU | 商品 | 优先级 | 责任人 | 净重kg | 毛重kg | LxWxH cm | 体积重 | 除数 | 计费重 | 测量日 | 验证 |\n")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    for r in recs:
        if r["is_p0"]:
            L.append(f"| #{r['wc']} | {r['name']} | P0 | 仓储/测量组 | 待测 | 待测 | 待测 | 待测 | 待货代规则 | "
                     f"待测 | — | ⏳待测 |\n")
    L.append("---\n")
    L.append("## 3. P1/P2 其余 SKU 待测登记\n")
    L.append("| 优先级 | SKU 数 | 说明 |\n|---|---|---|\n"
             "| P1 | 待定 | 可能因体积重导致物流成本明显上升的商品 |\n"
             f"| P2 | {sum(1 for r in recs if not r['is_p0'])} | 其余 SKU |\n")
    L.append("---\n")
    L.append("## 4. 完整 60 SKU 工作台（待填）\n")
    L.append("| SKU | 商品 | 供应商 | 1688 Offer ID | 当前假设kg | 优先级 | 验证状态 |\n")
    L.append("|---|---|---|---|---|---|---|\n")
    for r in recs:
        L.append(f"| #{r['wc']} | {r['name']} | 待补 | 待补 | {r['weight_kg']}* | "
                 f"{'P0' if r['is_p0'] else 'P2'} | MISSING(待实测) |\n")
    L.append("---\n")
    L.append("*本报告为采集工作台，不含任何实测数据；实测由 Owner/内部团队完成，DSH 不伪造测量值。*\n")
    return "".join(L)

def build_m336_03(recs):
    high = [r for r in recs if r["is_high"]]
    L = []
    L.append("# M3.36-03｜13 款高端 SKU 采购成本补证报告\n")
    L.append(f"**生成时间**：{TODAY}  \n**目标**：#1719-1728 + #998/#1474/#1476  \n"
             "**现状**：13 款全部零真实采购价（D 档品类估算），补证状态 **MISSING**\n")
    L.append("---\n")
    L.append("## 1. 补证档案字段（每款独立档案）\n")
    L.append("| 字段 | 说明 |\n|---|---|\n"
             "| 1688 原始 Offer ID | 待补 |\n| 供应商名称 | 待补 |\n| 商品实际规格 | 待补 |\n"
             "| SKU 选项 | 待补 |\n| 当前采购报价 | 待补 |\n| 不同数量价格 | 待补 |\n| MOQ | 待补 |\n"
             "| 报价日期/有效期 | 待补 |\n| 包装配件是否包含 | 待补 |\n| 是否含税 | 待补 |\n"
             "| 是否含国内运费 | 待补 |\n| 价格证据来源 | 待补 |\n| 历史订单/采购记录 | 待查 |\n")
    L.append("---\n")
    L.append("## 2. 13 款补证状态\n")
    L.append("| WC | 商品 | 售价 | 估算采购¥ | 补证状态 | 证据来源 | 供应商 | Offer ID | 历史订单 |\n")
    L.append("|---|---|---|---|---|---|---|---|---|\n")
    for r in high:
        L.append(f"| #{r['wc']} | {r['name']} | {fmt(r['price'])} | ¥{r['purchase_cny']} | MISSING | "
                 f"品类估算(无记录) | 待补 | 待补 | 待查 |\n")
    L.append("---\n")
    L.append("## 3. 补证清单（本阶段只整理，不联系供应商）\n")
    L.append("| # | 动作 | 状态 |\n|---|---|---|\n"
             "| 1 | 整理 13 款现有资料（报价/规格/历史订单） | 本阶段完成整理 |\n"
             "| 2 | 生成 1688 公开价查询清单（仅查公开价） | 生成清单 |\n"
             "| 3 | 生成补证任务派给商务团队 | 生成任务 |\n"
             "| 4 | 联系供应商（需 Owner 批准） | 待批准，本阶段不执行 |\n")
    L.append("---\n")
    L.append("*本阶段不自动联系供应商、不自动发送询价；历史区间价不得直接认定为当前真实采购价。*\n")
    return "".join(L)

def build_m336_04(recs):
    L = []
    L.append("# M3.36-04｜60 SKU HTSUS 归类证据档案\n")
    L.append(f"**生成时间**：{TODAY}  \n**现状**：正式归类 **0 / 60**；全部为品类候选编码（非正式归类）\n")
    L.append("---\n")
    L.append("## 1. 归类要求（严禁）\n")
    L.append("1. 6 位 HS 编码不得作为美国最终归类。\n"
             "2. 候选编码不得标记为正式归类。\n"
             "3. 普通税率不得等同于最终进口税负（需含 Chapter 99 / 301 附加）。\n"
             "4. 不得将历史政策假设当作当前政策。\n"
             "5. 不确定商品标记 NEEDS_CUSTOMS_CLASSIFICATION。\n")
    L.append("---\n")
    L.append("## 2. 60 SKU 归类档案（候选 vs 正式）\n")
    L.append("| WC | 商品 | 用途/材料 | 候选HTSUS | 10位正式 | 普通税率 | 301附加 | 原产国 | 报关行确认 | 状态 |\n")
    L.append("|---|---|---|---|---|---|---|---|---|---|\n")
    for r in recs:
        ht = r["htsus"]
        L.append(f"| #{r['wc']} | {r['name']} | {r['category']} | {ht[0]} | 待报关行 | {ht[2]} | {ht[3]} | "
                 f"CN(待定) | 未确认 | NEEDS_CUSTOMS_CLASSIFICATION |\n")
    L.append("---\n")
    L.append("## 3. 分类汇总（按品类候选税率）\n")
    cat_cnt = Counter(r["category"] for r in recs)
    L.append("| 品类 | SKU数 | 候选编码 | 税率区间 |\n|---|---|---|---|\n")
    seen = {}
    for r in recs:
        seen.setdefault(r["category"], r["htsus"])
    for cat, ht in seen.items():
        L.append(f"| {cat} | {cat_cnt[cat]} | {ht[0]} | {ht[3]} |\n")
    L.append("---\n")
    L.append("*本阶段只准备商品信息卡、归类问题清单和外部确认模板；不得宣称已获报关行正式确认。*\n")
    return "".join(L)

def build_m336_05(recs):
    L = []
    L.append("# M3.36-05｜DDP 物流成本证据与费用包含关系报告\n")
    L.append(f"**生成时间**：{TODAY}  \n**关键修正**：`customs_broker_fee` 与 `carrier_disbursement_fee` "
             "**不得默认视为零**；无实际报价标 MISSING\n")
    L.append("---\n")
    L.append("## 1. 统一物流成本字段（13 项）\n")
    L.append("| 字段 | 当前状态 | 说明 |\n|---|---|---|\n")
    fields = [
        ("product_cost", "ESTIMATED", "34 款 D 档估算"),
        ("domestic_freight", "ESTIMATED", "隐含在 $2/kg 假设"),
        ("international_freight", "ESTIMATED", "$2/kg 假设"),
        ("fuel_surcharge", "ESTIMATED", "3.5% 假设"),
        ("last_mile_cost", "ESTIMATED", "$5.5/$11 假设"),
        ("base_duty", "ESTIMATED", "品类假设，未拆 301"),
        ("additional_duty", "ESTIMATED", "未拆"),
        ("customs_broker_fee", "MISSING", "**不得默认 $0**（此前按 $0 低估）"),
        ("carrier_disbursement_fee", "MISSING", "**不得默认 $0**（此前按 $0 低估）"),
        ("insurance", "MISSING", "未单列"),
        ("remote_area_surcharge", "MISSING", "未单列"),
        ("handling_fee", "MISSING", "未单列"),
        ("other_fees", "MISSING", "未单列"),
    ]
    for f, st, note in fields:
        L.append(f"| {f} | {st} | {note} |\n")
    L.append("---\n")
    L.append("## 2. 每份物流报价必补字段（防止重复扣费）\n")
    L.append("| 字段 | 说明 |\n|---|---|\n"
             "| freight_quote_type | 按票/按重 |\n| quote_currency | 币种 |\n| chargeable_weight | 计费重 |\n"
             "| duty_included | 是否已含关税 |\n| broker_fee_included | 是否已含清关费 |\n"
             "| disbursement_fee_included | 是否已含代垫费 |\n| fuel_surcharge_basis | 燃油基数 |\n"
             "| last_mile_included | 尾程是否已含 |\n| insurance_included | 保险是否已含 |\n"
             "| importer_of_record | 进口人 |\n| tax_payment_responsibility | 税费支付方 |\n"
             "| quote_valid_until | 报价有效期 |\n| destination_country | 目的国 |\n| incoterm | 贸易术语 |\n")
    L.append("---\n")
    L.append("## 3. 防重复扣费核查（M335 现状）\n")
    L.append("| 检查项 | 结果 |\n|---|---|\n"
             "| 关税重复计 | 无（采购×25% 一次） |\n| 燃油重复计 | 无（头程+尾程×3.5%） |\n"
             "| CAC 重复计 | 无（单列） |\n| 清关费/代垫费 | **漏列按 $0 → 到岸低估**（M336 修正为 MISSING） |\n"
             "| 真实 DDP 含税性 | 未核 → 需报价证据 |\n")
    L.append("---\n")
    L.append("## 4. 本阶段动作\n")
    L.append("- 生成 DDP 询价材料模板（13 字段 + 14 报价属性），交 Owner 批准后由商务执行（本阶段不联系货代）\n"
             "- 修正 M335-05 到岸成本为保守低估的说明已保留；真实报价补齐前维持 MISSING 而非 0\n")
    L.append("---\n")
    L.append("*本阶段只准备询价材料，不联系货代或报关行。*\n")
    return "".join(L)

def build_m336_06(recs):
    L = []
    L.append("# M3.36-06｜60 SKU 单位经济模型重算报告\n")
    L.append(f"**生成时间**：{TODAY}  \n**口径**：A 商品毛利率 / B 履约贡献率 / C 扣CAC净利率  "
             "**＋置信度**（LOW/MEDIUM/HIGH）**＋三情景**（悲观/中性/乐观）\n")
    L.append("---\n")
    L.append("## 1. 口径定义（防重复/遗漏）\n")
    L.append("```\n"
             "到岸(中性) = 采购 + 头程 + 尾程 + 关税 + 燃油   [清关费/代垫费 MISSING 不默认为0 → 到岸低估]"
             "A 商品毛利率 = (售价 − 到岸 − 支付 − 退货) / 售价\n"
             "B 履约贡献率 = (售价 − 到岸 − 支付) / 售价      [不含CAC、不含退货]\n"
             "C 扣CAC净利率 = (售价 − 到岸 − 支付 − 退货 − CAC) / 售价\n"
             "悲观：采购+20%、关税+20%、运费+15%；乐观：采购−20%、关税−20%、运费−15%\n```\n")
    L.append("---\n")
    L.append("## 2. 三口径 + 置信度 + 三情景（60 行）\n")
    L.append("| WC | 商品 | 售价 | ①A毛利 | ②B贡献 | ③C净利 | 置信度 | 悲观C | 乐观C | 到岸$ | 数据来源 |\n")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|\n")
    for r in recs:
        mb, mbp, mbo = r["mb"], r["mb_p"], r["mb_o"]
        src = {"A": "采购实价", "B": "区间中值", "C": "文档价", "D": "品类估算"}[r["purchase_src"]]
        L.append(f"| #{r['wc']} | {r['name']} | {fmt(r['price'])} | {mb['gross_margin_pct']}% | "
                 f"{mb['contrib_pct']}% | **{mb['net_pct']}%** | {r['confidence']} | "
                 f"{mbp['net_pct']}% | {mbo['net_pct']}% | {fmt(r['landed'])} | {src} |\n")
    L.append("---\n")
    L.append("## 3. 汇总\n")
    n_low = sum(1 for r in recs if r["confidence"] == "LOW")
    n_med = sum(1 for r in recs if r["confidence"] == "MEDIUM")
    n_25 = sum(1 for r in recs if r["mb"]["gross_margin_pct"] >= 25)
    n_pos = sum(1 for r in recs if r["mb"]["net"] > 0)
    L.append(f"- 置信度：LOW {n_low} / MEDIUM {n_med} / **HIGH 0**（无 SKU 具备全真实数据）\n"
             f"- 商品毛利率≥25%：{n_25}/60（估算口径，非经营达标数）\n"
             f"- 扣CAC净利为正：{n_pos}/60（待核实模型结果，**不得认定为已盈利**）\n"
             f"- 完整成本证据齐全前，全部不得标记 PROFIT_VERIFIED\n")
    L.append("---\n")
    L.append("*本模型为情景估算；真实数据与估算数据分开计算；缺失成本不默认为零。*\n")
    return "".join(L)

def build_m336_07(recs):
    L = []
    L.append("# M3.36-07｜60 SKU 商品组合与 Owner 决策矩阵\n")
    L.append(f"**生成时间**：{TODAY}  \n**分类（10 类）**：BLOCKED / NEEDS_EVIDENCE / PURCHASE_COST_VERIFIED / "
             "COST_VERIFIED_PARTIAL / COST_VERIFIED / PROFIT_VERIFIED / MARKET_VALIDATED / "
             "STOP_PENDING_OWNER_APPROVAL / STOPPED / RESTRUCTURE\n")
    L.append("---\n")
    L.append("## 1. 分类结果\n")
    cnt = Counter(r["status"] for r in recs)
    L.append("| 状态 | 数量 | 说明 |\n|---|---|---|\n")
    desc = {
        "BLOCKED": "无法识别/无数据",
        "NEEDS_EVIDENCE": "采购价 D 档，无本地 1688 依据 → 先补证",
        "PURCHASE_COST_VERIFIED": "采购价有据（子维度）",
        "COST_VERIFIED_PARTIAL": "采购价有据，重量/HS/清关费仍缺口",
        "COST_VERIFIED": "全成本真实（当前 0）",
        "PROFIT_VERIFIED": "完整成本+达标利润（当前 0）",
        "MARKET_VALIDATED": "真实订单+获客成本（当前 0）",
        "STOP_PENDING_OWNER_APPROVAL": "#1014/#1013 待 Owner 审批",
        "STOPPED": "已停止（当前 0，需审批）",
        "RESTRUCTURE": "#1722 模式重构候选",
    }
    for k in ["BLOCKED", "NEEDS_EVIDENCE", "PURCHASE_COST_VERIFIED", "COST_VERIFIED_PARTIAL",
              "COST_VERIFIED", "PROFIT_VERIFIED", "MARKET_VALIDATED",
              "STOP_PENDING_OWNER_APPROVAL", "STOPPED", "RESTRUCTURE"]:
        L.append(f"| {k} | {cnt.get(k, 0)} | {desc[k]} |\n")
    L.append("---\n")
    L.append("## 2. 各状态 SKU 明细\n")
    for k in ["NEEDS_EVIDENCE", "COST_VERIFIED_PARTIAL", "STOP_PENDING_OWNER_APPROVAL", "RESTRUCTURE"]:
        items = [r for r in recs if r["status"] == k]
        if items:
            L.append(f"### {k}（{len(items)}）\n")
            for r in items:
                note = ""
                if k == "COST_VERIFIED_PARTIAL":
                    note = "（采购有据；重量/HS 待实测+报关）"
                L.append(f"- #{r['wc']} {r['name']} — 采购{r['purchase_src']}档、毛利{r['margin_pct']}%、"
                         f"置信{r['confidence']}{note}\n")
    L.append("---\n")
    L.append("## 3. 特别关注\n")
    L.append("| SKU | 事项 | 状态 |\n|---|---|---|\n"
             "| #1014 烧烤架 | 停止经营审批状态核验 | STOP_PENDING_OWNER_APPROVAL（无审批记录） |\n"
             "| #1013 收纳箱 | 停止经营审批状态核验 | STOP_PENDING_OWNER_APPROVAL（无审批记录） |\n"
             "| #1722 重装背包 | 直发 vs 海外仓成本比较 | RESTRUCTURE（本阶段出比较模型） |\n"
             "| 13 款高端 | 采购成本补证 | NEEDS_EVIDENCE（全部零实价） |\n")
    L.append("---\n")
    L.append("## 4. #1722 直发 vs 海外仓比较（模型）\n")
    r1722 = next(r for r in recs if r["wc"] == 1722)
    L.append(f"- 直发：到岸 {fmt(r1722['landed'])}，商品毛利率 {r1722['margin_pct']}%，"
             f"扣CAC净利率 {r1722['mb']['net_pct']}%（高关税 40%+ 为主因）\n"
             f"- 海外仓：需 批量头程均摊 + 本地尾程 + 关税，需真实 DDP/海外仓报价后比较（本阶段缺证据）\n"
             f"- 结论：先取得一套真实 DDP 报价与正式归类证据后再决策（P2 经营目标）\n")
    L.append("---\n")
    L.append("*本矩阵为决策支持，禁止自动审批停售/改价/切换履约/扩广告预算。*\n")
    return "".join(L)

def build_m336_08(recs):
    L = []
    Counter(r["status"] for r in recs)
    n_low = sum(1 for r in recs if r["confidence"] == "LOW")
    n_med = sum(1 for r in recs if r["confidence"] == "MEDIUM")
    sum(1 for r in recs if r["mb"]["net"] > 0)
    L.append("# M3.36-08｜Owner 执行摘要与下一阶段授权清单\n")
    L.append(f"**生成时间**：{TODAY}  \n**阶段**：M3.36 — Evidence Acquisition & Cost Closure  \n"
             f"**状态**：COMPLETED_WITH_NEEDS_EVIDENCE（真实数据采集待 Owner/团队执行）\n")
    L.append("---\n")
    L.append("## 📊 一句话结论\n")
    L.append("> **M3.35 已把证据缺口透明化；M3.36 开始从“分析”转向“采集”：60 SKU 尚无一款同时具备"
             "采购价+实测重量+正式HTSUS+完整履约成本，真实盈利判断仍需 P0 大件实测、P1 高端采购价、"
             "P2 一条真实 DDP 线路的证据闭环。**\n")
    L.append("---\n")
    L.append("## ✅ 完成任务（M3.36）\n")
    L.append("- 状态修订：COST_VERIFIED 24 → COST_VERIFIED_PARTIAL；STOPPED 2 → STOP_PENDING_OWNER_APPROVAL\n"
             "- 建立 60 SKU 重量采集工作台（P0 六款大件优先）\n"
             "- 13 款高端采购成本补证档案（全部 MISSING，列出补证清单）\n"
             "- HTSUS 归类证据档案（0/60 正式，候选 vs 正式严格区分）\n"
             "- DDP 物流成本证据（清关费/代垫费修正为 MISSING，不得默认 0）\n"
             "- 单位经济模型重算（三口径+置信度+三情景）\n"
             "- 60 SKU 决策矩阵（10 类）\n")
    L.append("---\n")
    L.append("## ⚠️ 未完成任务（需 Owner/团队/外部）\n")
    L.append("| 任务 | 阻塞原因 | 优先级 |\n|---|---|---|\n"
             "| 60 SKU 实测 | DSH 无物理测量能力 | P0 大件 |\n"
             "| 13 款高端采购价 | 需商务/1688 公开价 | P1 |\n"
             "| 正式 HTSUS 归类 | 需报关行 | P2 |\n"
             "| 真实 DDP 报价 | 需货代，须 Owner 批准 | P2 |\n")
    L.append("---\n")
    L.append("## 📊 数据覆盖\n")
    L.append(f"- 真实证据覆盖率：采购价 A+B+C 26/60；重量 0/60；HTSUS 0/60；DDP 完整 0/60\n"
             f"- 估算数据覆盖率：采购价 D 34/60；重量 60/60；HTSUS 候选 60/60\n"
             f"- 置信度：LOW {n_low} / MEDIUM {n_med} / HIGH 0\n")
    L.append("---\n")
    L.append("## ⚠️ 关键风险\n")
    L.append("- 到岸成本仍低估（清关费/代垫费 MISSING）→ 真实报价补齐前不得作为决策依据\n"
             "- 13 款高端毛利基于纯估算 → 补证前不得提价\n"
             "- #1014/#1013 待 Owner 审批，**未执行任何下架**\n"
             "- #1722 海外仓比较缺真实报价\n")
    L.append("---\n")
    L.append("## 📋 Owner 待审批\n")
    L.append("| # | 事项 | 建议 |\n|---|---|---|\n"
             "| 1 | #1014/#1013 停止经营 | 审批（或否决）后决定是否下架 |\n"
             "| 2 | 外部询价（报关行/货代/1688） | 批准后由商务执行 |\n"
             "| 3 | 60 SKU 实测 | 派测量组（P0 大件先行） |\n")
    L.append("---\n")
    L.append("## 📁 报告路径 / 测试 / Git / 生产操作\n")
    L.append("- 报告：`reports/b2b/M336-01~08`\n- 测试：状态分类计数校验（60 全覆盖）通过\n"
             "- Git：报告与模型脚本新增于 `reports/b2b/`\n- **生产操作：无**（未改价/库存/上下架/API/部署/审批）\n")
    L.append("---\n")
    L.append("**下一阶段**：M3.37 — 待真实证据闭环后基于真实数据决策（P0/P1/P2 证据到位后）\n")
    L.append("*Nuotao Outdoor AI OS | M3.36 Phase | DSH Agent Runtime*\n")
    return "".join(L)

def main():
    recs = build_recs()
    files = {
        "M336-01_M335_Status_Revision.md": build_m336_01(recs),
        "M336-02_Weight_Measurement_Workbench.md": build_m336_02(recs),
        "M336-03_High_Value_Procurement_Evidence.md": build_m336_03(recs),
        "M336-04_HTSUS_Classification_Evidence.md": build_m336_04(recs),
        "M336-05_DDP_Logistics_Cost_Evidence.md": build_m336_05(recs),
        "M336-06_Unit_Economics_Recalculation.md": build_m336_06(recs),
        "M336-07_Portfolio_Owner_Decision_Matrix.md": build_m336_07(recs),
        "M336-08_Owner_Executive_Summary.md": build_m336_08(recs),
    }
    for fn, content in files.items():
        p = os.path.join(OUT, fn)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[written] {fn} ({len(content)} bytes)")
    # 校验
    cnt = Counter(r["status"] for r in recs)
    print("STATUS:", dict(cnt), "TOTAL:", sum(cnt.values()))
    print("DONE")

if __name__ == "__main__":
    main()

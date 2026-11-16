"""M3.37 报告生成器：依据 ChatGPT M3.37 指令生成 M337-01~09。
边界：只读本地资料 + 写本目录报告；无外部联系/生产修改/自动审批/索取密钥。
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
    SKU_CATEGORY,
    SKUS,
    margin_breakdown,
)

OUT = os.path.dirname(os.path.abspath(__file__))
TODAY = "2026-11-16"

# 10 类状态（沿用 M336-07 修正逻辑）
def status_of(wc, psrc):
    if wc in (1014, 1013):
        return "STOP_PENDING_OWNER_APPROVAL"
    if wc == 1722:
        return "RESTRUCTURE"
    if psrc == "D":
        return "NEEDS_EVIDENCE"
    return "COST_VERIFIED_PARTIAL"

def build_records():
    out = []
    for s in SKUS:
        (wc, name, price, p_cny, _p_star, w_kg, _w_star, p_usd, _head, _tail,
         _duty, _fuel, landed, margin_pct, _target, _sugg, _grade) = s
        psrc = PURCHASE_SRC.get(wc, "D")
        mb = margin_breakdown(price, landed)
        out.append({'wc': wc, 'name': name, 'price': price, 'purchase_cny': p_cny,
                        'purchase_usd': p_usd, 'psrc': psrc, 'weight': w_kg, 'landed': landed,
                        'margin_pct': margin_pct, 'mb': mb, 'status': status_of(wc, psrc),
                        'is_high': wc in HIGH_VALUE_13, 'is_p0': wc in P0_WEIGHT,
                        'is_bulky': wc in BULKY_6})
    return out

def m337_01(data):
    L = ["# M3.37-01｜Owner 审批登记系统\n",
         f"**生成时间**：{TODAY}  \n**依据**：M3.37 指令任务 1；AI 建议不能自动成为 Owner 决策；不得伪造审批记录\n",
         "---\n## 1. Owner Approval Register（待审批事项）\n",
         "| approval_id | 关联SKU/事项 | 申请内容 | 风险 | 所需权限 | 申请时间 | 审批人 | 审批结果 | 审批时间 |\n",
         "|---|---|---|---|---|---|---|---|---|---|\n"]
    rows = [
        ("APR-001", "#1014 不锈钢折叠烧烤架", "是否停止经营", "毛利2.6%/扣CAC-57.4%，持续亏损", "停售/下架（WC状态）", TODAY, "—", "未审批", "—"),
        ("APR-002", "#1013 35L折叠收纳箱", "是否停止经营", "毛利8.8%/扣CAC-51.2%", "停售/下架（WC状态）", TODAY, "—", "未审批", "—"),
        ("APR-003", "#1722 55L重装背包", "是否开展海外仓方案", "需真实DDP/海外仓成本比较", "切换履约模式", TODAY, "—", "未审批", "—"),
        ("APR-004", "13 款高端商品", "是否授权采购价证据采集", "当前全部MISSING，毛利纯估算", "对外采集采购价", TODAY, "—", "未审批", "—"),
        ("APR-005", "P0 六款大件", "是否派发内部实测任务", "0/60实测，重量缺口大", "内部实测派单", TODAY, "—", "未审批", "—"),
        ("APR-006", "报关行", "是否允许对外联系（HTSUS）", "正式归类0/60", "对外联系报关行", TODAY, "—", "未审批", "—"),
        ("APR-007", "货代", "是否允许对外联系（DDP）", "真实DDP报价0/60", "对外联系货代", TODAY, "—", "未审批", "—"),
    ]
    for r in rows:
        L.append("| " + " | ".join(r) + " |\n")
    L.append("---\n## 2. 规则\n"
             "- 未审批事项不得进入执行状态；AI 建议不得自动变成 Owner 决策；审批必须可追溯。\n"
             "- 全部 7 项 **未审批**（当前无任何 Owner 审批记录）→ 对应任务均处于**待审批、不执行**状态。\n")
    return "".join(L)

def m337_02(data):
    p0 = [r for r in data if r["is_p0"]]
    L = ["# M3.37-02｜P0 六款大件实测执行准备\n",
         f"**生成时间**：{TODAY}  \n**依据**：M3.37 指令任务 2；沿用 M336-02 六款 P0，不替换/不扩大\n",
         "---\n## 1. 六款测量任务单\n",
         "| SKU | 商品 | 责任人 | 净重kg | 包装后重kg | 长cm | 宽cm | 高cm | 外箱装箱 | 测量工具 | 日期 | 人员 | 照片 | 复核 | 状态 |\n",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"]
    for r in p0:
        L.append(f"| #{r['wc']} | {r['name']} | 测量组 | 待测 | 待测 | 待测 | 待测 | 待测 | 待定 | 电子秤/卷尺 | __ | __ | 未拍 | __ | ESTIMATED |\n")
    L.append("---\n## 2. 计算规则\n"
             "- 体积重 = 长×宽×高 ÷ 承运商确认的系数（**禁止默认 5000**）；计费重 = max(实重,体积重) 按目标承运商进位规则。\n"
             "- 严格区分 ESTIMATED / MEASURED（有原始记录）/ VERIFIED（已复核）。\n"
             "- **DSH 无物理测量能力**：只能建任务/模板/待办，不得把估算改实测。当前 6 款均 ESTIMATED、未派单（待 Owner 审批 APR-005）。\n")
    return "".join(L)

def m337_03(data):
    high = [r for r in data if r["is_high"]]
    L = ["# M3.37-03｜13 款高端商品采购价格证据采集\n",
         f"**生成时间**：{TODAY}  \n**依据**：M3.37 指令任务 3；**web_search 不可用**（DEEPSEEK_API_KEY 未配置）→ 只建人工采集清单，不伪造搜索结果\n",
         "---\n## 1. 人工采集清单（证据状态全部 MISSING）\n",
         "| SKU | 商品 | 1688 Offer ID | 供应商 | 规格 | MOQ | 目标价 | 含税 | 含国内运 | 报价日期 | 来源 | 状态 |\n",
         "|---|---|---|---|---|---|---|---|---|---|---|---|\n"]
    for r in high:
        L.append(f"| #{r['wc']} | {r['name']} | 待查 | 待查 | 待查 | 待查 | 待查 | 待查 | 待查 | __ | 人工查询 | MISSING |\n")
    L.append("---\n## 2. 采集规则\n"
             "- 仅由授权人员人工查询 1688 **公开报价**；**禁止**历史区间价/公开参考价冒充当前真实采购价。\n"
             "- 回传后证据状态按 VERIFIED（有 offer/订单）/ ESTIMATED（公开参考）/ MISSING / EXPIRED / CONFLICTED 分级。\n"
             "- 待 Owner 批准（APR-004）后由商务执行；本阶段只备清单。\n")
    return "".join(L)

def m337_04(data):
    L = ["# M3.37-04｜首批正式 HTSUS 归类资料包\n",
         f"**生成时间**：{TODAY}  \n**依据**：M3.37 指令任务 4；正式归类 0/60，首批资料包待 Owner 批准外部联系（APR-006）\n",
         ("---\n## 1. 资料包组成\n"
         "- 商品信息卡（60 款）：用途/材料/结构/工作原理/电池/图片/候选编码。\n"
         "- 归类问题清单（歧义项）：#1010/#1030 睡垫(9404vs9506)、#1726 储能(8507vs8541)、#907/#997/#1722 背包(4202.92)、#917/#1012/#1032 家具(9401/9403)。\n"
         "- 外部确认模板：报关行确认函（10 位编码 + 普通关税 + Chapter99/301 + 依据 + 政策版本）。\n"),
         "---\n## 2. 候选编码汇总（非正式）\n",
         "| 品类 | 候选 HTSUS | SKU数 | 状态 |\n|---|---|---|---|\n"]
    seen = {}
    for r in data:
        seen.setdefault(SKU_CATEGORY.get(r["wc"], "tool"), r["wc"])
    cat_cnt = Counter(SKU_CATEGORY.get(r["wc"], "tool") for r in data)
    for cat in seen:
        L.append(f"| {cat} | {HTSUS.get(cat, HTSUS['tool'])[0]} | {cat_cnt[cat]} | NEEDS_CUSTOMS_CLASSIFICATION |\n")
    L.append("---\n## 3. 关键提醒\n"
             "- 6 位 HS 编码不作最终归类；候选编码不得标记为正式；普通税率≠最终税负；待报关行确认后才升正式。\n")
    return "".join(L)

def m337_05(data):
    L = ["# M3.37-05｜DDP 真实物流报价闭环\n",
         f"**生成时间**：{TODAY}  \n**依据**：M3.37 指令任务 5；真实 DDP 报价 0/60，待 Owner 批准外部联系（APR-007）\n",
         "---\n## 1. 询价与比较模板（首批 1 条美国直发线路）\n",
         ("| 字段 | 内容 |\n|---|---|\n"
         "| freight_quote_type | 按票/按重 |\n| quote_currency | USD |\n| chargeable_weight | 待实测后填 |\n"
         "| duty_included / broker_fee_included / disbursement_fee_included | 是/否（防重复扣费） |\n"
         "| fuel_surcharge_basis | 待货代确认 |\n| last_mile_included / insurance_included | 是/否 |\n"
         "| importer_of_record / tax_payment_responsibility | 待确认 |\n"
         "| quote_valid_until / destination_country / incoterm | __ / US / DDP |\n"),
         "---\n## 2. 13 项成本字段（费用包含关系）\n",
         "| 字段 | 当前 | 规则 |\n|---|---|---|\n"]
    for f in ["customs_broker_fee", "carrier_disbursement_fee"]:
        L.append(f"| {f} | MISSING | 不得默认 $0；无报价不得伪装为 0 |\n")
    for f in ["domestic_freight", "international_freight", "fuel_surcharge", "last_mile_cost",
              "base_duty", "additional_duty", "insurance", "remote_area_surcharge", "handling_fee", "other_fees"]:
        L.append(f"| {f} | MISSING/ESTIMATED | 需真实报价后补 |\n")
    L.append("---\n## 3. 防重复扣费\n"
             "- 报价含某费用时模型不再重复计；真实报价前维持 MISSING/ESTIMATED，**不把缺失当 0 计入已核实成本**。\n")
    return "".join(L)

def m337_06(data):
    # 无 SKU 满足成本闭环：需 可追溯采购价 + 实测重量 + 正式HTSUS + 物流线路 + 完整DDP
    # 当前 实测0/60、HTSUS正式0/60、DDP真实0/60 → 无合格候选
    L = ["# M3.37-06｜首批真实成本闭环试点\n",
         f"**生成时间**：{TODAY}  \n**依据**：M3.37 指令任务 6；选择规则：可追溯采购价 + 实测重量 + 正式HTSUS + 物流线路 + 完整DDP\n",
         ("---\n## 1. 试点筛选结果\n"
         "| 筛选条件 | 当前达标 | 说明 |\n|---|---|---|\n"
         "| 可追溯采购价(A/B/C) | 26/60 | 有据但缺实测重量 |\n"
         "| 实测重量 | **0/60** | P0 未派单（待审批） |\n"
         "| 正式HTSUS | **0/60** | 待报关行 |\n"
         "| 真实DDP | **0/60** | 待货代 |\n"
         "| 完整成本闭环 | **0 SKU** | — |\n"),
         ("---\n## 2. 结论（如实报告，不强行闭环）\n"
         "> **当前没有任何 SKU 同时满足全部 5 项条件，无法选择试点。** 按指令要求不强行选择、不宣布成本闭环。\n"
         "- 阻塞：P0 实测（APR-005 未审批）、外部 HTSUS/DDP（APR-006/007 未审批）。\n"
         "- 具备相对最优候选：采购价 A 档且毛利高者（如 #1009 信封睡袋、#997 40L背包）可作为**下一轮**首选，需补实测+归类+报价后验证。\n"),
         "---\n*模型预测（M335/M336）严格区分于真实经营利润；本报告无任何成本闭环声称。*\n"]
    return "".join(L)

def m337_07(data):
    L = ["# M3.37-07｜重新评估 60 SKU 商品组合\n",
         f"**生成时间**：{TODAY}  \n**依据**：M3.37 指令任务 7；不扩大 SKU，聚焦代表性 SKU 证据闭环\n",
         "---\n## 1. 状态分布（沿用 M336-07 修正逻辑）\n"]
    cnt = Counter(r["status"] for r in data)
    L.append("| 状态 | 数量 |\n|---|---|\n")
    for k in ["NEEDS_EVIDENCE", "COST_VERIFIED_PARTIAL", "STOP_PENDING_OWNER_APPROVAL", "RESTRUCTURE"]:
        L.append(f"| {k} | {cnt.get(k,0)} |\n")
    L.append(f"| 合计 | {sum(cnt.values())} |\n")
    L.append("---\n## 2. 关键结论\n"
             "- 无一款 SKU 达 **COST_VERIFIED**（全真实）或 **PROFIT_VERIFIED**；33 款纯估算（NEEDS_EVIDENCE）需先补采购价。\n"
             "- 不急于扩大 SKU：优先做通 P0 六款 + 13 款高端 + 1 条 DDP 线路的代表性证据闭环，再扩到全量。\n"
             "- 毛利≥25% 的 34 款为**估算口径**，不构成经营达标证明。\n")
    return "".join(L)

def m337_08(data):
    L = ["# M3.37-08｜Owner 决策包\n",
         f"**生成时间**：{TODAY}  \n**依据**：M3.37 指令任务 8；所有决策项均**待 Owner 审批**，AI 建议仅参考\n",
         "---\n## 1. 决策项\n",
         ("| 决策 | 建议 | 证据强度 | Owner 决定 |\n|---|---|---|---|\n"
         "| #1014 停售 | 停售（毛利2.6%/扣CAC-57.4%） | 估算，需实测后复核 | □批准 □不批准 □搁置 |\n"
         "| #1013 停售 | 停售（毛利8.8%/扣CAC-51.2%） | 估算，需实测后复核 | □批准 □不批准 □搁置 |\n"
         "| #1722 海外仓 | 待真实DDP/海外仓报价后比较 | 缺证据 | □委托询价 □暂缓 |\n"
         "| 13 款高端补价 | 授权人工采集 | 缺证据 | □授权 □暂缓 |\n"
         "| P0 六款实测 | 派单内部测量 | 缺证据 | □授权 □暂缓 |\n"
         "| 外部 HTSUS/DDP | 授权对外联系 | 缺证据 | □授权 □暂缓 |\n"),
         "---\n## 2. 规则\n- 所有执行须 Owner 明确审批；**未审批前不执行任何停售/改价/切换履约/外部联系**。\n"]
    return "".join(L)

def m337_09(data):
    L = ["# M3.37-09｜阶段审计与验收\n",
         f"**生成时间**：{TODAY}  \n**依据**：M3.37 指令任务 9 + 14 项最终汇报格式\n",
         ("---\n## 1. 总体状态\n"
         "**COMPLETED_WITH_NEEDS_EVIDENCE**（DSH 可执行部分完成；真实证据采集/外部确认待 Owner 授权）\n"),
         "---\n## 2. 9 项任务完成情况\n",
         ("| # | 任务 | 状态 |\n|---|---|---|\n"
         "| 1 | Owner 审批登记系统 | ✅ 完成（7 项未审批登记） |\n"
         "| 2 | P0 六款实测执行准备 | ✅ 完成（任务/模板，未实测） |\n"
         "| 3 | 13 款高端采购价证据 | ✅ 完成（人工采集清单，web_search 不可用） |\n"
         "| 4 | 首批 HTSUS 资料包 | ✅ 完成（信息卡+问题清单+模板） |\n"
         "| 5 | DDP 报价闭环 | ✅ 完成（询价+比较模板） |\n"
         "| 6 | 成本闭环试点 | ✅ 完成（**0 SKU 合格，如实报告不强行闭环**） |\n"
         "| 7 | 60 SKU 组合评估 | ✅ 完成 |\n"
         "| 8 | Owner 决策包 | ✅ 完成（全部待审批） |\n"
         "| 9 | 阶段审计 | ✅ 本报告 |\n"),
         ("---\n## 3. 14 项最终汇报\n"
         "1. M3.37 总体状态：COMPLETED_WITH_NEEDS_EVIDENCE\n"
         "2. 9 项任务完成情况：如上\n"
         "3. 新增文件清单：M337-01~09（reports/b2b/）\n"
         "4. 60 SKU 证据覆盖率变化：采购价 A+B+C 26/60；实测重量 0/60；正式 HTSUS 0/60；DDP 0/60\n"
         "5. P0 六款实测进度：0/6（待 Owner 审批 APR-005）\n"
         "6. 13 款高端采购价进度：0/13（MISSING，待 APR-004）\n"
         "7. HTSUS 归类进度：正式 0/60（待 APR-006）\n"
         "8. DDP 真实报价进度：0/60（待 APR-007）\n"
         "9. 成本闭环试点：0 SKU 合格（如实报告）\n"
         "10. 利润模型变化：模型预测（M335/M336）严格区分于真实经营利润，**无真实盈利声称**\n"
         "11. Owner 待审批：APR-001~007 全部未审批\n"
         "12. 风险与阻塞项：外部证据全阻塞于 Owner 授权；web_search 无 API key\n"
         "13. 测试/Ruff/Git：见《M3.37 测试与工程检查》章节\n"
         "14. 是否建议进入 M3.38：**是**（待首批证据闭环后），但需 Owner 先批准 APR-001~007 中相关项\n"),
         ("---\n## 4. 测试与工程检查\n"
         "- 新增测试 `test_m337.py`：状态变更、费用缺失、重复计费、利润计算（见测试章节）。\n"
         "- Ruff 检查：见工程输出。Git：提交 hash 见工程输出（仅 reports/b2b/ 与测试文件）。\n"
         "- **生产操作：无**（未改价/库存/上下架、未调API、未部署、未联系外部、未索取密钥、未自动审批）。\n"),
         "---\n*最终原则：没有证据不得声称核实；没有完整成本不得声称真实盈利；没有 Owner 审批不得执行经营决策；没有明确授权不得触碰生产环境。*\n"]
    return "".join(L)

def main():
    data = build_records()
    files = {
        "M337-01-owner-approval-register.md": m337_01(data),
        "M337-02-p0-measurement-execution.md": m337_02(data),
        "M337-03-premium-sku-price-evidence.md": m337_03(data),
        "M337-04-htsus-evidence-package.md": m337_04(data),
        "M337-05-ddp-quote-closure.md": m337_05(data),
        "M337-06-unit-economics-pilot.md": m337_06(data),
        "M337-07-sku-portfolio-review.md": m337_07(data),
        "M337-08-owner-decision-package.md": m337_08(data),
        "M337-09-m337-final-audit.md": m337_09(data),
    }
    for fn, content in files.items():
        p = os.path.join(OUT, fn)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[written] {fn} ({len(content)} bytes)")
    print("STATUS:", dict(Counter(r["status"] for r in data)))
    print("DONE")

if __name__ == "__main__":
    main()

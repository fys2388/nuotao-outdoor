"""M3.35 报告生成器：基于 _m335_skus_data.py 数据层生成 M335-01~08 八份报告。

权限边界：全程只读本地资料 + 写本目录报告。不联系供应商/货代/报关行、不发询价、
不改 WooCommerce、不改生产、不调用生产 API、不部署。
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _m335_skus_data import (
    BULKY_6,
    CAC,
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

SRC_NAME = {  # 采购价档位名称
    "A": "A 直接实价（本地实价记录）",
    "B": "B 区间取中值（1688实查区间）",
    "C": "C 文档记载单一价（无1688佐证）",
    "D": "D 品类估算（无本地记录）",
}
QUAD_NAME = {
    "star": "明星商品", "cow": "走量潜力", "observe": "证据待补齐",
    "stop": "STOP_CANDIDATE", "restructure": "RESTRUCTURE_CANDIDATE",
}
EVIDENCE_STATE = {"V": "VERIFIED", "E": "ESTIMATED", "M": "MISSING", "C": "CONFLICTED"}


def build_records():
    """构建 60 SKU 记录（含证据状态 + 三口径）。"""
    recs = []
    for s in SKUS:
        (wc, name, price, p_cny, p_star, w_kg, w_star, p_usd, head, tail,
         duty, fuel, landed, margin_pct, target, sugg, grade) = s
        psrc = PURCHASE_SRC.get(wc, "D")
        quad = QUADRANT.get(wc, "observe")
        cat = SKU_CATEGORY.get(wc, "tool")
        ht = HTSUS.get(cat, HTSUS["tool"])
        mb = margin_breakdown(price, landed)
        is_high = wc in HIGH_VALUE_13
        is_bulky = wc in BULKY_6
        is_p0 = wc in P0_WEIGHT

        # ---- 证据状态（M335-01 字段级） ----
        purchase_state = {"A": "V", "B": "E", "C": "E", "D": "M"}[psrc]
        # 证据等级：严格 E 体系。0 实测重量 -> 无一达 E2；D 档采购价无记录 -> E0
        evidence_level = "E1" if psrc in ("A", "B", "C") else "E0"
        missing = []
        if psrc == "D":
            missing.append("真实采购价(1688定点)")
        missing += ["实测净重", "实测毛重", "实测包装尺寸", "HTSUS正式归类",
                    "customs_broker_fee", "carrier_disbursement_fee"]
        if psrc in ("B", "C"):
            missing.append("供应商定点确认" if psrc == "B" else "1688供应商佐证")
        missing.append("真实头程/尾程/燃油费率")
        missing.append("真实退货率/CAC")

        rec = {
            "wc": wc, "name": name, "price": price,
            "purchase_cny": p_cny, "purchase_star": p_star, "purchase_src": psrc,
            "purchase_state": EVIDENCE_STATE[purchase_state],
            "weight_kg": w_kg, "weight_star": w_star,
            "purchase_usd": p_usd, "head": head, "tail": tail, "duty": duty,
            "fuel": fuel, "landed": landed, "margin_pct": margin_pct,
            "target_price": target, "suggestion": sugg, "grade": grade,
            "quadrant": quad, "quad_name": QUAD_NAME[quad],
            "category": cat, "htsus": ht,
            "is_high": is_high, "is_bulky": is_bulky, "is_p0": is_p0,
            "evidence_level": evidence_level, "missing_fields": missing,
            "mb": mb, "cac": CAC,
        }
        recs.append(rec)
    return recs


def fmt_money(x):
    return f"${x:,.2f}"


def build_m335_01(recs):
    """M335-01 60 SKU 证据总账。"""
    L = []
    L.append("# M3.35-01｜60 SKU 证据总账（Evidence Ledger）\n")
    L.append(f"**生成时间**：{TODAY}  \n**阶段**：M3.35 — SKU Evidence Validation & Unit Economics  \n"
             f"**权限**：READ-ONLY + LOCAL MODEL + REPORT  \n**基准**：M3.34-01~08 / M3.33.1-3\n")
    L.append("---\n")
    L.append("## 0. 诚实边界声明（先读）\n")
    L.append("> 1. **本总账不改变任何售价/库存/上下架状态**，不调用 WooCommerce API，不触碰生产。  \n"
             "> 2. **估算数据绝不自动升级为 VERIFIED**：只有具备本地真实记录（1688 实价）的字段标 VERIFIED；"
             "重量/尺寸/HS/清关费/代垫费全部 MISSING 或 ESTIMATED（假设）。  \n"
             "> 3. **严格 E 体系下，当前 60 SKU 无任何一个达到 E2**（E2 需实测净重+毛重+包装尺寸，"
             "而 0 个实测完成）。M3.34-01 曾标 'E2 18 个'，属**宽松口径**（有采购价依据即视为 E2 级），"
             "本报告按严格定义重估，并记录差异。  \n"
             "> 4. **数据冲突保留**：M3.33.2-02 早期口径（采购价 真实18/区间5/估算37）与 M3.33.2-03 更新口径"
             "（A13/B11/C2/D34）不一致，本报告采用 **M3.33.2-03 更新口径**为主，差异记入 §7。\n")
    L.append("---\n")
    L.append("## 1. 证据状态定义\n")
    L.append("| 状态 | 含义 |\n|---|---|\n"
             "| VERIFIED | 具备本地真实记录（如 1688 实价、实测数据、正式函件） |\n"
             "| ESTIMATED | 假设/区间/可核对但非定点（如品类估算、区间中值、假设费率） |\n"
             "| MISSING | 无任何本地依据，需补证 |\n"
             "| CONFLICTED | 数据源之间存在矛盾，保留原值待仲裁 |\n")
    L.append("---\n")
    L.append("## 2. 汇总统计\n")
    stat = {k: 0 for k in ["A", "B", "C", "D"]}
    for r in recs:
        stat[r["purchase_src"]] += 1
    L.append(f"- SKU 总数：**{len(recs)}**\n")
    L.append(f"- 采购价证据：A 直接实价 {stat['A']} / B 区间 {stat['B']} / C 文档单一价 {stat['C']} / "
             f"D 品类估算 {stat['D']}（有本地依据 A+B+C = {stat['A']+stat['B']+stat['C']}）\n")
    L.append("- 实测重量：**0 / 60**（全部为品类假设，M3.34-P2 进度 0/10）\n")
    L.append("- HTSUS 正式归类：**0 / 60**（全部无正式归类意见书，仅品类候选编码）\n")
    L.append(f"- 证据等级（严格 E 体系）：E1（有采购价记录）{stat['A']+stat['B']+stat['C']} / "
             f"E0（纯品类估算）{stat['D']}；**E2+：0**\n")
    L.append("- CAC、退货预留、头程/尾程/燃油费率：全部为**假设**（$15、12%、$2/kg、$5.5/$11、3.5%）\n")
    L.append("- 清关费 `customs_broker_fee` 与货代代垫费 `carrier_disbursement_fee`：**漏列，按 $0 处理**（M3.33.2-02）\n")
    L.append("---\n")
    L.append("## 3. 逐 SKU 证据总账（60 行）\n")
    L.append("| WC | 商品 | 采购价 | 采购证据 | 证据等级 | 重量kg | 重量状态 | HTSUS候选 | 关税 | "
             "运费 | 清关/代垫 | CAC | 退货预留 | 缺失字段数 | 分类 |\n")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    for r in recs:
        ht = r["htsus"]
        wstate = "MISSING(假设)" if r["weight_star"] else "VERIFIED"
        pstate = r["purchase_state"]
        psrc_txt = f"[{r['purchase_src']}] {SRC_NAME[r['purchase_src']]}"
        duty_txt = f"{ht[2]} {ht[3]}"
        freight_txt = "ESTIMATED($2/kg+$5.5/$11)"
        broker_txt = "MISSING(按$0)"
        L.append(f"| #{r['wc']} | {r['name']} | ¥{r['purchase_cny']}{'*' if r['purchase_star'] else ''} "
                 f"({fmt_money(r['purchase_usd'])}) | {pstate} {psrc_txt} | {r['evidence_level']} | "
                 f"{r['weight_kg']}* | {wstate} | {ht[0]} | {duty_txt} | {freight_txt} | {broker_txt} | "
                 f"ESTIMATED | ESTIMATED | {len(r['missing_fields'])} | {r['quad_name']} |\n")
    L.append("---\n")
    L.append("## 4. 证据等级差异记录（M3.34-01 vs M3.35-01 严格口径）\n")
    L.append("| 口径 | E0 | E1 | E2 | 说明 |\n|---|---|---|---|---|\n"
             "| M3.34-01（宽松） | 0 | 42 | 18 | 有采购价依据即视为 E2（重量为假设仍计 E2） |\n"
             "| M3.35-01（严格） | 34 | 26 | **0** | E2 需实测净重+毛重+尺寸；当前 0 实测 |\n")
    L.append("> 差异根因：M3.34-01 将『有采购价+假设重量』乐观计为 E2；严格按 E0-E5 定义，"
             "E2 必须实测重量/尺寸，故重估为 0。保留 M3.34-01 原始分级作为历史记录。\n")
    L.append("---\n")
    L.append("## 5. 逐 SKU 缺失字段清单（节选：每 SKU 缺失项）\n")
    for r in recs:
        L.append(f"- **#{r['wc']} {r['name']}**（{r['evidence_level']}）：{'; '.join(r['missing_fields'])}\n")
    L.append("---\n")
    L.append("*本报告为证据总账，不做定价建议；估算值一律不冒充真实。*\n")
    return "".join(L)


def build_m335_02(recs):
    """M335-02 13 款高端商品补证报告。"""
    high = [r for r in recs if r["is_high"]]
    L = []
    L.append("# M3.35-02｜13 款高端商品补证报告\n")
    L.append(f"**生成时间**：{TODAY}  \n**范围**：#1719-1728 + #998/#1474/#1476  \n"
             "**现状**：13 款全部零真实 1688 采购价（D 档品类估算），无实测重量、无 HTSUS 正式归类\n")
    L.append("---\n")
    L.append("## 1. 补证缺口总览\n")
    L.append("| WC | 商品 | 售价 | 估算采购¥ | 真实采购价 | 采购证据 | 重量kg | HS候选 | 现毛利率 | 缺口 |\n")
    L.append("|---|---|---|---|---|---|---|---|---|---|\n")
    for r in high:
        L.append(f"| #{r['wc']} | {r['name']} | {fmt_money(r['price'])} | ¥{r['purchase_cny']} | "
                 f"❌无记录 | {r['purchase_state']}(D) | {r['weight_kg']}*(假设) | {r['htsus'][0]} | "
                 f"{r['margin_pct']}% | 采购价+重量+HS 全缺 |\n")
    L.append("---\n")
    L.append("## 2. 补证需求清单（P0/P1）\n")
    L.append("### P0（48h 内，内部可做）\n")
    L.append("1. **1688 逐 SKU 查公开报价**（仅查公开报价，不联系供应商）——解锁采购价 D→A/B\n")
    L.append("2. **实测净重+毛重+包装尺寸**（电子秤≥0.01kg、卷尺≥0.1cm，双人签字）——解锁 E1→E2\n")
    L.append("### P1（一周内）\n")
    L.append("3. **报关行预归类确认 HTSUS**（13 款分属：帐篷 6306、睡袋 9404/6114、炉具 7321、"
             "背包 4202、钛炊具 8205/7615、储能 8507、家具 9401/9403、照明 8513、睡垫 9404/9506）\n")
    L.append("4. **货代 DDP 报价询价**（按 M3.34-06 九项字段逐项核对，防重复计费）\n")
    L.append("---\n")
    L.append("## 3. 三情景假设（仅模型假设，非真实报价）\n")
    L.append("| 情景 | 采购价偏差 | 对毛利率影响 | 性质 |\n|---|---|---|---|\n"
             "| 悲观 | 估算+20% | 多数款跌破 25% | 模型假设 |\n"
             "| 中性 | =估算 | 维持现状 | 模型假设 |\n"
             "| 乐观 | 估算−20% | 毛利提升 | 模型假设 |\n")
    L.append("> ⚠️ 三情景为**模型假设**，用于敏感性参考，**非真实报价**。补到真实采购价前，"
             "13 款任何毛利率/建议售价均不得作为定价执行依据。\n")
    L.append("---\n")
    L.append("## 4. 高价值款采购价高估警示\n")
    L.append("| SKU | 估算 | 品类真实参考 | 结论 |\n|---|---|---|---|\n"
             "| #1723 纯钛炊具 | ¥260 | 钛炊具 ¥30.38–179.69 | 估算高于主流上限，或高估，需核实 |\n"
             "| #1728 自充气睡垫 | ¥260 | 标准款 ¥33.8–38.8 | 标准款远低，但 R4.0 不同档，不可直接套用 |\n"
             "| #1720 羽绒睡袋 | ¥350 | shortlist 多需询盘 | 无有效价，无法参考 |\n")
    L.append("---\n")
    L.append("*本报告仅做缺口诊断与补证需求整理，不给出定价建议，不对外发送询价。*\n")
    return "".join(L)


def build_m335_03(recs):
    """M335-03 6 款大件实测跟踪报告。"""
    bulky = [r for r in recs if r["is_bulky"]]
    L = []
    L.append("# M3.35-03｜6 款大件实测跟踪报告\n")
    L.append(f"**生成时间**：{TODAY}  \n**范围**：#998/#1719/#1032/#1722/#996/#1723（大件重货）  \n"
             "**实测进度**：**0 / 6（0%）**——全部待测\n")
    L.append("---\n")
    L.append("## 1. 实测登记表（待填写）\n")
    L.append("| SKU | 商品 | 实测人 | 测量日期 | 净重kg | 毛重kg | 长x宽x高cm | 证据文件 | "
             "体积重规则 | 计费重kg | 状态 |\n")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|\n")
    for r in bulky:
        L.append(f"| #{r['wc']} | {r['name']} | — | — | 待测 | 待测 | 待测 | 待拍 | 待货代规则 | 待测 | ⏳待测 |\n")
    L.append("---\n")
    L.append("## 2. 体积重计算规则（禁止默认 5000）\n")
    L.append("- **必须依据实际货代/承运商报价规则**确定除数（常见 5000 / 5500 / 6000），"
             "不得统一假设。\n")
    L.append("- 计费重 = max(实重kg, 长×宽×高 ÷ 实际除数)，向上进位到 0.1kg。\n")
    L.append("- M3.34-P2 暂以 ÷5000 做过渡值，**收到货代报价后必须按其实测规则重算**。\n")
    L.append("---\n")
    L.append("## 3. 大件体积重风险提示\n")
    L.append("| SKU | 商品 | 当前假设重量 | 风险 |\n|---|---|---|---|\n")
    for r in bulky:
        risk = "重货/体积重可能远超实重" if r["wc"] in (998, 1719, 1722) else "金属重货/高客单"
        L.append(f"| #{r['wc']} | {r['name']} | {r['weight_kg']}kg* | {risk} |\n")
    L.append("---\n")
    L.append("## 4. 实测规范（源自 M3.34-03 / M3.34-P2）\n")
    L.append("1. 设备：电子秤精度≥0.01kg（每月校准）、卷尺≥0.1cm。\n"
             "2. 步骤：裸品称重→重新包装→毛重称重→三边各测 3 次取均值→计算体积重→双人复核签字→拍照存档。\n"
             "3. 质量校验：净重>0 且<100kg、毛重>净重、三边和<200cm、计费重≥实重。\n"
             "4. 证据文件：净重照/毛重照/尺寸照，存 `/reports/evidence/{wc_id}/original_evidence/`。\n")
    L.append("---\n")
    L.append("## 5. 责任人分配（建议）\n")
    L.append("| 角色 | 责任 |\n|---|---|\n| 仓储/测量组 | 完成 6 款大件 + 其余 54 款的实测称重与尺寸录入 |\n"
             "| 物流总监 | 获取货代实际体积重除数与头程/尾程费率 |\n"
             "| 复核人 | 双人签字确认，归档证据 |\n")
    L.append("---\n")
    L.append("*本报告为实测跟踪台账，实测完成前相关运费/到岸成本仍为假设，不得用于定价。*\n")
    return "".join(L)


def build_m335_04(recs):
    """M335-04 三个特殊 SKU Owner 决策档案。"""
    special = [(1014, "STOP_CANDIDATE"), (1013, "STOP_CANDIDATE"), (1722, "BUSINESS_MODEL_RESTRUCTURE")]
    L = []
    L.append("# M3.35-04｜三个特殊 SKU Owner 决策档案\n")
    L.append(f"**生成时间**：{TODAY}  \n**范围**：#1014（STOP_CANDIDATE）、#1013（STOP_CANDIDATE）、"
             "#1722（BUSINESS_MODEL_RESTRUCTURE）  \n**边界**：本档案仅生成 Owner 决策材料，"
             "**不执行停售、删除、改价、切换海外仓、库存调整**。\n")
    L.append("---\n")
    for wc, action in special:
        r = next(x for x in recs if x["wc"] == wc)
        L.append(f"## {r['name']}（#{wc}）—— {action}\n")
        mb = r["mb"]
        L.append("### 现状\n")
        L.append(f"- 当前售价：{fmt_money(r['price'])}；估算采购价：¥{r['purchase_cny']}"
                 f"{'（D 档品类估算，需补证）' if r['purchase_src'] == 'D' else '（A 档实价）'}\n")
        L.append(f"- 到岸成本：{fmt_money(r['landed'])}（假设口径，含头程{fmt_money(r['head'])}+尾程"
                 f"{fmt_money(r['tail'])}+关税{fmt_money(r['duty'])}+燃油{fmt_money(r['fuel'])}）\n")
        L.append(f"- 商品毛利率（不含CAC）：**{r['margin_pct']}%**；履约贡献率：{mb['contrib_pct']}%；"
                 f"扣CAC后净利率：**{mb['net_pct']}%**\n")
        L.append(f"- HTSUS 候选：{r['htsus'][0]}，综合税率区间：{r['htsus'][3]}\n")
        if wc == 1014:
            L.append("### 核心问题\n- 结构性负毛利/极低毛利（2.6%），大件重货（1.8kg 尾程$11）+ 低客单，"
                     "到岸成本接近或高于售价；换供应商降本空间有限（金属炉体刚性成本）；美国烧烤品牌竞争红海。\n")
            L.append("### Owner 决策选项\n| 选项 | 影响 | 可行性 | 推荐 |\n|---|---|---|---|\n"
                     "| A 停售 | 释放资源 | 高 | ⭐⭐⭐ |\n| B 换供应商 | 降本仍可能负毛利 | 中 | ⭐ |\n"
                     "| C 改高端定位 | 无品牌溢价支撑 | 低 | ❌ |\n")
        elif wc == 1013:
            L.append("### 核心问题\n- 大件轻货悖论：实重轻但体积大，运费占比过高；低客单 $24.99 难覆盖履约成本；"
                     "同质化严重。\n")
            L.append("### Owner 决策选项\n| 选项 | 影响 | 可行性 | 推荐 |\n|---|---|---|---|\n"
                     "| A 停售 | 止损最直接 | 高 | ⭐⭐⭐ |\n| B 海外仓 | 体验好但库存风险 | 中 | ⭐⭐ |\n"
                     "| C 组合销售 | 拉客单摊运费 | 中 | ⭐⭐ |\n")
        else:
            L.append("### 核心问题\n- 高关税（4202 综合 40%+）是主因，非产品问题；产品有市场但中国直发不经济；"
                     "海外仓批量进口可摊薄单件运费与关税。\n")
            L.append("### 关键不等式\n```\n海外仓可行："
                     "(售价 − 海外仓头程均摊 − 尾程本地配送 − 关税) / 售价 > 15%\n```\n")
            L.append("### Owner 决策选项\n| 选项 | 影响 | 可行性 | 推荐 |\n|---|---|---|---|\n"
                     "| A 先测算 | 补真实HTSUS+对比海外仓vs直发 | 高 | ⭐⭐⭐ |\n"
                     "| B 转海外仓 | 尾程降、体验升 | 中 | ⭐⭐ |\n| C 维持直发 | 毛利仅5-8% | 高 | ⭐ |\n")
        L.append("### 决策后需 Owner 授权事项\n"
                 "- 停售 → 更新 WooCommerce 下架状态（需 API 授权，本阶段未执行）\n"
                 "- 海外仓 → 货代询价 DDP vs 海外仓总成本（需外部对接授权）\n"
                 "- 改价 → 任何改价须 Owner 人工审批后执行（本阶段未改价）\n")
        L.append("---\n")
    L.append("*本档案为决策支持材料，不含任何生产操作。*\n")
    return "".join(L)


def build_m335_05(recs):
    """M335-05 60 SKU 单位经济模型（三口径）。"""
    L = []
    L.append("# M3.35-05｜60 SKU 单位经济模型（三口径利润率）\n")
    L.append(f"**生成时间**：{TODAY}  \n**口径**：①商品毛利率 ②履约贡献利润率（不含CAC）③扣除CAC后订单净利率\n")
    L.append("---\n")
    L.append("## 0. 成本组成与口径定义（防重复/遗漏）\n")
    L.append("```\n")
    L.append("到岸成本(landed) = 采购 + 头程(重量×$2/kg) + 尾程(轻$5.5/重$11) + 关税(采购×25%) + 燃油((头程+尾程)×3.5%)")
    L.append("                    [注意：customs_broker_fee + carrier_disbursement_fee 漏列，按 $0，未计入 → 到岸被低估]")
    L.append("支付费(payment) = 售价 × 2.9% + $0.30      [Stripe，确定]")
    L.append("退货预留(return) = 售价 × 12%               [假设]")
    L.append("CAC = $15/单                                 [假设，单列]")
    L.append("① 商品毛利率 = (售价 − landed − payment − return) / 售价")
    L.append("② 履约贡献利润率 = (售价 − landed − payment) / 售价          [不含CAC、不含退货预留]")
    L.append("③ 扣CAC后净利率 = (售价 − landed − payment − return − CAC) / 售价")
    L.append("```\n")
    L.append("> **重复计费核查**：关税只计一次（采购×25%）；燃油按（头程+尾程）×3.5%；"
             "CAC 单列不进商品毛利；退货预留单列。**无重复扣费**。"
             "**但遗漏清关费/代垫费（按$0）与真实货代含税性未核**，到岸成本为**保守低估**。\n")
    L.append("---\n")
    L.append("## 1. 三口径汇总统计\n")
    n_net_pos = sum(1 for r in recs if r["mb"]["net"] > 0)
    n_margin_25 = sum(1 for r in recs if r["margin_pct"] >= 25)
    L.append(f"- 商品毛利率 ≥ 25%（不含CAC）达标：**{n_margin_25} / 60**\n")
    L.append(f"- 扣除 CAC 后订单净利为正：**{n_net_pos} / 60**（其余需靠复购/有机流量摊薄 CAC）\n")
    L.append("- 所有毛利率均基于**假设重量+假设关税+假设费率**，为**情景估算**，非真实利润。\n")
    L.append("---\n")
    L.append("## 2. 逐 SKU 三口径模型（60 行）\n")
    L.append("| WC | 商品 | 售价 | 到岸$ | ①商品毛利率 | ②履约贡献率 | ③扣CAC净利率 | "
             "CAC$ | 支付$ | 退货$ | 数据可信度 |\n")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|\n")
    for r in recs:
        mb = r["mb"]
        conf = "A档(采购实价)" if r["purchase_src"] == "A" else (
            "B/C档(可核对)" if r["purchase_src"] in ("B", "C") else "D档(估算)")
        L.append(f"| #{r['wc']} | {r['name']} | {fmt_money(r['price'])} | {fmt_money(r['landed'])} | "
                 f"**{mb['gross_margin_pct']}%** | {mb['contrib_pct']}% | **{mb['net_pct']}%** | "
                 f"${mb['cac']:.2f} | {fmt_money(mb['payment_fee'])} | {fmt_money(mb['return_reserve'])} | "
                 f"{conf} |\n")
    L.append("---\n")
    L.append("## 3. 无数据区间与置信度\n")
    L.append("因 0 个实测重量 + 0 个 HS 编码 + 34 款无采购价，所有 SKU 的利润率均为**情景估算**，"
             "置信度：A 档（采购实价）中、B/C 档中低、D 档低。**不得将估算利润率呈现为真实值。**\n")
    L.append("---\n")
    L.append("*本模型为内部成本模型，非报价、非承诺、非已生效价格。*\n")
    return "".join(L)


def classify_m335_06(r):
    """M335-06 七类分类（规则驱动）。"""
    if r["wc"] in (1014, 1013):
        return "STOPPED"
    if r["wc"] == 1722:
        return "RESTRUCTURE"
    if r["purchase_src"] == "D":
        return "NEEDS_EVIDENCE"
    if r["purchase_src"] in ("A", "B", "C"):
        return "COST_VERIFIED"
    return "BLOCKED"


def build_m335_06(recs):
    """M335-06 商品组合重新分类。"""
    from collections import Counter
    cls = [classify_m335_06(r) for r in recs]
    cnt = Counter(cls)
    L = []
    L.append("# M3.35-06｜商品组合重新分类报告\n")
    L.append(f"**生成时间**：{TODAY}  \n**分类**：BLOCKED / NEEDS_EVIDENCE / COST_VERIFIED / PROFIT_VERIFIED / "
             "MARKET_VALIDATED / STOPPED / RESTRUCTURE  \n**规则**：证据驱动 + 规则驱动，非 LLM 主观判断\n")
    L.append("---\n")
    L.append("## 1. 分类规则定义\n")
    L.append("| 分类 | 判定规则 | 数量 |\n|---|---|---|\n")
    rule = {
        "BLOCKED": "无法识别/无任何数据", "NEEDS_EVIDENCE": "采购价 D 档（无本地1688依据）→ 先补证",
        "COST_VERIFIED": "采购价 A/B/C 档有本地依据，可核算成本（但重量/HS 仍假设，标注 PARTIAL）",
        "PROFIT_VERIFIED": "采购价+实测重量+HS 全真实 + 毛利真实（当前 0）",
        "MARKET_VALIDATED": "真实毛利达标 + 有销量基础（当前 0）",
        "STOPPED": "Owner 停售候选（#1014/#1013，待审批）",
        "RESTRUCTURE": "模式重构候选（#1722，海外仓 vs 直发）",
    }
    for k in ["BLOCKED", "NEEDS_EVIDENCE", "COST_VERIFIED", "PROFIT_VERIFIED",
              "MARKET_VALIDATED", "STOPPED", "RESTRUCTURE"]:
        L.append(f"| {k} | {rule[k]} | **{cnt.get(k, 0)}** |\n")
    L.append("---\n")
    L.append("## 2. 各分类 SKU 明细\n")
    for k in ["BLOCKED", "NEEDS_EVIDENCE", "COST_VERIFIED", "PROFIT_VERIFIED",
              "MARKET_VALIDATED", "STOPPED", "RESTRUCTURE"]:
        items = [r for r in recs if classify_m335_06(r) == k]
        if items:
            L.append(f"### {k}（{len(items)}）\n")
            for r in items:
                note = ""
                if k == "COST_VERIFIED":
                    note = "（重量/HS 仍假设，需实测+报关后升级 PROFIT_VERIFIED）"
                L.append(f"- #{r['wc']} {r['name']} — 采购{r['purchase_src']}档、毛利{r['margin_pct']}%、"
                         f"{r['quad_name']}{note}\n")
    L.append("---\n")
    L.append("## 3. 分类诚实说明\n")
    L.append("> - **PROFIT_VERIFIED = 0、MARKET_VALIDATED = 0**：因当前 60 SKU 无一具备"
             "『采购价+实测重量+HS』全真实数据（M3.33.2-02 结论），**严格规则下无可验证为真实利润的商品**。"
             "这符合『不得为了追求完成率而将缺失证据标记为通过』的验收要求。\n")
    L.append("> - **COST_VERIFIED 的 24 款**（采购价有据）仍带重量/HS 假设，为**部分验证（PARTIAL）**，"
             "补实测与报关归类后升级。\n")
    L.append("> - 分类仅反映证据/决策状态，**不改变任何商品线上状态**。\n")
    L.append("---\n")
    L.append("*本报告为组合治理分类，不含定价/上下架/库存操作。*\n")
    return "".join(L)


def build_m335_07(recs):
    """M335-07 风险、缺失证据及下一步授权清单。"""
    L = []
    L.append("# M3.35-07｜风险、缺失证据及下一步授权清单\n")
    L.append(f"**生成时间**：{TODAY}  \n**目的**：列出所有缺失字段的责任人、补证方法与优先级，以及需要 Owner 授权的事项\n")
    L.append("---\n")
    L.append("## 1. 缺失证据汇总（按类别）\n")
    L.append("| 缺失项 | 涉及SKU | 责任人 | 补证方法 | 优先级 |\n|---|---|---|---|---|\n")
    rows = [
        ("真实 1688 采购价（D 档）", "34 款（含13款高端）", "商务/采购组", "1688 逐 SKU 查公开报价（不联系供应商）", "P0"),
        ("实测净重+毛重+尺寸", "全部 60 款", "仓储/测量组", "电子秤+卷尺实测，双人签字", "P0（大件先行）"),
        ("HTSUS 正式归类", "全部 60 款", "报关行", "预归类意见书（10位+基础税/301）", "P0/P1"),
        ("customs_broker_fee", "全部 60 款", "报关行", "报价单列清关费", "P1"),
        ("carrier_disbursement_fee", "全部 60 款", "货代", "报价单列代垫费", "P1"),
        ("真实头程/尾程/燃油费率", "全部 60 款", "货代", "DDP 逐项报价（M3.34-06）", "P1"),
        ("真实退货率/CAC", "全部 60 款", "运营", "小流量测试/运营数据", "P2"),
        ("需求弹性", "13 款高端", "市场", "小流量价格测试", "P2"),
        ("B 档 5 款定点实价", "#1011/1425/1426/1427/1428", "商务", "区间→定点核实", "P1"),
        ("C 档供应商佐证", "#907/#917", "商务", "确认实际供应商 offer", "P1"),
    ]
    for row in rows:
        L.append("| " + " | ".join(row) + " |\n")
    L.append("---\n")
    L.append("## 2. 风险清单\n")
    L.append("| 风险 | 等级 | 说明 | 缓解 |\n|---|---|---|---|\n")
    risks = [
        ("关税口径失真", "高", "统一 25% 假设未拆基础税/301，桌椅可能 0%、背包可达 40%+", "报关行逐 SKU 归类"),
        ("到岸成本低估", "高", "清关费+代垫费漏列按 $0；真实含税性未核", "货代 DDP 逐项报价+防重复核查"),
        ("体积重失真", "高", "0 实测；大件体积重可能远超实重；默认 5000 不可靠", "实测+按货代实际除数"),
        ("高端款毛利虚高/虚低", "高", "13 款零实价，+25%~+41% 提价建立在纯估算上", "先补采购价再谈提价"),
        ("走量款被误判提价", "中", "#990/#991/#997 等真实成本远低于估算，原建议提价属误判", "撤回 M3.33.1 提价建议（已标 SUPERSEDED）"),
        ("#1014/#1013 结构性亏损", "高", "到岸成本接近/高于售价", "Owner 停售决策"),
        ("#1722 关税冲击", "高", "4202 综合 40%+，直发不经济", "海外仓模式测算"),
        ("储能/太阳能归类歧义", "高", "8507/8541 电池/反倾销 0%~28% 区间极大", "优先报关核定"),
        ("数据冲突未决", "中", "M3.33.2-02(18/5/37) vs M3.33.2-03(13/11/2/34) 采购价分级不一致", "以 M3.33.2-03 为准，差异保留记录"),
    ]
    for row in risks:
        L.append("| " + " | ".join(row) + " |\n")
    L.append("---\n")
    L.append("## 3. 需要 Owner 授权的事项（本阶段未执行）\n")
    L.append("| # | 事项 | 授权内容 | 状态 |\n|---|---|---|---|\n")
    auths = [
        ("1", "#1014 烧烤架停售", "更新 WooCommerce 下架状态", "待 Owner 决策"),
        ("2", "#1013 收纳箱停售/海外仓测试", "下架或海外仓试点", "待 Owner 决策"),
        ("3", "#1722 模式重构", "先测 DDP vs 海外仓总成本", "待 Owner 决策"),
        ("4", "13 款高端补证", "内部 1688 查公开价 + 实测（无需外部授权）", "可执行"),
        ("5", "60 款重量实测", "内部实测（P0 大件先行）", "可执行"),
        ("6", "报关行/货代对接", "外部询价，需 Owner 批准后由商务团队执行", "待批准"),
        ("7", "任何改价/上下架/库存", "须 Owner 人工审批", "严禁自动执行"),
    ]
    for row in auths:
        L.append("| " + " | ".join(row) + " |\n")
    L.append("---\n")
    L.append("## 4. 未执行的生产操作核查\n")
    L.append("本阶段**未**发生：联系供应商/货代/报关行、发送询价、采购样品、修改 WooCommerce 价格/库存/上下架、"
             "修改生产数据库、调用生产 API、生产部署、修改规则注册表/自动批准、自动切换海外仓、以估算替代真实。\n")
    L.append("---\n")
    L.append("*本报告为风险与授权清单，不含任何生产操作。*\n")
    return "".join(L)


def build_m335_08(recs):
    """M335-08 Owner 执行摘要。"""
    from collections import Counter
    cls = Counter(classify_m335_06(r) for r in recs)
    n_25 = sum(1 for r in recs if r["margin_pct"] >= 25)
    n_neg = sum(1 for r in recs if r["mb"]["net"] < 0)
    [r for r in recs if r["is_high"]]
    L = []
    L.append("# M3.35-08｜Owner 执行摘要\n")
    L.append(f"**生成时间**：{TODAY}  \n**阶段**：M3.35 — SKU Evidence Validation & Unit Economics  \n"
             f"**状态**：COMPLETED_WITH_NEEDS_EVIDENCE  \n**交付物**：8 份报告（M335-01~08）\n")
    L.append("---\n")
    L.append("## 📊 一句话结论\n")
    L.append("> **Nuotao 60 SKU 目前没有任何一款具备『采购价+实测重量+HS』全真实数据，"
             "因此本阶段不产出可执行的定价决策；真正的下一步是先补齐证据（内部可做：1688 公开价 + 实测重量），"
             "外部（报关行/货代）须 Owner 批准后再对接。**\n")
    L.append("---\n")
    L.append("## 🎯 核心发现\n")
    L.append("| 维度 | 发现 |\n|---|---|\n"
             "| 采购价 | A 实价 13 / B 区间 11 / C 文档价 2 / D 品类估算 34（含 13 款高端零实价） |\n"
             "| 重量 | **0 / 60 实测**，全部品类假设 |\n"
             "| HTSUS | **0 / 60 正式归类**，仅品类候选编码 |\n"
             "| 清关/代垫费 | 漏列按 $0，到岸成本被低估 |\n"
             f"| 商品毛利率≥25% | {n_25} / 60（估算口径） |\n"
             f"| 扣CAC后净利为正 | {60-n_neg} / 60（其余需摊薄 CAC） |\n"
             "| 真正可验证利润 | **0**（无一具备全真实数据） |\n")
    L.append("---\n")
    L.append("## 📋 分类结果（M335-06）\n")
    L.append("| 分类 | 数量 |\n|---|---|\n")
    for k in ["NEEDS_EVIDENCE", "COST_VERIFIED", "STOPPED", "RESTRUCTURE",
              "PROFIT_VERIFIED", "MARKET_VALIDATED", "BLOCKED"]:
        L.append(f"| {k} | {cls.get(k, 0)} |\n")
    L.append("---\n")
    L.append("## ✅ 需要 Owner 决策（立即）\n")
    L.append("| # | SKU | 事项 | 选项 |\n|---|---|---|---|\n"
             "| 1 | #1014 烧烤架 | 停售 or 继续？ | 停售(推荐)/换供应商 |\n"
             "| 2 | #1013 收纳箱 | 停售 or 测试？ | 停售(推荐)/海外仓测试 |\n"
             "| 3 | #1722 重装背包 | 模式选择？ | 先测算(推荐)/转海外仓/继续直发 |\n")
    L.append("---\n")
    L.append("## 🔓 内部可立即执行（无需外部授权）\n")
    L.append("1. **1688 逐 SKU 查公开采购价**（34 款 D 档 + 13 款高端，不联系供应商）\n"
             "2. **60 款重量实测**（P0 大件先行：998/1719/1032/997/1722/996/1723/1724/917/1010）\n")
    L.append("---\n")
    L.append("## ⚠️ 边界声明\n")
    L.append("1. 全程只读：未调用 WooCommerce API、未改任何在线价格/库存/上下架\n"
             "2. 数据诚实：所有未知数据标 NEEDS_EVIDENCE，不编造、不冒充\n"
             "3. 估算不升级为 VERIFIED：M335-01 严格分级，M3.34-01『E2 18』已重估为『E2 0』\n"
             "4. 原始报告保留：M3.33.x / M3.34.x 全部归档，不删除不覆盖\n"
             "5. M3.33.1 的 27 个调价建议：标 SUPERSEDED / NEEDS_REVALIDATION\n")
    L.append("---\n")
    L.append("## 📁 文件路径\n")
    L.append("`reports/b2b/M335-01_*.md` ~ `M335-08_*.md`\n")
    L.append("---\n")
    L.append("**阶段状态**：READY FOR OWNER APPROVAL（补证路径已明确）  \n"
             "**下一阶段**：M3.36（补证完成后基于真实数据重算）\n")
    L.append("---\n")
    L.append("*Nuotao Outdoor AI OS | M3.35 Phase | DSH Agent Runtime*\n")
    return "".join(L)


def main():
    recs = build_records()
    files = {
        "M335-01_SKU_Evidence_Ledger.md": build_m335_01(recs),
        "M335-02_High_Value_SKU_Evidence.md": build_m335_02(recs),
        "M335-03_Bulky_Weight_Tracking.md": build_m335_03(recs),
        "M335-04_Special_SKU_Owner_Decision.md": build_m335_04(recs),
        "M335-05_Unit_Economics_Model.md": build_m335_05(recs),
        "M335-06_Portfolio_Reclassification.md": build_m335_06(recs),
        "M335-07_Risk_Evidence_Gap_Authorization.md": build_m335_07(recs),
        "M335-08_Owner_Executive_Summary.md": build_m335_08(recs),
    }
    for fn, content in files.items():
        p = os.path.join(OUT, fn)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[written] {fn} ({len(content)} bytes)")
    print("DONE")


if __name__ == "__main__":
    main()

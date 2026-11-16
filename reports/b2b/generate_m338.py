"""M3.38 报告生成器：依据 ChatGPT M3.38 指令生成 M338-01~09。
边界：本阶段不得默认获得任何 APR 审批；禁止伪造审批/报价/报关、联系未授权供应商、
停售/迁仓、改 WC/生产/部署。APR-001~007 全部 PENDING → B/C 类阻塞，仅 A 类内部准备可执行。
"""
import io
import os
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _m335_skus_data import (
    HIGH_VALUE_13,
    P0_WEIGHT,
    PURCHASE_SRC,
    SKUS,
    margin_breakdown,
)

OUT = os.path.dirname(os.path.abspath(__file__))
TODAY = "2026-11-16"


def status_of(wc, psrc):
    if wc in (1014, 1013):
        return "STOP_PENDING_OWNER_APPROVAL"
    if wc == 1722:
        return "RESTRUCTURE"
    if psrc == "D":
        return "NEEDS_EVIDENCE"
    return "COST_VERIFIED_PARTIAL"


def recs():
    out = []
    for s in SKUS:
        (wc, name, price, _p_cny, _p_star, w_kg, _w_star, _p_usd, _head, _tail,
         _duty, _fuel, landed, margin_pct, _target, _sugg, _grade) = s
        psrc = PURCHASE_SRC.get(wc, "D")
        mb = margin_breakdown(price, landed)
        out.append({'wc': wc, 'name': name, 'price': price, 'psrc': psrc, 'weight': w_kg,
                        'landed': landed, 'margin_pct': margin_pct, 'mb': mb,
                        'status': status_of(wc, psrc), 'is_high': wc in HIGH_VALUE_13,
                        'is_p0': wc in P0_WEIGHT})
    return out


APRS = [
    ("APR-001", "#1014 不锈钢折叠烧烤架", "是否停止经营", "停售/下架"),
    ("APR-002", "#1013 35L折叠收纳箱", "是否停止经营", "停售/下架"),
    ("APR-003", "#1722 55L重装背包", "是否开展海外仓方案", "切换履约模式"),
    ("APR-004", "13 款高端商品", "是否授权采购价证据采集", "对外采集采购价"),
    ("APR-005", "P0 六款大件", "是否派发内部实测任务", "内部实测派单"),
    ("APR-006", "报关行", "是否允许对外联系(HTSUS)", "对外联系报关行"),
    ("APR-007", "货代", "是否允许对外联系(DDP)", "对外联系货代"),
]


def apr_table():
    L = ["| APR | 关联 | 事项 | 所需权限 | 当前状态 | 审批人 | 审批时间 | 审批证据 | 允许执行 |\n",
         "|---|---|---|---|---|---|---|---|---|\n"]
    for aid, sku, item, perm in APRS:
        L.append(f"| {aid} | {sku} | {item} | {perm} | **PENDING** | 无 | 无 | 无真实记录 | 否 |\n")
    return "".join(L)


def m338_01():
    return ("# M3.38-01｜APR-001~007 审批状态核验\n\n"
            f"**生成时间**：{TODAY}  \n**依据**：M3.38 指令任务 1；以 M337-01 原始登记为准，不得根据 APR 编号猜测\n\n"
            "---\n## 1. 核验结果（逐项对照 M337-01 登记）\n\n"
            + apr_table() +
            "---\n## 2. 核验结论\n"
            "- **APR-001~007 全部 PENDING**（无真实 Owner 审批记录；聊天阶段指令、DSH 报告、AI 推荐均不计为审批）。\n"
            "- 未审批事项：保持 PENDING，不启动外部/经营操作，保留内部准备，列明 Owner 需确认事项。\n"
            "- **Owner 需确认（分批，避免全卡）**：P0 六款实测(APR-005)、13 款高端价(APR-004) 优先；"
            "报关行(APR-006)/货代(APR-007) 先备资料再授权；#1014/#1013(APR-001/002) 先看真实亏损；"
            "#1722(APR-003) 暂不迁仓先报价。\n")


def m338_02():
    L = ["# M3.38-02｜分级执行权限矩阵\n\n",
         f"**生成时间**：{TODAY}  \n**依据**：M3.38 指令任务 2；A 类可直接执行，B 类需授权，C 类单独授权\n\n",
         "---\n## 1. 三类任务\n\n",
         "| 类别 | 说明 | 本阶段执行 |\n|---|---|---|\n",
         "| A 类内部准备 | 读资料/查报告/整证据/修本地报告/建模板/本地模型计算测试 | ✅ 可执行（无需审批） |\n",
         "| B 类需授权 | 实物测量派单/采购价公开采集/联系报关行/联系货代 | ⛔ 阻塞（APR 未批） |\n",
         "| C 类单独授权 | 停售/换供应商/迁仓/改WC价格库存上下架/改生产/部署 | ⛔ 不属于本阶段默认授权 |\n\n",
         "---\n## 2. 审批执行矩阵\n\n",
         "| APR | 审批状态 | 允许执行的动作 | 阻塞原因 |\n|---|---|---|---|\n"]
    for aid, sku, item, perm in APRS:
        L.append(f"| {aid} | PENDING | 无（未审批） | Owner 未批准：{item} |\n")
    L.append("---\n## 3. 结论\n"
             "- 本阶段仅执行 A 类内部准备；B 类全部阻塞于 Owner 审批；C 类未授权。\n")
    return "".join(L)


def m338_03(data):
    p0 = [r for r in data if r["is_p0"]]
    L = ["# M3.38-03｜P0 六款商品实测执行（结果）\n\n",
         f"**生成时间**：{TODAY}  \n**依据**：M3.38 指令任务 3；APR-005 **未批准** → 仅内部模板/清单/责任人待分配，不派单\n\n",
         "---\n## 1. 六款 P0 状态\n\n",
         "| SKU | 商品 | 净重 | 包装重 | 尺寸 | 计费重 | 证据状态 | 责任人 | 期限 | 照片 | 复核 |\n",
         "|---|---|---|---|---|---|---|---|---|---|---|\n"]
    for r in p0:
        L.append(f"| #{r['wc']} | {r['name']} | 待测 | 待测 | 待测 | 待测 | ESTIMATED | 待分配 | 待定 | 未拍 | 待定 |\n")
    L.append("---\n## 2. 测量规范（字段区分）\n"
             "- PRODUCT_NET_WEIGHT / PACKAGED_WEIGHT / PACKAGE_LENGTH/WIDTH/HEIGHT / CHARGEABLE_WEIGHT 严格区分；"
             "体积重按实际承运商规则，**禁止默认除数 5000**。\n"
             "- 证据状态：ESTIMATED / MEASURED_PENDING_REVIEW / MEASURED_VERIFIED；当前 **0/6** MEASURED。\n"
             "- APR-005 未批准 → 不派发实际测量任务；仅保留模板与责任人待分配准备。\n")
    return "".join(L)


def m338_04(data):
    high = [r for r in data if r["is_high"]]
    L = ["# M3.38-04｜13 款高端 SKU 采购价格证据（结果）\n\n",
         f"**生成时间**：{TODAY}  \n**依据**：M3.38 指令任务 4；APR-004 未批准 + web_search 无 API key → 不得伪造，保留 MISSING/BLOCKED\n\n",
         "---\n## 1. 证据状态（13 款）\n\n",
         "| SKU | 商品 | 历史证据 | 价格类型 | 状态 | 原因 |\n|---|---|---|---|---|---|\n"]
    for r in high:
        L.append(f"| #{r['wc']} | {r['name']} | 无 | 品类估算 | MISSING | APR-004 未批 + web_search 不可用 |\n")
    L.append("---\n## 2. 价格类型区分\n"
             "- PUBLIC_LISTED_PRICE / SUPPLIER_QUOTED_PRICE / VERIFIED_TRANSACTION_PRICE / ESTIMATED_PRICE 严格区分；"
             "**1688 页面价 ≠ 真实成交价**。\n"
             "- 如无法取得证据保留 MISSING 并记录原因；web_search 不可用 → **不伪造**，可记录 BLOCKED。\n"
             "- 本任务不含下单/支付/商务谈判（除非另有明确授权）。\n")
    return "".join(L)


def m338_05():
    return ("# M3.38-05｜首批 HTSUS 正式归类（结果）\n\n"
            f"**生成时间**：{TODAY}  \n**依据**：M3.38 指令任务 5；APR-006 未批准 → 无提交/无报关行意见\n\n"
            "---\n## 1. 归类状态\n\n"
            "| 状态 | 数量 | 说明 |\n|---|---|---|\n"
            "| CANDIDATE_HTSUS | 60 | 品类候选编码（非正式） |\n"
            "| BROKER_REVIEW_PENDING | 0 | 未提交（APR-006 未批） |\n"
            "| **BROKER_CONFIRMED** | **0** | 无报关行书面确认 |\n"
            "| NEEDS_FURTHER_REVIEW | 60 | 全部待正式归类 |\n\n"
            "---\n## 2. 规则\n"
            "- 状态只能根据真实证据更新；**不得将 AI 候选编码直接改为 BROKER_CONFIRMED**；6 位 HS 编码不得冒充美国正式 10 位 HTSUS。\n"
            "- 无书面确认 → 正式归类覆盖率 **0/60**。\n")


def m338_06():
    return ("# M3.38-06｜首批 DDP 真实报价（结果）\n\n"
            f"**生成时间**：{TODAY}  \n**依据**：M3.38 指令任务 6；APR-007 未批准 → 仅准备询价表，未联系货代\n\n"
            "---\n## 1. 报价状态\n\n"
            "| 状态 | 数量 | 说明 |\n|---|---|---|\n"
            "| QUOTE_REQUEST_PREPARED | 1 线路 | 询价表已备（未发送） |\n"
            "| QUOTE_REQUESTED | 0 | 未联系货代 |\n"
            "| **QUOTE_RECEIVED** | **0** | 无真实报价 |\n"
            "| QUOTE_REVIEWED | 0 | — |\n\n"
            "---\n## 2. 规则\n"
            "- 报价须含起运地/目的地/商品/申报价/重量/尺寸/计费重/方式/时效/清关责任/税费承担/尾程/"
            "Broker Fee/Disbursement Fee/保险/偏远/其他/有效期/费用包含关系（20 项）。\n"
            "- 至少对同一商品、同一线路、相同计费条件比较；不得不同服务条件直接比较。\n"
            "- 未报价项目保留 MISSING 不得默认 $0；无真实报价不得标记完整 DDP 已验证。\n")


def m338_07():
    return ("# M3.38-07｜首批 SKU 成本闭环（试点）\n\n"
            f"**生成时间**：{TODAY}  \n**依据**：M3.38 指令任务 7；8 项闭环条件，当前均不满足\n\n"
            "---\n## 1. 闭环条件检查\n\n"
            "| 条件 | 达标 |\n|---|---|\n"
            "| 1 可追溯采购价 | 26/60（缺实测重量） |\n"
            "| 2 实测商品重量 | 0/60 |\n"
            "| 3 实测包装尺寸 | 0/60 |\n"
            "| 4 正式 HTSUS | 0/60 |\n"
            "| 5 完整物流报价 | 0/60 |\n"
            "| 6 费用包含关系复核 | 0/60 |\n"
            "| 7 币种汇率口径 | 部分（USD 单一口径） |\n"
            "| 8 成本可复现 | 60/60（模型） |\n\n"
            "---\n## 2. 结论\n"
            "> **0 SKU 满足全部 8 项闭环条件**（实测/正式HTSUS/真实DDP 均为 0，阻塞于 APR-005/006/007）。\n"
            "- 不得为了完成阶段目标降低标准；如实报告 **0 SKU 完成闭环**。\n"
            "- 三种口径（A商品毛利/B履约贡献/C扣CAC净利）+ 三情景 + 置信度：模型预测与真实经营结果分开存储；"
            "**无真实盈利声称**。\n"
            "- 盈亏平衡售价/25%目标售价：需真实证据后按统一利润口径计算，当前仅模型情景。\n")


def m338_08(data):
    return ("# M3.38-08｜经营决策准备\n\n"
            f"**生成时间**：{TODAY}  \n**依据**：M3.38 指令任务 8；#1014/#1013 未批停售保持待审批；#1722 仅假设情景\n\n"
            "---\n## 1. 重点\n\n"
            "| SKU | 当前证据 | 成本验证 | 利润预测 | 风险 | 下一步 | 需 Owner 决策 |\n"
            "|---|---|---|---|---|---|---|\n"
            "| #1014 | 采购A档/重量EST/HS候选 | 未验证 | 估算-57.4% | 持续亏损 | 待真实亏损证据 | APR-001 停售 |\n"
            "| #1013 | 采购A档/重量EST/HS候选 | 未验证 | 估算-51.2% | 持续亏损 | 待真实亏损证据 | APR-002 停售 |\n"
            "| #1722 | 采购D档/重量EST/HS候选 | 未验证 | 估算-2.7% | 高关税 | 仅假设情景，不迁仓 | APR-003 海外仓 |\n\n"
            "---\n## 2. 结论\n"
            "- #1014/#1013：Owner 未批准停售 → 保持 **STOP_PENDING_OWNER_APPROVAL**，不擅自下架。\n"
            "- #1722：无可比真实直发/海外仓报价 → **只能给假设情景，不得建议立即迁仓**。\n"
            "- 60 SKU 均无 COST_VERIFIED / PROFIT_VERIFIED；真实证据采集率 0%（APR 未批）。\n")


def m338_09(data):
    return ("# M3.38-09｜阶段审计与验收\n\n"
            f"**生成时间**：{TODAY}  \n**依据**：M3.38 指令任务 9；14 问 + 4 指标\n\n"
            "---\n## 1. 14 问\n\n"
            "| # | 问题 | 答案 |\n|---|---|---|\n"
            "| 1 | APR-001~007 多少项获真实审批 | **0/7**（全 PENDING） |\n"
            "| 2 | 哪些动作实际启动 | 仅 A 类内部准备 |\n"
            "| 3 | 哪些动作仍被阻塞 | B 类全部（实测/采集/报关/货代） |\n"
            "| 4 | P0 六款实测完成 | 0/6 |\n"
            "| 5 | 13 款高端采购价补证 | 0/13 |\n"
            "| 6 | 正式 HTSUS 归类 | 0/60 |\n"
            "| 7 | 真实 DDP 报价 | 0/60 |\n"
            "| 8 | 完整成本闭环 SKU | 0 |\n"
            "| 9 | 成本仍低估/不确定 SKU | 60 |\n"
            "| 10 | 费用重复扣除 | 无（已验证单次） |\n"
            "| 11 | 未经授权对外联系 | 无 |\n"
            "| 12 | 未经授权经营/生产修改 | 无 |\n"
            "| 13 | 真实盈利支持 PROFIT_VERIFIED | 无（0） |\n"
            "| 14 | 报告/证据可追溯 | 是（reports/b2b/） |\n\n"
            "---\n## 2. 验收与阶段状态\n"
            "**验收：NEEDS_EVIDENCE**（真实证据采集 0%，阻塞于 Owner 审批）  \n"
            "**阶段状态：COMPLETED_WITH_NEEDS_EVIDENCE**\n\n"
            "---\n## 3. 4 指标分开（禁止冒充）\n\n"
            "| 指标 | 完成率 | 说明 |\n|---|---|---|\n"
            "| 1 内部准备完成率 | 100% | 模板/清单/审计/矩阵就绪 |\n"
            "| 2 Owner 审批通过率 | 0% | APR-001~007 全 PENDING |\n"
            "| 3 真实证据采集完成率 | 0% | 实测0/6、价0/13、HTSUS0/60、DDP0/60 |\n"
            "| 4 完整成本闭环完成率 | 0% | 0 SKU |\n\n"
            "---\n## 4. 测试/Ruff/Git\n"
            "- 测试 `test_m338.py`：审批状态/证据等级/费用缺失/重复费用/成本闭环逻辑。\n"
            "- Ruff：见工程输出。Git：从 d548b8e，见工程输出（reports/b2b/ 新增，不覆盖历史）。\n"
            "- **生产操作：无**（未联系外部、未改 WC/生产、未部署、未自动审批、未伪造证据）。\n\n"
            "---\n*最终原则：M3.38 成绩 = 真正增加的有来源/原始记录/复核/责任人的真实经营证据（本阶段 0，因 Owner 未授权）。*\n")


def main():
    data = recs()
    files = {
        "M338-01-approval-verification.md": m338_01(),
        "M338-02-execution-permission-matrix.md": m338_02(),
        "M338-03-p0-measurement-results.md": m338_03(data),
        "M338-04-premium-sku-price-results.md": m338_04(data),
        "M338-05-htsus-review-results.md": m338_05(),
        "M338-06-ddp-quote-results.md": m338_06(),
        "M338-07-cost-closure-pilot.md": m338_07(),
        "M338-08-business-decision-review.md": m338_08(data),
        "M338-09-final-audit.md": m338_09(data),
    }
    for fn, content in files.items():
        with open(os.path.join(OUT, fn), "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[written] {fn} ({len(content)} bytes)")
    print("STATUS:", dict(Counter(r["status"] for r in data)))
    print("DONE")


if __name__ == "__main__":
    main()

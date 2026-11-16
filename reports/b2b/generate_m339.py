"""M3.39 报告生成器：Owner Authorization & First Evidence Acquisition（M339-01~09）。
APR-004/005 已获 Owner 正式批准（2026-11-16，ChatGPT 整理）；其他 APR PENDING。
边界：不联系供应商/报关行/货代、不采购支付、不改 WC/生产/部署、不伪造证据、页面标价≠成交价。
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

# APR 状态（M3.39 正式审批）：APR-004/005 APPROVED，其他 PENDING
APR_STATUS = {"APR-001": "PENDING", "APR-002": "PENDING", "APR-003": "PENDING",
              "APR-004": "APPROVED", "APR-005": "APPROVED",
              "APR-006": "PENDING", "APR-007": "PENDING"}
APR_ITEMS = {"APR-001": ("#1014 不锈钢折叠烧烤架", "停售/下架", "未批准，先看真实亏损证据"),
             "APR-002": ("#1013 35L折叠收纳箱", "停售/下架", "未批准，先看真实亏损证据"),
             "APR-003": ("#1722 55L重装背包", "切换履约模式", "未批准，暂不迁仓先报价"),
             "APR-004": ("13 款高端商品", "采集1688公开价格/规格", "APPROVED 2026-11-16，Owner 明确授权"),
             "APR-005": ("P0 六款大件", "实物称重/尺寸/拍照", "APPROVED 2026-11-16，Owner 明确授权"),
             "APR-006": ("报关行", "HTSUS 正式归类", "未批准，先备资料再授权联系"),
             "APR-007": ("货代", "DDP 真实报价", "未批准，先明确线路再授权询价")}


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


def m339_01(data):
    """前置审计：Git/HEAD/worktree/报告/APR 原始申请+本次审批核验。"""
    return ("# M3.39-01｜M3.38 前置审计\n\n"
            f"**生成时间**：{TODAY}  \n**依据**：M3.39 指令任务 1；必须读取实际文件，不得仅凭摘要\n\n"
            "---\n## 1. Git 基线核验\n\n"
            "| 项 | 结果 |\n|---|---|\n"
            "| 分支 | main（符合） |\n"
            "| HEAD | e84e828（= M3.38 前置 Commit，符合） |\n"
            "| worktree 生产源码 | 21 文件既有未提交改动（M3.33 前遗留 B2B/前端工作，非 M3.39 阶段；如实记录不提交） |\n"
            "| M3.36~M3.38 报告 | M336-01/09、M337-01/09、M338-01/09 齐全 |\n"
            "| 模型脚本/测试 | generate_m336/337/338.py、test_m337/338.py 存在 |\n\n"
            "---\n## 2. APR 原始申请 + 本次审批核验\n\n"
            "| APR | 原始申请内容 | 真实 Owner 审批 | 状态 |\n|---|---|---|---|\n"
            "| APR-001 | #1014 停售 | 无 | PENDING |\n"
            "| APR-002 | #1013 停售 | 无 | PENDING |\n"
            "| APR-003 | #1722 海外仓 | 无 | PENDING |\n"
            "| APR-004 | 13款高端 1688 采集 | **有（2026-11-16，Owner 明确授权，ChatGPT 整理）** | **APPROVED** |\n"
            "| APR-005 | P0 六款实测 | **有（2026-11-16，Owner 明确授权，ChatGPT 整理）** | **APPROVED** |\n"
            "| APR-006 | 报关行 HTSUS | 无 | PENDING |\n"
            "| APR-007 | 货代 DDP | 无 | PENDING |\n\n"
            "---\n## 3. 审计结论\n"
            "- 前置文件齐全、Git 基线 e84e828 可确认；APR-004/005 为**真实 Owner 审批**（非 AI 摘要）。\n"
            "- 本次授权范围具体（SKU 清单、动作、排除项），有效期未限定（一次性授权范围）。\n"
            "- 无过期/撤销授权；无审批内容与拟执行动作不一致。\n")


def m339_02():
    """Owner 授权登记：APR-004/005 APPROVED，引用 Owner 明确授权记录。"""
    L = ["# M3.39-02｜Owner 授权登记\n\n",
         f"**生成时间**：{TODAY}  \n**依据**：M3.39 指令任务 2；APR-004/005 正式登记 APPROVED\n\n",
         "---\n## 1. 审批登记表\n\n",
         "| APR | 状态 | 审批人 | 审批日期 | 授权范围 | 证据引用 | DSH 登记 |\n",
         "|---|---|---|---|---|---|---|\n"]
    for aid in ["APR-001", "APR-002", "APR-003", "APR-004", "APR-005", "APR-006", "APR-007"]:
        item, _perm, _note = APR_ITEMS[aid]
        st = APR_STATUS[aid]
        if st == "APPROVED":
            L.append(f"| {aid} | **APPROVED** | Owner | 2026-11-16 | {item} | Owner 明确授权记录（ChatGPT M3.39 整理） | 已登记/待归档 |\n")
        else:
            L.append(f"| {aid} | PENDING | — | — | {item} | 无 | 未登记 |\n")
    L.append("---\n## 2. 登记说明\n"
             "- APR-004：授权 13 款高端（#1719–1728/#998/#1474/#1476）采集 1688 公开价/规格/MOQ/价格阶梯及原始页面证据。\n"
             "- APR-005：授权 P0 六款（#998/#1719/#1032/#1722/#996/#1723）实物称重/包装重量/长宽高/照片/原始记录/复核归档。\n"
             "- 排除：供应商询价谈判、采购支付、报关行/货代联系、停售/迁仓、WC 生产修改、生产库/API、生产部署。\n"
             "- 保存原始审批内容（非仅 AI 摘要）；DSH 登记与证据归档状态单独标记。\n")
    return "".join(L)


def m339_03(data):
    """P0 六款实测：APR-005 APPROVED → 任务单已建；实际称重需线下团队，0/6 MEASURED。"""
    p0 = [r for r in data if r["is_p0"]]
    L = ["# M3.39-03｜P0 六款实测证据\n\n",
         f"**生成时间**：{TODAY}  \n**依据**：M3.39 指令任务；APR-005 **APPROVED** → 已建内部测量任务单，待线下执行\n\n",
         "---\n## 1. 六款状态（统一证据档案）\n\n",
         "| SKU | 商品 | 净重 | 包装重 | 尺寸 | 证据状态 | 任务单 | 责任人 | 照片 | 复核 |\n",
         "|---|---|---|---|---|---|---|---|---|---|\n"]
    for r in p0:
        L.append(f"| #{r['wc']} | {r['name']} | EST(估算) | EST | EST | ESTIMATED | 已建 | 待分配 | 未拍 | 待定 |\n")
    L.append("---\n## 2. 测量规范\n"
             "- 字段区分：PRODUCT_NET_WEIGHT / PACKAGED_WEIGHT / PACKAGE_LENGTH/WIDTH/HEIGHT / CHARGEABLE_WEIGHT；"
             "体积重按实际承运商规则（禁止默认除数 5000）。\n"
             "- 证据状态：ESTIMATED / MEASURED_PENDING_REVIEW / MEASURED_VERIFIED；当前 **0/6 MEASURED**（任务单已建，"
             "实际称重需线下团队执行）。\n"
             "- **禁止将估算重量标记为实测**；原始照片/测量记录/采集时间需保留。\n"
             "- 统一 SKU 证据档案：#1719/#1722/#998 同时出现在实测与价格清单 → 与 M339-04 关联，避免两套工作台重复。\n")
    return "".join(L)


def m339_04(data):
    """13 款高端价格：APR-004 APPROVED → 采集启动；web_search 无 API key → 0/13 取得，不伪造。"""
    high = [r for r in data if r["is_high"]]
    L = ["# M3.39-04｜13 款高端采购价格证据\n\n",
         f"**生成时间**：{TODAY}  \n**依据**：M3.39 指令任务；APR-004 **APPROVED** → 采集启动；web_search 无 API key → 0/13 取得，不伪造\n\n",
         "---\n## 1. 证据状态（13 款）\n\n",
         "| SKU | 商品 | 公开页面价 | 价格类型 | 状态 | 原因 |\n|---|---|---|---|---|---|\n"]
    for r in high:
        L.append(f"| #{r['wc']} | {r['name']} | 未取得 | — | MISSING | 采集工具受限（web_search 无 API key） |\n")
    L.append("---\n## 2. 价格类型区分\n"
             "- PUBLIC_LISTED_PRICE / SUPPLIER_QUOTED_PRICE / VERIFIED_TRANSACTION_PRICE / ESTIMATED_PRICE 严格区分；"
             "**1688 页面标价 ≠ 真实成交价**。\n"
             "- 无原始页面链接/截图/采集时间 → 不得认定已取得；保留 MISSING/BLOCKED，**不伪造价格/链接/截图**。\n"
             "- 本任务仅限公开信息采集与内部证据核验；不含询价/谈判/下单/支付。\n")
    return "".join(L)


def m339_05():
    return ("# M3.39-05｜HTSUS 正式归类证据\n\n"
            f"**生成时间**：{TODAY}  \n**依据**：M3.39 指令；APR-006 PENDING → 保持 0/60 正式\n\n"
            "---\n## 1. 归类状态\n\n"
            "| 状态 | 数量 | 说明 |\n|---|---|---|\n"
            "| CANDIDATE_HTSUS | 60 | 品类候选（非正式） |\n"
            "| BROKER_CONFIRMED | 0 | 等待 APR-006 |\n"
            "| NEEDS_FURTHER_REVIEW | 60 | 全部待正式 |\n\n"
            "---\n## 2. 规则\n"
            "- 6 位 HS ≠ 美国正式 10 位 HTSUS；无报关行书面确认不得认定正式。\n"
            "- 保持 0/60，等待 APR-006 授权后提交。\n")


def m339_06():
    return ("# M3.39-06｜DDP 真实报价证据\n\n"
            f"**生成时间**：{TODAY}  \n**依据**：M3.39 指令；APR-007 PENDING → 保持 0/60 真实\n\n"
            "---\n## 1. 报价状态\n\n"
            "| 状态 | 数量 | 说明 |\n|---|---|---|\n"
            "| QUOTE_REQUEST_PREPARED | 1 线路 | 询价表已备（未发送） |\n"
            "| QUOTE_RECEIVED | 0 | 等待 APR-007 |\n\n"
            "---\n## 2. 规则\n"
            "- 报价须含 20 项（起运/目的地/商品/申报价/重量/尺寸/计费重/方式/时效/清关责任/税费/尾程/"
            "Broker/Disbursement/保险/偏远/其他/有效期/包含关系）；未报价保留 MISSING 不得默认 $0。\n"
            "- 保持 0/60，等待 APR-007 授权后询价。\n")


def m339_07(data):
    return ("# M3.39-07｜成本验证结果\n\n"
            f"**生成时间**：{TODAY}  \n**依据**：M3.39 指令；完整成本闭环需实测+正式HTSUS+真实DDP，当前不足\n\n"
            "---\n## 1. 闭环条件\n\n"
            "| 条件 | 达标 |\n|---|---|\n"
            "| 可追溯采购价 | 26/60 |\n"
            "| 实测重量 | 0/6（任务单已建待线下） |\n"
            "| 正式 HTSUS | 0/60 |\n"
            "| 真实 DDP 报价 | 0/60 |\n"
            "| 费用复核 | 0/60 |\n\n"
            "---\n## 2. 结论\n"
            "> **0 SKU 满足完整成本闭环**（实测/HTSUS/DDP 未到位，如实报告，不强行闭环）。\n"
            "- 模型预测与真实经营结果分开；**无真实盈利声称**。\n"
            "- 暂不强求闭环，等待证据积累（APR-004/005 执行中）。\n")


def m339_08(data):
    return ("# M3.39-08｜Owner 决策更新\n\n"
            f"**生成时间**：{TODAY}  \n**依据**：M3.39 指令；APR-004/005 批准后 P0/13款 进入执行准备\n\n"
            "---\n## 1. 决策状态\n\n"
            "| 事项 | 状态 | 说明 |\n|---|---|---|\n"
            "| APR-004/005 | APPROVED | P0 六款实测 + 13款价格采集进入执行准备 |\n"
            "| #1014/#1013 停售 | PENDING | 保持 STOP_PENDING_OWNER_APPROVAL，先看真实亏损证据 |\n"
            "| #1722 海外仓 | PENDING | 暂不迁仓，先取得真实报价 |\n"
            "| APR-006/007 | PENDING | 报关行/货代先备资料，再授权 |\n\n"
            "---\n## 2. 结论\n"
            "- 60 SKU 均无 COST_VERIFIED / PROFIT_VERIFIED（真实证据未到位）。\n"
            "- 本阶段不改变任何经营状态（未停售/未迁仓/未改价/未下架）。\n")


def m339_09(data):
    return ("# M3.39-09｜阶段审计与验收\n\n"
            f"**生成时间**：{TODAY}  \n**依据**：M3.39 指令任务 9；以真实证据数量衡量进展\n\n"
            "---\n## 1. 报告项\n\n"
            "| 指标 | 结果 |\n|---|---|\n"
            "| APR-001~007 审批 | APR-004/005 APPROVED（2/7），其余 PENDING（5/7） |\n"
            "| P0 六款实测 | 0/6 MEASURED（任务单已建，待线下） |\n"
            "| 13 款价格补证 | 0/13 取得（采集工具受限） |\n"
            "| 正式 HTSUS | 0/60（等 APR-006） |\n"
            "| DDP 真实报价 | 0/60（等 APR-007） |\n"
            "| 成本闭环 SKU | 0 |\n"
            "| 真实盈利验证 | 0 |\n"
            "| 新增证据文件/复核 | 0（本阶段仅登记+任务单） |\n"
            "| 未授权动作 | 无 |\n\n"
            "---\n## 2. 4 指标分开\n\n"
            "| 指标 | 完成率 |\n|---|---|\n"
            "| 内部准备完成率 | 100%（审计/登记/任务单/模板） |\n"
            "| Owner 审批通过率 | 2/7=28.6%（APR-004/005） |\n"
            "| 真实证据采集完成率 | 0%（实测0/6、价0/13、HTSUS0/60、DDP0/60） |\n"
            "| 完整成本闭环完成率 | 0% |\n\n"
            "---\n## 3. 验收\n"
            "**验收：NEEDS_EVIDENCE**（真实证据采集 0%，但审批已通过 2 项，APR-004/005 执行中）  \n"
            "**阶段状态：COMPLETED_WITH_NEEDS_EVIDENCE**  \n"
            "- 测试/Ruff/Git：见工程输出；从 e84e828；不覆盖历史证据；生产操作无。\n"
            "- **最终原则**：M3.39 不以报告完成率作为经营成果；以真实证据数量、复核数量、完整成本闭环数量衡量。\n")


def main():
    data = recs()
    files = {
        "M339-01-preflight-audit.md": m339_01(data),
        "M339-02-owner-authorization-register.md": m339_02(),
        "M339-03-p0-measurement-evidence.md": m339_03(data),
        "M339-04-premium-price-evidence.md": m339_04(data),
        "M339-05-htsus-evidence.md": m339_05(),
        "M339-06-ddp-evidence.md": m339_06(),
        "M339-07-cost-validation-results.md": m339_07(data),
        "M339-08-owner-decision-update.md": m339_08(data),
        "M339-09-final-audit.md": m339_09(data),
    }
    for fn, content in files.items():
        with open(os.path.join(OUT, fn), "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[written] {fn} ({len(content)} bytes)")
    print("STATUS:", dict(Counter(r["status"] for r in data)))
    print("DONE")


if __name__ == "__main__":
    main()

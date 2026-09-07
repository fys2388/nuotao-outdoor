"""Agent 评测集结构校验测试：每个 Agent ≥20 条、字段完整、可执行路由。"""

import json
from pathlib import Path

import pytest

from app.services.agent_eval_runner import (
    EVAL_FUNCTIONS,
    build_scorecard,
    load_eval_sets,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "agent_eval_sets"

REQUIRED_AGENTS = {
    "product_manager",
    "marketing_manager",
    "supply_chain_manager",
    "customer_manager",
    "business_analyst",
}

CASE_FIELDS = {"id", "category", "title", "eval_mode", "input", "expected"}
EXPECTED_FIELDS = {"output_keys", "rules"}


def test_all_five_agents_have_eval_sets():
    sets = load_eval_sets()
    agents = {s["agent_id"] for s in sets}
    assert agents == REQUIRED_AGENTS


@pytest.mark.parametrize("agent_id", sorted(REQUIRED_AGENTS))
def test_each_agent_has_at_least_20_cases(agent_id):
    sets = load_eval_sets()
    es = next(s for s in sets if s["agent_id"] == agent_id)
    assert len(es["cases"]) >= 20, f"{agent_id} 用例数 < 20"


@pytest.mark.parametrize("agent_id", sorted(REQUIRED_AGENTS))
def test_case_fields_valid(agent_id):
    sets = load_eval_sets()
    es = next(s for s in sets if s["agent_id"] == agent_id)
    ids = set()
    for case in es["cases"]:
        assert CASE_FIELDS <= set(case.keys()), f"{agent_id}/{case['id']} 缺字段"
        assert EXPECTED_FIELDS <= set(case["expected"].keys()), f"{agent_id}/{case['id']} expected 缺字段"
        assert case["eval_mode"] in ("deterministic", "llm")
        assert case["id"] not in ids, f"{agent_id} 重复用例 id: {case['id']}"
        ids.add(case["id"])


def test_json_files_parse_and_agent_ids_consistent():
    for path in sorted(DATA_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["agent_id"] in REQUIRED_AGENTS
        # 顶层 agent_id 应与文件名一致
        assert data["agent_id"] == path.stem, f"{path.name} agent_id 与文件名不一致"


def test_all_deterministic_cases_have_registered_eval_function():
    sets = load_eval_sets()
    unregistered = []
    for es in sets:
        agent_id = es["agent_id"]
        for case in es["cases"]:
            if case["eval_mode"] == "deterministic":
                key = (agent_id, case["category"])
                if key not in EVAL_FUNCTIONS:
                    unregistered.append(f"{agent_id}/{case['id']} ({case['category']})")
    assert not unregistered, f"未注册评测函数: {unregistered}"


def test_deterministic_scorecard_all_pass():
    """确定性用例必须全部通过（评测回归门槛）。"""
    sets = load_eval_sets()
    card = build_scorecard(sets, with_llm=False)
    assert card["executed"] >= 100, "确定性用例数不足 100"
    assert card["failed"] == 0, f"存在失败用例: {card['per_agent']}"
    assert card["skipped"] >= 10, "llm 用例应被跳过标记"

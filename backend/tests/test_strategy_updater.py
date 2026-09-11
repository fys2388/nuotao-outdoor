"""strategy_updater 测试（P2-9）：A/B 显著性精确计算 + 策略版本持久化与回滚。"""

import pytest

from app.models import StrategyVersion
from app.services import strategy_updater


# --------------------------------------------------------------------------- #
# A/B 显著性（评测集回归：修复 z/3 低估置信度的缺陷）
# --------------------------------------------------------------------------- #

def test_ab_significant_with_large_sample():
    """0.02 vs 0.05, n=500：真实置信度 ~0.99，应判显著且 B 胜。"""
    result = strategy_updater.evaluate_ab_test_result(
        variant_a_metrics={"conversion_rate": 0.02},
        variant_b_metrics={"conversion_rate": 0.05},
        sample_size_a=500,
        sample_size_b=500,
    )
    assert result["significant"] is True
    assert result["winner"] == "B"
    assert result["confidence"] >= 0.95


def test_ab_not_significant_with_small_sample():
    """n=30 未达最小样本量，不得下结论。"""
    result = strategy_updater.evaluate_ab_test_result(
        variant_a_metrics={"conversion_rate": 0.02},
        variant_b_metrics={"conversion_rate": 0.03},
        sample_size_a=30,
        sample_size_b=30,
    )
    assert result["significant"] is False
    assert result["winner"] == "none"


def test_ab_confidence_between_0_and_1():
    result = strategy_updater.evaluate_ab_test_result(
        variant_a_metrics={"conversion_rate": 0.02},
        variant_b_metrics={"conversion_rate": 0.07},
        sample_size_a=800,
        sample_size_b=800,
    )
    assert 0 < result["confidence"] < 1


def test_ab_relative_lift_calculation():
    result = strategy_updater.evaluate_ab_test_result(
        variant_a_metrics={"conversion_rate": 0.04},
        variant_b_metrics={"conversion_rate": 0.05},
        sample_size_a=600,
        sample_size_b=600,
    )
    assert result["relative_lift"] == pytest.approx(0.25, abs=1e-3)


def test_ab_zero_rate_defensive():
    result = strategy_updater.evaluate_ab_test_result(
        variant_a_metrics={"conversion_rate": 0},
        variant_b_metrics={"conversion_rate": 0},
        sample_size_a=200,
        sample_size_b=200,
    )
    assert result["significant"] is False


# --------------------------------------------------------------------------- #
# 策略版本持久化与回滚
# --------------------------------------------------------------------------- #

async def test_record_strategy_change_persists_version(db_session):
    """写入 strategy_versions 表，版本号按类型自增。"""
    result = await strategy_updater.record_strategy_change(
        db_session,
        strategy_type="pricing",
        old_config={"discount": 0.1},
        new_config={"discount": 0.15},
        reason="A/B 测试: B 变体胜出",
        changed_by="ab_test_auto",
        experiment_id="exp-001",
    )
    assert result["version"] == 1
    assert result["strategy_type"] == "pricing"

    result2 = await strategy_updater.record_strategy_change(
        db_session,
        strategy_type="pricing",
        old_config={"discount": 0.15},
        new_config={"discount": 0.2},
        reason="二次调优",
        changed_by="user",
    )
    assert result2["version"] == 2


async def test_rollback_strategy_restores_config(db_session):
    """回滚到指定版本：恢复 new_config 并写入回滚记录。"""
    await strategy_updater.record_strategy_change(
        db_session,
        strategy_type="marketing",
        old_config={"bid": 1.0},
        new_config={"bid": 2.0},
        reason="v1",
        changed_by="user",
    )
    v2 = await strategy_updater.record_strategy_change(
        db_session,
        strategy_type="marketing",
        old_config={"bid": 2.0},
        new_config={"bid": 3.0},
        reason="v2",
        changed_by="user",
    )
    # 回滚到 v2（bid=3.0 版本）
    rolled = await strategy_updater.rollback_strategy(
        db_session,
        strategy_type="marketing",
        version_id=str(v2["version_id"]),
        reason="新策略效果差，回滚",
    )
    assert rolled["rolled_back"] is True
    assert rolled["restored_config"] == {"bid": 3.0}
    assert rolled["restored_version"] == 2
    # 回滚记录已写入（change_type=rollback）
    assert rolled["rollback_record_version"] == 3


async def test_rollback_invalid_version_id(db_session):
    result = await strategy_updater.rollback_strategy(
        db_session,
        strategy_type="pricing",
        version_id="not-a-number",
        reason="x",
    )
    assert result["rolled_back"] is False

    result2 = await strategy_updater.rollback_strategy(
        db_session,
        strategy_type="pricing",
        version_id="999999",
        reason="x",
    )
    assert result2["rolled_back"] is False


async def test_update_strategy_from_ab_test_low_risk_auto_apply_persists(db_session):
    """低风险策略自动应用后写入版本记录（A/B→策略→版本闭环）。"""
    evaluation = strategy_updater.evaluate_ab_test_result(
        variant_a_metrics={"conversion_rate": 0.02},
        variant_b_metrics={"conversion_rate": 0.06},
        sample_size_a=600,
        sample_size_b=600,
    )
    result = await strategy_updater.update_strategy_from_ab_test(
        db_session,
        experiment_id="exp-002",
        experiment_name="首页头图 A/B",
        strategy_type="listing",
        evaluation=evaluation,
        winning_variant_config={"headline_style": "benefit_led"},
        auto_apply=True,
    )
    assert result["applied"] is True
    # 版本记录已写入
    versions = await db_session.execute(
        StrategyVersion.__table__.select().where(
            StrategyVersion.strategy_type == "listing"
        )
    )
    rows = versions.fetchall()
    assert len(rows) == 1
    assert rows[0].experiment_id == "exp-002"
